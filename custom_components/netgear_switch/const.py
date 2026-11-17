"""Constants for NETGEAR Switch."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "netgear_switch"
NAME: Final = "NETGEAR Switch"

SCAN_INTERVAL: Final = timedelta(seconds=30)

# On a port's link entity, for other integrations and apps (such as the Network app)
ATTR_PORT: Final = "port"
ATTR_SWITCH_HOST: Final = "switch_host"
ATTR_SPEED: Final = "speed_mbps"
