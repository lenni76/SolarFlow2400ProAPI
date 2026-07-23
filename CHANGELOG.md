# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/lenni76/SolarFlow2400-API/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/lenni76/SolarFlow2400-API/releases/tag/v1.1.0
