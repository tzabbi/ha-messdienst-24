"""Messdienst24 (EXTERN Messdienst) meter readings."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import Messdienst24Client
from .const import CONF_MD, DEFAULT_MD
from .coordinator import Messdienst24ConfigEntry, Messdienst24Coordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: Messdienst24ConfigEntry
) -> bool:
    # Own session so the portal's session cookies don't leak into the shared jar.
    client = Messdienst24Client(
        async_create_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_MD, DEFAULT_MD),
    )
    coordinator = Messdienst24Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: Messdienst24ConfigEntry
) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
