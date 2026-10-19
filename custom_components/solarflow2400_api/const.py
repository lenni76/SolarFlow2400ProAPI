"""Constants for the SolarFlow2400-API integration.

All property names, units, access flags (RO/RW), value ranges and enum
mappings in this file are taken *verbatim* from the official Zendure zenSDK
documentation:

  - Repo:       https://github.com/Zendure/zenSDK
  - Properties: https://github.com/Zendure/zenSDK/blob/main/docs/en_properties.md

Nothing here is guessed. Where the Zendure documentation does not specify a
value (e.g. an upper bound for a power limit), this is called out explicitly
in comments and the value is only used as a UI slider bound - the device
itself enforces the real limits.
"""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "solarflow2400_api"
MANUFACTURER = "Zendure"

# Local HTTP API (zenSDK README -> "Device Communication (HTTP RESTful API)")
REPORT_PATH = "/properties/report"
WRITE_PATH = "/properties/write"

# Config / options keys
CONF_HOST = "host"
CONF_SERIAL = "serial"
CONF_MODEL = "model"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_COMMAND_VALIDATION = "command_validation"
CONF_AUTO_RECOVERY = "auto_recovery"
CONF_VALIDATION_DELAY = "validation_delay"
CONF_RECOVERY_COOLDOWN = "recovery_cooldown"
CONF_SKIP_UNCHANGED = "skip_unchanged"

# zenSDK does not mandate a poll rate. The reference Symcon script used 10 s.
# We default to 30 s to be gentle on the device and make it user-configurable.
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_COMMAND_VALIDATION = True
DEFAULT_AUTO_RECOVERY = False
DEFAULT_VALIDATION_DELAY = 2
DEFAULT_RECOVERY_COOLDOWN = 300
DEFAULT_SKIP_UNCHANGED = True
# Local cache policy, not a manufacturer API limit. Never throttle changed values.
DUPLICATE_MAX_AGE = 5
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600

# HTTP timeout for a single request.
REQUEST_TIMEOUT = 10

# Zeroconf service advertised by the device (zenSDK README -> mDNS section).
# Service name format: Zendure-<Model>-<Last12MAC>
ZEROCONF_TYPE = "_zendure._tcp.local."

MIN_UPDATE_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)
