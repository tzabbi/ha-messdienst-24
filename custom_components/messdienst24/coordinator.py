from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    EnergyConverter,
    VolumeConverter,
)

from .api import Messdienst24AuthError, Messdienst24Client, Messdienst24Error
from .const import CONF_IMPORTED_HISTORY, DOMAIN, UPDATE_INTERVAL
from .parsing import Meter, consumption_sums

_LOGGER = logging.getLogger(__name__)

type Messdienst24ConfigEntry = ConfigEntry[Messdienst24Coordinator]

# kind -> (unit converter, native unit)
STAT_UNITS: dict[str, tuple[type[BaseUnitConverter], str]] = {
    "heat": (EnergyConverter, UnitOfEnergy.KILO_WATT_HOUR),
    "warm_water": (VolumeConverter, UnitOfVolume.CUBIC_METERS),
    "cold_water": (VolumeConverter, UnitOfVolume.CUBIC_METERS),
}

# (start, meter value, cumulative consumption), all in the native unit
type HistoryPoint = tuple[datetime, float, float]


def legacy_statistic_id(meter: Meter) -> str:
    """External statistic written by version 0.1.0, migrated to the sensor."""
    return f"{DOMAIN}:{meter.kind}_{meter.number}".lower()


class Messdienst24Coordinator(DataUpdateCoordinator[dict[str, Meter]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: Messdienst24ConfigEntry,
        client: Messdienst24Client,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Meter]:
        try:
            meters = await self.client.async_get_meters()
        except Messdienst24AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Messdienst24Error as err:
            raise UpdateFailed(str(err)) from err
        if not meters:
            raise UpdateFailed("No meters found on the consumption page")
        return {m.number: m for m in meters}

    def history_imported(self, number: str) -> bool:
        return number in self.config_entry.data.get(CONF_IMPORTED_HISTORY, [])

    @callback
    def _mark_history_imported(self, number: str) -> None:
        entry = self.config_entry
        done = set(entry.data.get(CONF_IMPORTED_HISTORY, []))
        if number in done:
            return
        self.hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_IMPORTED_HISTORY: sorted(done | {number})},
        )

    async def async_import_history(
        self, meter: Meter, entity_id: str, unit: str | None
    ) -> None:
        """Import the portal's reading history into the sensor's statistics.

        Runs once per meter. Afterwards the recorder compiles the sensor's
        statistics itself (state_class total_increasing), so new readings are
        recorded at the time they are fetched.

        The recorder starts its own sum at 0 with the current reading, so the
        imported sums are shifted to end at 0 with the newest reading. Only
        sum differences matter (Energy dashboard, statistics cards), so the
        negative absolute values of the old rows are harmless.
        """
        if meter.kind not in STAT_UNITS or self.history_imported(meter.number):
            return
        converter, native_unit = STAT_UNITS[meter.kind]
        if unit not in converter.VALID_UNITS:
            return

        points = await self._history_points(meter)
        if not points:
            self._mark_history_imported(meter.number)
            return
        shift = points[-1][2]

        # The recorder inserts its compiled hourly rows without checking for
        # existing ones, so never import into hours it may compile itself:
        # only hours before the current one and before any existing row.
        cutoff = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        if first := await self._first_statistic_start(entity_id, cutoff):
            cutoff = min(cutoff, first)
        points = [p for p in points if p[0] < cutoff]

        if points:
            _LOGGER.debug("Importing %s statistics for %s", len(points), entity_id)
            async_import_statistics(
                self.hass,
                StatisticMetaData(
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=None,
                    source="recorder",
                    statistic_id=entity_id,
                    unit_class=converter.UNIT_CLASS,
                    unit_of_measurement=unit,
                ),
                [
                    StatisticData(
                        start=start,
                        state=converter.convert(value, native_unit, unit),
                        sum=round(
                            converter.convert(total - shift, native_unit, unit), 6
                        ),
                    )
                    for start, value, total in points
                ],
            )
        self._mark_history_imported(meter.number)

    async def _first_statistic_start(
        self, statistic_id: str, before: datetime
    ) -> datetime | None:
        """Start of the oldest long-term statistic row before `before`, if any."""
        recorder = get_instance(self.hass)
        if not await recorder.async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, False, {"sum"}
        ):
            return None
        rows = (
            await recorder.async_add_executor_job(
                statistics_during_period,
                self.hass,
                datetime.fromtimestamp(0, UTC),
                before + timedelta(hours=1),
                {statistic_id},
                "hour",
                None,
                {"sum"},
            )
        ).get(statistic_id)
        return dt_util.utc_from_timestamp(rows[0]["start"]) if rows else None

    async def _history_points(self, meter: Meter) -> list[HistoryPoint]:
        """Portal readings, prefixed by the legacy external statistic if present.

        The legacy statistic may contain readings that are no longer shown in
        the portal, so it is kept as is and continued with newer readings.
        """
        points: list[HistoryPoint] = [
            (
                dt_util.as_utc(dt_util.start_of_local_day(reading.date)),
                reading.value,
                total,
            )
            for reading, total in consumption_sums(meter.readings)
        ]

        legacy_id = legacy_statistic_id(meter)
        rows = (
            await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                datetime.fromtimestamp(0, UTC),
                None,
                {legacy_id},
                "hour",
                None,
                {"state", "sum"},
            )
        ).get(legacy_id)
        legacy = [
            (dt_util.utc_from_timestamp(row["start"]), row["state"], row["sum"])
            for row in rows or []
            if row.get("state") is not None and row.get("sum") is not None
        ]
        if not legacy:
            return points

        last_start, _, last_sum = legacy[-1]
        anchor = [p for p in points if p[0] <= last_start]
        offset = last_sum - (anchor[-1][2] if anchor else 0.0)
        return legacy + [
            (start, value, total + offset)
            for start, value, total in points
            if start > last_start
        ]
