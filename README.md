# Messdienst24 (EXTERN) for Home Assistant

<img src="custom_components/messdienst24/brand/icon.png" alt="Messdienst24 logo" width="96" align="right">

Custom Home Assistant integration that reads the meter values (heat, warm water,
cold water) from the tenant portal **[legacy.messdienst24.de](https://legacy.messdienst24.de/)**
operated by EXTERN Messdienst GmbH - including the full reading history.

> Unofficial project, not affiliated with EXTERN Messdienst GmbH. The portal has
> no public API, so this integration logs in like a browser and parses the HTML.
> Changes to the portal may break it.

_Deutsch: Inoffizielle Integration, die die Zählerstände (Heizung, Warmwasser,
Kaltwasser) inkl. Historie aus dem Mieterportal von messdienst24 in Home
Assistant holt._

## Features

- One device + sensor per meter, with the current reading:

  | Meter type  | Unit | Device class | Icon                    |
  |-------------|------|--------------|-------------------------|
  | Heat        | kWh  | `energy`     | `mdi:radiator`          |
  | Warm water  | m³   | `water`      | `mdi:water-thermometer` |
  | Cold water  | m³   | `water`      | `mdi:water`             |

  Attributes: `ablesedatum` (date of the reading in the portal),
  `zaehlerart`, `statistik_id`.
- **Full history import** as external statistics
  (`messdienst24:<type>_<meter number>`), usable in the Energy dashboard and in
  statistics graph cards. New readings are appended on every update.
- Data cleanup during import: leading zero readings are skipped, small drops
  (portal corrections) are ignored, large drops (annual reset) are treated as a
  meter reset.
- Config flow (UI setup) and re-authentication when the password changes.
- Polls every 6 hours (the portal only publishes new readings a few times per
  month).

## Requirements

- Home Assistant **2026.3** or newer
- A tenant account (Mieterzugang) for legacy.messdienst24.de

## Installation

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories* → add
   `https://github.com/tzabbi/ha-messdienst-24`, category *Integration*.
2. Install **Messdienst24 (EXTERN)** and restart Home Assistant.

### Manual

Copy `custom_components/messdienst24` into `<config>/custom_components/` and
restart Home Assistant.

## Configuration

*Settings → Devices & services → Add integration → Messdienst24*, then enter:

- **Username / password** of the portal
- **Metering service code**: the `md` parameter from the portal URL
  (`https://legacy.messdienst24.de/?md=ex` → `ex`)

## Energy dashboard

Use the **statistics** (`Kaltwasser …`, `Warmwasser …`, `Heizung …`), not the
sensors - only the statistics contain the imported history. The sensors
intentionally have no long-term statistics to avoid duplicates.

- Water meters → *Water consumption*
- Heat meter (kWh) → there is no dedicated heat category; *Gas consumption*
  (accepts kWh) works as a workaround.

Consumption appears on the reading dates (roughly twice a month), because the
portal does not provide finer data.

## Limitations

- Only tested with tenant accounts of EXTERN Messdienst (`md=ex`). Landlord
  accounts or other metering services on the same portal may have a different
  page layout.
- Meter types are detected from the portal's icons (`mbt4` heat, `mbt6` warm
  water, `mbt7` cold water). Unknown types are added without unit.
- The portal itself transmits the credentials as URL query parameters (over
  HTTPS); the integration has to do the same.

## Development / troubleshooting

The `scripts/` folder contains standalone helpers (they read
`scripts/credentials.ini`, see `credentials.ini.example`):

- `md24_discover.py` - logs in and dumps all portal pages to `scripts/dump/`
  (contains personal data, git-ignored). Useful if your account looks different.
- `test_client.py` - runs the integration's client without Home Assistant
  (`pip install aiohttp`).
- `make_brand_icon.py` - regenerates the logo (`pip install pillow`).

Debug logging:

```yaml
logger:
  logs:
    custom_components.messdienst24: debug
```

## License

MIT - see [LICENSE](LICENSE).
