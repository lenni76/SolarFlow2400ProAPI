# SolarFlow2400-API

[![HACS validation](https://github.com/lenni76/SolarFlow2400ProAPI/actions/workflows/validate-release.yml/badge.svg)](https://github.com/lenni76/SolarFlow2400ProAPI/actions/workflows/validate-release.yml)
[![Hassfest](https://github.com/lenni76/SolarFlow2400ProAPI/actions/workflows/validate-release.yml/badge.svg)](https://github.com/lenni76/SolarFlow2400ProAPI/actions/workflows/validate-release.yml)
[![Ruff](https://github.com/lenni76/SolarFlow2400ProAPI/actions/workflows/validate-release.yml/badge.svg)](https://github.com/lenni76/SolarFlow2400ProAPI/actions/workflows/validate-release.yml)
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

- Home Assistant **2026.10.2** or newer. Version 1.2.1 uses the current
  config-entry-scoped device lookup for battery-to-hub links; 2026.10.2 is the
  minimum compatibility target for this update.
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
| select | `gridReverse` | 0 / 1 / 2 retained; Chinese SDK reference: disabled / allow / prohibit reverse flow |
| select | `gridOffMode` | Standard / Economic / Closure (**documented**) |
| select | `gridStandard` | Germany…Italy 0–9 (**documented**) — *disabled by default* |
| select | `Fanspeed` | Auto / Gear 1 / Gear 2 — *disabled by default* ("not recommended") |
| switch | `smartMode` | 0/1 — 1 = don't persist to flash (**documented**) |
| switch | `Fanmode` | 0/1 off/on — *disabled by default* ("not recommended") |

Entities are only created for properties your specific device actually reports, so an
800-series unit won't show controls it doesn't support.

## Important notes on the data (verified)

- **`socSet` / `minSoc` are transported by the tested firmware in tenths of a
  percent.** The integration converts reported API values such as `930` and `110` to
  **93 %** and **11 %** in Home Assistant. Values written from Home Assistant are
  multiplied by 10 before being sent back to the device.
- **`BatVolt`, `maxVol`, `minVol`** are reported in **0.01 V** and are scaled to volts.
  **`maxTemp` and `hyperTmp`** are reported in **0.1 Kelvin** and converted to °C
  via `(raw − 2731) / 10`, as specified in OpenAPI 1.0.2.
- **`totalVol`** is scaled by 0.01 V, matching
  [Zendure's own HA integration](https://github.com/Zendure/Zendure-HA/blob/master/custom_components/zendure_ha/entity.py).
  OpenAPI's V label omits the raw scaling. Earlier versions exposed values
  100 times too large: history is not automatically rescaled. Remove any /100
  workaround in your own templates when updating.
- **`batcur`** is a signed 16-bit two's-complement current in tenths of an ampere:
  `65534` becomes **−0.2 A**. Already signed values are also supported. The sensor
  remains disabled by default, as does `hyperTmp`.
- Battery **`packType` and `heatState`** are disabled diagnostic sensors, created
  only if the device reports these fields. Existing unique IDs remain unchanged.
- SOC wire scaling is also explicit in the Chinese property reference
  (`socSet` 700–1000; `minSoc` 0–500). The English OpenAPI schema instead gives
  percent ranges. This integration preserves the wire scaling verified on a
  SolarFlow2400 Pro report; it does not blindly send the schema's percent values.
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
- API contract checked on 2026-10-19 — [OpenAPI 1.0.2](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/docs/openapi.yaml)
- Wire values and enum meanings — [Chinese property reference](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/docs/zh_properties.md)
- HA integration manifest — <https://developers.home-assistant.io/docs/creating_integration_manifest>
- HA config entries — <https://developers.home-assistant.io/docs/config_entries_index>

## License

This project is licensed under the [MIT License](LICENSE).


## Home Assistant compatibility update (1.2.1)

Battery devices now link to the main device using `via_device_id`. The main
device is registered before platform setup, so battery discovery also works on
first installation. Existing device identifiers and entity unique IDs remain
unchanged.

Manual setup and Zeroconf discovery leave host-change reloads to the existing
config-entry update listener. This avoids a second reload and the deprecated
combination scheduled to become an error in Home Assistant 2026.12.

For an existing HACS installation, update this integration through HACS after
the new version is published, then restart Home Assistant. Keep the existing
integration entry and its devices.

Discovery also preserves the HTTP port advertised by the device. MQTT setup via
`/rpc` is outside this local HTTP integration's scope.

The detailed API audit and remaining proposals are in
[API-ABGLEICH-2026-10-19.md](API-ABGLEICH-2026-10-19.md).

## Isolated regression tests

Use Python 3.12 or newer, install `tests/requirements.txt` in a test environment,
then run `python -m unittest discover -s tests -v`. The 68 tests use HA doubles
and aiohttp's real JSON decoder, with no network access to a SolarFlow device.
They do not replace a full HA instance/device test.

## Diagnose und Befehlssicherheit (ab Version 1.2.0)

Die Integration prüft Schreibbefehle anhand der Geräterückmeldung und wiederholt sie bei Abweichung einmal. Im vorbereiteten Stand 1.2.1 führen endgültig unbestätigte Befehle zu einem HA-Servicefehler. Kürzlich bestätigte gleiche Sollwerte können ohne zusätzlichen Aufruf übernommen werden; Nullleistungsbefehle werden immer gesendet. Es gibt keine zusätzliche Totzone oder Mindestpause.

Recovery bleibt standardmäßig aus. Sie ist nur bei einem Ausgangsbefehl über 0 W im bestätigten Entladebetrieb mit gemeldeter Rückspeisesperre zulässig. Die Rückkehr zum ursprünglichen AC-Modus wird auch bei Abbruch versucht und geprüft. Der aktuelle Gerätezustand wird getrennt vom letzten Befehlsresultat angezeigt.

Vier neue Diagnosezähler zeigen API-Schreibversuche, vermiedene Doppelbefehle, Wiederholungen und Recovery-Schreibversuche. Diese zählen keine physischen Flash-Schreibvorgänge. Dokumentierte Entitäten haben deutsche/englische Namen; die Leistungsfelder zeigen gemeldete Grenzen und erlauben 1-W-Schritte. Bestehende Unique IDs und Auswahlwerte bleiben erhalten.

Der Ziel-Netzbezug bleibt Aufgabe des separaten Reglers und dort über die Visualisierung einstellbar. In dieser API-Integration wurde kein zweiter Zielwert ergänzt. [Umsetzung und Bedienung](VERBESSERUNGEN-UND-BEDIENUNG.md).

Neue Diagnoseentitäten:

- **Zendure Status** – verständlicher, aus beobachtbaren Daten abgeleiteter Integrationsstatus.
- **Zendure Zustand** – kompakte Bewertung (`OK`, `Eingeschränkter Betrieb`, `Fehler`).
- **Letzter Steuerbefehl** – Soll-, Sende- und Rückmeldewerte sowie Zeitpunkte.

Wichtig: Nicht eindeutig dokumentierte Geräte-Rohwerte werden niemals interpretiert. Sie bleiben als Rohwert sichtbar.

## Version selection and rollback

The unchanged 1.2.0 release remains selectable in HACS. The new 1.2.1 release is
published only after CI checks pass. A rollback with higher version 1.2.2 is
prepared from the original runtime code and will only be released if needed.
[Update and rollback instructions](docs/HACS-UPDATE-UND-ROLLBACK.md).
