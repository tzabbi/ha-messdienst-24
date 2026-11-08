from __future__ import annotations

import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter, VolumeConverter

from .api import Messdienst24AuthError, Messdienst24Client, Messdienst24Error
from .const import DOMAIN, UPDATE_INTERVAL
from .parsing import Meter, consumption_sums

_LOGGER = logging.getLogger(__name__)

type Messdienst24ConfigEntry = ConfigEntry[Messdienst24Coordinator]

# kind -> (unit_class, unit)
_STAT_UNITS = {
    "heat": (EnergyConverter.UNIT_CLASS, UnitOfEnergy.KILO_WATT_HOUR),
    "warm_water": (VolumeConverter.UNIT_CLASS, UnitOfVolume.CUBIC_METERS),
    "cold_water": (VolumeConverter.UNIT_CLASS, UnitOfVolume.CUBIC_METERS),
}


def statistic_id(meter: Meter) -> str:
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

        for meter in meters:
            if meter.kind in _STAT_UNITS:
                await self._insert_statistics(meter)
        return {m.number: m for m in meters}

    async def _insert_statistics(self, meter: Meter) -> None:
        """Import the portal's reading history as external statistics.

        Each reading is stored at local midnight of its reading date with
        state = meter value and sum = cumulative consumption. Only readings
        newer than the last imported one are added, continuing its sum.
        """
        stat_id = statistic_id(meter)
        unit_class, unit = _STAT_UNITS[meter.kind]
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{meter.label} {meter.number}",
            source=DOMAIN,
            statistic_id=stat_id,
            unit_class=unit_class,
            unit_of_measurement=unit,
        )

        points = [
            (dt_util.start_of_local_day(reading.date), reading.value, total)
            for reading, total in consumption_sums(meter.readings)
        ]
        if not points:
            return

        last = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, stat_id, True, {"sum"}
        )
        offset = 0.0
        if last and last.get(stat_id):
            last_ts = last[stat_id][0]["start"]
            last_sum = last[stat_id][0]["sum"] or 0.0
            # Anchor on the newest already imported reading so the sum stays
            # continuous even if old readings drop out of the portal's window.
            anchor = [p for p in points if p[0].timestamp() <= last_ts]
            offset = last_sum - (anchor[-1][2] if anchor else 0.0)
            points = [p for p in points if p[0].timestamp() > last_ts]

        if not points:
            return
        _LOGGER.debug("Adding %s statistics for %s", len(points), stat_id)
        async_add_external_statistics(
            self.hass,
            metadata,
            [
                StatisticData(start=start, state=value, sum=round(total + offset, 6))
                for start, value, total in points
            ],
        )
