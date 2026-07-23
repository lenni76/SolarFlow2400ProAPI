# Publishing checklist

## Before the first push

- Create the public GitHub repository as `lenni76/SolarFlow2400-API`.
- Set the repository description, for example:
  `Local Home Assistant integration for Zendure SolarFlow 2400 via the zenSDK API.`
- Add repository topics:
  `home-assistant`, `hacs`, `solarflow`, `zendure`, `solar-energy`, `battery-storage`.
- Confirm that the default branch is `main`.

## Before every release

- Update the version in `custom_components/solarflow2400_api/manifest.json`.
- Update `CHANGELOG.md` and move completed entries out of `Unreleased`.
- Run `ruff check .`.
- Run `ruff format --check .`.
- Push and verify that HACS, hassfest, and Ruff workflows pass.
- Create a GitHub release whose tag matches the manifest version, for example `v1.1.0`.
- Add release notes or use GitHub's generated release notes.
- Test installation or update through HACS.
