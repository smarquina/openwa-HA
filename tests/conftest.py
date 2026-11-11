"""Enable local custom integrations in Home Assistant tests."""

import pytest


@pytest.fixture(autouse=True)
def _enable_custom_integration(enable_custom_integrations):
    """Load the integration from this repository."""
