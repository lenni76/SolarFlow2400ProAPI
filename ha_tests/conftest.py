"""Run real Home Assistant fixtures separately from isolated module doubles."""

import pytest


@pytest.fixture(autouse=True)
def enable_local_integration(enable_custom_integrations):
    """Permit loading this repository's custom integration."""
