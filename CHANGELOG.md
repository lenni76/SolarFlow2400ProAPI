# Changelog

## 1.2.1 - 2026-10-19 (locally prepared, unpublished)

- Align sensor decoding with zenSDK OpenAPI 1.0.2 (SDK commit 9b68389):
  decode batcur as signed int16 / 10 A and convert hyperTmp from 0.1 K to °C.
- Scale battery totalVol by 0.01 V, matching Zendure's own HA integration.
  Existing history is not rescaled; remove any user-side /100 workaround on update.
- Expose reported battery packType and heatState as disabled diagnostic sensors.
- Honor the HTTP port advertised by Zeroconf and bracket IPv6 address literals.
- Preserve SOC wire scaling and existing selection strings; document differences
  between the OpenAPI schema and the manufacturer's Chinese property reference.
- Replace the deprecated battery `via_device` identifier tuple with
  `via_device_id`, resolved within the owning config entry.
- Register the main device before platform setup so the lookup also works on
  first installation and independently of platform setup order.
- Preserve main and battery identifiers and all entity unique IDs.
- Let the existing config-entry update listener handle host changes without a
  second reload from the manual or Zeroconf config flow, avoiding the API
  combination removed in Home Assistant 2026.12.
- Set the minimum Home Assistant compatibility target to 2026.10.2.
- Correct the documentation and issue-tracker URLs to the actual repository.
- Skip exact recently confirmed duplicate settings with an option to disable it;
  always send zero-power commands and add no rate limit or deadband.
- Raise Home Assistant errors after failed readback/retry; publish final command
  outcomes consistently and separate them from current device health.
- Restore and verify the original AC mode during optional recovery, including
  cancellation and ambiguous timeouts. Keep recovery off by default and restrict
  it to nonzero output requests in discharge mode with reverse-flow prohibition.
- Add separate counters for API attempts, skipped duplicates, retries and recovery.
- Add German/English entity names, flash-persistence explanations, reported UI
  power bounds and 1 W input/output steps while preserving unique IDs and options.
- Add 68 isolated regression tests for device identity, setup order, config-flow
  reload behavior and API compatibility, including an anonymized real report and
  the actual aiohttp response decoder. No device requests are sent by these tests.

## 1.2.0

- Dynamische Begrenzung von `outputLimit` und `inputLimit` anhand aktuell gemeldeter Gerätelimits.
- Optionale Validierung jedes Schreibbefehls mit einmaliger Wiederholung.
- Konfigurierbare, einmalige Recovery mit Sperrzeit; standardmäßig deaktiviert.
- Neue Diagnoseentitäten für Status, Gesamtzustand und letzten Steuerbefehl.
- Erkennung des beobachtbaren Zustands „100 % erreicht, keine Entladung“.
- Rohwerte unbekannter oder nicht eindeutig dokumentierter Gerätezustände werden unverändert ausgegeben.
- Ereignisverlauf und Befehlsdetails als Diagnoseattribute.


All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## 1.1.2

- Fixed the `DeviceInfo` import for current Home Assistant versions.
- `DeviceInfo` is now imported from `homeassistant.helpers.device_registry`.

## [Unreleased]

## [1.1.1] - 2026-07-23

### Fixed

- Scale `socSet` and `minSoc` from API tenths of a percent for display.
- Convert percentage values back to API tenths when writing.

### Added

- Initial public HACS repository preparation.
- HACS and hassfest validation workflows.
- Ruff linting and formatting workflow.
- Integration brand icon.
- MIT license and release documentation.

## [1.1.0] - 2026-07-23

### Added

- Local polling integration for SolarFlow 2400 devices.
- Config flow with manual and Zeroconf discovery.
- Sensors, binary sensors, numbers, selects, and switches.
- Dynamic discovery of battery packs.

### Fixed

- Duplicate `gridOffPower` sensor definition.
- API response cleanup and invalid JSON handling.
- Serialized write operations and coordinator error handling.

[Unreleased]: https://github.com/lenni76/SolarFlow2400-API/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/lenni76/SolarFlow2400-API/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/lenni76/SolarFlow2400-API/releases/tag/v1.1.0
