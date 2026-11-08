from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import Messdienst24ConfigEntry, Messdienst24Coordinator, statistic_id
from .parsing import Meter

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
    # No state_class on purpose: long-term statistics (incl. history) come from
    # the external statistics imported by the coordinator. A state_class here
    # would create a second, history-less statistic for the same meter.

    def __init__(self, coordinator: Messdienst24Coordinator, number: str) -> None:
        super().__init__(coordinator)
        self._number = number
        meter = coordinator.data[number]
        device_class, unit, precision = _KIND_CONFIG.get(meter.kind, (None, None, None))
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision
        # Picks the per-meter-type icon from icons.json.
        if meter.kind in _KIND_CONFIG:
            self._attr_translation_key = meter.kind
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{number}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, number)},
            name=f"{meter.label} {number}",
            manufacturer=MANUFACTURER,
            model=meter.label,
            serial_number=number,
        )

    @property
    def _meter(self) -> Meter | None:
        return self.coordinator.data.get(self._number)

    @property
    def available(self) -> bool:
        return super().available and self._meter is not None

    @property
    def native_value(self) -> float | None:
        meter = self._meter
        return meter.latest.value if meter and meter.latest else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        meter = self._meter
        if not meter or not meter.latest:
            return None
        return {
            "ablesedatum": meter.latest.date.isoformat(),
            "zaehlerart": meter.label,
            "statistik_id": statistic_id(meter),
        }
