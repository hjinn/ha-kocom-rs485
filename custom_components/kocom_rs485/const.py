"""Constants for the Kocom RS485 integration."""

DOMAIN = "kocom_rs485"

CONF_ROOMS = "rooms"
DEFAULT_PORT = 8899
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60  # seconds, ADR-0015
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

# room sub id -> key for entity ids, unique ids, names and logs
ROOM_KEYS = {0: "livingroom", 1: "bedroom", 2: "room1", 3: "room2"}
