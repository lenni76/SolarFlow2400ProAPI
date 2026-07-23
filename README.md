# SolarFlow2400-API

[![HACS validation](https://github.com/lenni76/SolarFlow2400-API/actions/workflows/hacs.yml/badge.svg)](https://github.com/lenni76/SolarFlow2400-API/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/lenni76/SolarFlow2400-API/actions/workflows/hassfest.yml/badge.svg)](https://github.com/lenni76/SolarFlow2400-API/actions/workflows/hassfest.yml)
[![Ruff](https://github.com/lenni76/SolarFlow2400-API/actions/workflows/ruff.yml/badge.svg)](https://github.com/lenni76/SolarFlow2400-API/actions/workflows/ruff.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


A custom [Home Assistant](https://www.home-assistant.io/) integration that talks to a
SolarFlow2400-API device **entirely over the local network**, using the official
Zendure **zenSDK** local HTTP API. Once the device's IP is known, the integration
never contacts the internet or the Zendure cloud — it works fully offline on your LAN.

This is a port of a working IP-Symcon PHP script to a modern, config-flow based
Home Assistant integration. Every property name, unit, access flag and value range
is taken directly from the official Zendure documentation (see
[Sources](#sources)); nothing is guessed. Where the documentation is silent or
inconsistent, this README says so explicitly.

## What it does

- **Auto-discovery** via mDNS/zeroconf (`_zendure._tcp.local.`), or manual setup by IP.
- Polls `GET /properties/report` on a configurable interval (default 30 s).
- Creates a **sensor for every property** the device reports (typed sensors for the
  documented ones, raw diagnostic sensors — disabled by default — for anything else,
  so nothing is lost).
- Creates a separate HA **device per battery pack**, linked to the main unit.
- Exposes all **writable** properties as proper controls (`number`, `select`, `switch`),
  which write back via `POST /properties/write`.

## Requirements

- Home Assistant **2024.12** or newer (uses the typed `runtime_data` config-entry pattern).
- The device's **local API must be enabled**. Per the zenSDK README, on current
  firmware (EN 18031) the local HTTP API is **disabled by default**. To enable it:
  **add a HEMS in the Zendure app, then remove it again** — this activates the local API.
- The device must be reachable on your LAN (a fixed/reserved DHCP IP is recommended).

## Installation

### Via HACS (recommended)

1. In HACS → *Integrations* → three-dot menu → **Custom repositories**.
2. Add this repository URL, category **Integration**.
3. Install **SolarFlow2400-API** and restart Home Assistant.

### Manual

Copy `custom_components/solarflow2400_api/` into your Home Assistant
`config/custom_components/` folder and restart.

## Setup

- If the device is discovered automatically, you'll get a notification — just confirm.
- Otherwise: *Settings → Devices & Services → Add Integration → SolarFlow2400-API*,
  then enter the device's IP address.

The integration reads the serial number (`sn`) from the device itself, so — unlike the
original Symcon script — you do **not** have to enter it by hand. The `sn` is also used
as the unique ID, so re-adding or a changed IP won't create duplicates.

The polling interval can be changed later under the integration's **Configure** (options).

## Writable controls

All ranges/labels below are from the zenSDK property table.

| Entity type | Property | Range / options (source) |
|---|---|---|
| number | `socSet` | 70–100 % (**documented**) |
| number | `minSoc` | 0–50 % (**documented**) |
| number | `outputLimit` | W — *UI bound* 0–2400 (max not in doc) |
| number | `inputLimit` | W — *UI bound* 0–2400 (max not in doc) |
| number | `inverseMaxPower` | W — *UI bound* 0–2400 (max not in doc) |
| number | `batCalTime` | minutes — *disabled by default* ("not recommended") |
| select | `acMode` | 1 (charge) / 2 (discharge) — doc: "Charge or discharge mode", range 1–2 |
| select | `gridReverse` | 0 / 1 / 2 (no per-value labels documented) |
| select | `gridOffMode` | Standard / Economic / Closure (**documented**) |
| select | `gridStandard` | Germany…Italy 0–9 (**documented**) — *disabled by default* |
| select | `Fanspeed` | Auto / Gear 1 / Gear 2 — *disabled by default* ("not recommended") |
| switch | `smartMode` | 0/1 — 1 = don't persist to flash (**documented**) |
| switch | `Fanmode` | 0/1 off/on — *disabled by default* ("not recommended") |

Entities are only created for properties your specific device actually reports, so an
800-series unit won't show controls it doesn't support.

## Important notes on the data (verified)

- **`socSet` / `minSoc` are plain percentages, not tenths.** The Zendure property
  documentation lists `socSet` with unit **%** and range **70–100**, and `minSoc` with
  unit **%** and range **0–50**. This integration therefore reads and writes them as
  plain integers. The original Symcon script divided/multiplied these by 10 — that
  scaling is **not** supported by the official documentation, so it was intentionally
  dropped. If your firmware genuinely reports tenths, open an issue.
- **`BatVolt`, `maxVol`, `minVol`** are reported in **0.01 V** and are scaled to volts.
  **`maxTemp`** is reported in **0.1 Kelvin** and converted to °C via `(raw − 2731) / 10`.
  All of these conversions are documented in the zenSDK property reference.
- **`Fanspeed`** has a documented inconsistency: the table's *Range* column says `0–1`
  while its *Description* says `0 Auto / 1 / 2`. This integration follows the description
  (three options) and disables the entity by default.
- **Power-limit maxima** (`outputLimit`, `inputLimit`, `inverseMaxPower`) are **not**
  specified by Zendure. The 0–2400 W slider bounds are UI-only; the device enforces its
  own real limits. Adjust them in `number.py` for your model if needed.

## Offline behaviour

All communication is direct HTTP to the device's LAN IP (`iot_class: local_polling`).
There is no cloud dependency after setup. If the device goes offline, its entities become
*unavailable* and recover automatically on the next successful poll.

## Files

```
custom_components/solarflow2400_api/
├── __init__.py          # setup/unload, platform forwarding, runtime_data
├── api.py               # async HTTP client (GET report / POST write)
├── binary_sensor.py     # read-only 0/1 flags
├── config_flow.py       # user + zeroconf flow, options flow
├── const.py             # constants (all from zenSDK docs)
├── coordinator.py       # DataUpdateCoordinator + report normalization
├── entity.py            # base device / battery-pack entities
├── manifest.json
├── number.py            # writable numeric properties
├── select.py            # writable enumerated properties
├── sensor.py            # device + battery-pack sensors (+ raw fallback)
├── strings.json
├── switch.py            # writable boolean properties
└── translations/        # en, de
```

## Disclaimer

Not affiliated with or endorsed by Zendure. Writing properties such as `gridStandard`,
`batCalTime`, `Fanmode` and `Fanspeed` can affect device behaviour; Zendure marks several
of these as "unauthorized modification not recommended", which is why they are disabled by
default here. Use at your own risk.

## Sources

- Zendure zenSDK — <https://github.com/Zendure/zenSDK>
- SolarFlow property reference — <https://github.com/Zendure/zenSDK/blob/main/docs/en_properties.md>
- HA integration manifest — <https://developers.home-assistant.io/docs/creating_integration_manifest>
- HA config entries — <https://developers.home-assistant.io/docs/config_entries_index>

## License

This project is licensed under the [MIT License](LICENSE).
