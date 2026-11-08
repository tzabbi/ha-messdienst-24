from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import Messdienst24ConfigEntry, Messdienst24Coordinator
from .parsing import Meter, Reading

_LOGGER = logging.getLogger(__name__)

# kind -> (device_class, unit, suggested display precision)
_KIND_CONFIG = {
    "heat": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0),
    "warm_water": (SensorDeviceClass.WATER, UnitOfVolume.CUBIC_METERS, 3),
    "cold_water": (SensorDeviceClass.WATER, UnitOfVolume.CUBIC_METERS, 3),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Messdienst24ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MeterSensor(coordinator, number) for number in coordinator.data)


class MeterSensor(CoordinatorEntity[Messdienst24Coordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: Messdienst24Coordinator, number: str) -> None:
        super().__init__(coordinator)
        self._number = number
        meter = coordinator.data[number]
        device_class, unit, precision = _KIND_CONFIG.get(meter.kind, (None, None, None))
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision
        if meter.kind in _KIND_CONFIG:
            # Long-term statistics incl. the imported portal history.
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            # Picks the per-meter-type icon from icons.json.
            self._attr_translation_key = meter.kind
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{number}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, number)},
            name=f"{meter.label} {number}",
            manufacturer=MANUFACTURER,
            model=meter.label,
            serial_number=number,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.state_class is None or self.coordinator.history_imported(self._number):
            return
        self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self._async_import_history(),
            f"{DOMAIN} history import {self.entity_id}",
        )

    async def _async_import_history(self) -> None:
        if (meter := self._meter) is None:
            return
        try:
            await self.coordinator.async_import_history(
                meter, self.entity_id, self.unit_of_measurement
            )
        except HomeAssistantError as err:
            _LOGGER.warning("History import for %s failed: %s", self.entity_id, err)

    @property
    def _meter(self) -> Meter | None:
        return self.coordinator.data.get(self._number)

    @property
    def _reading(self) -> Reading | None:
        # Zero readings mean missing data; reporting them would look like a
        # meter reset and count the next reading twice in the statistics.
        meter = self._meter
        return meter.latest_valid if meter else None

    @property
    def available(self) -> bool:
        return super().available and self._meter is not None

    @property
    def native_value(self) -> float | None:
        reading = self._reading
        return reading.value if reading else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        meter, reading = self._meter, self._reading
        if not meter or not reading:
            return None
        return {
            "ablesedatum": reading.date.isoformat(),
            "zaehlerart": meter.label,
        }
