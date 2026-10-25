"""Constants for the Fellow integration."""

DOMAIN = "fellow"

# Configuration
CONF_TEMPERATURE_UNIT = "temperature_unit"
CONF_TEMP_SET_METHOD = "temp_set_method"

# Temperature units (matches kettle's internal values)
UNIT_CELSIUS = "celsius"
UNIT_FAHRENHEIT = "fahrenheit"

# Temperature-setting methods
# - direct: single `setsetting settempr <F>` firmware command (fast, preferred)
# - dial:   emulate physical dial via left/right step commands (compatible fallback)
TEMP_METHOD_DIRECT = "direct"
TEMP_METHOD_DIAL = "dial"

# Temperature limits (verified from kettle hardware)
MIN_TEMP_C = 40  # Minimum kettle can be set to
MAX_TEMP_C = 100  # Maximum (boiling point)
MIN_TEMP_F = 104  # Minimum in Fahrenheit
MAX_TEMP_F = 212  # Maximum in Fahrenheit (boiling point)

# Internal value format ("2C" - 2x Celsius)
MIN_VALUE_2C = 80   # 40°C * 2
MAX_VALUE_2C = 200  # 100°C * 2

# Rapid temperature-rise detection (see rise.py)
CONF_RAPID_RISE_AUTO_STOP = "rapid_rise_auto_stop"
CONF_RAPID_RISE_THRESHOLD = "rapid_rise_threshold"
DEFAULT_RAPID_RISE_AUTO_STOP = True
DEFAULT_RAPID_RISE_THRESHOLD = 3.0  # °C/s
MIN_RAPID_RISE_THRESHOLD = 1.0
MAX_RAPID_RISE_THRESHOLD = 10.0
EVENT_RAPID_RISE = f"{DOMAIN}_rapid_rise"
EVENT_RAPID_RISE_STOP_FAILED = f"{DOMAIN}_rapid_rise_stop_failed"
