# Stagg EKG+ Python API - Usage Examples

Complete examples for using the standalone Python API in this directory
(`stagg_ekg_api.py`). Run scripts from inside `examples/`, or add this
directory to `PYTHONPATH`, so `from stagg_ekg_api import StaggEKGClient`
resolves.

---

## Quick Start

```python
from stagg_ekg_api import StaggEKGClient

# Initialize
kettle = StaggEKGClient(host="192.168.1.100")

# Get current state
state = kettle.get_state()
print(f"Current: {state.current_temp_c}°C, Target: {state.set_temp_c}°C")
```

---

## Common Use Cases

### 1. Heat Water to Specific Temperature

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

# One-liner: Set temp and start heating
print(kettle.heat_to_temperature(95))
# Output: "Increased temperature by 10.0°C to 95°C and started heating"

# Or do it step-by-step:
kettle.set_temperature(95)  # Set target
kettle.start_heating()       # Start heating
```

### 2. Monitor Until Water is Ready

```python
import time
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

# Start heating to 85°C
kettle.heat_to_temperature(85)

# Wait until ready
print("Heating water...")
while not kettle.is_at_target(tolerance=2.0):
    state = kettle.get_state()
    print(f"Current: {state.current_temp_c:.1f}°C / Target: {state.set_temp_c}°C")
    time.sleep(5)

print("Water is ready!")
kettle.buzzer_sos()  # Alert!
```

### 3. Morning Coffee Routine

```python
from stagg_ekg_api import StaggEKGClient
import time

kettle = StaggEKGClient(host="192.168.1.100")

# Heat water for coffee
print("☕ Heating water for coffee (95°C)...")
kettle.heat_to_temperature(95)

# Monitor progress
while not kettle.is_at_target():
    state = kettle.get_state()
    progress = (state.current_temp_c / state.set_temp_c) * 100
    print(f"   {state.current_temp_c:.1f}°C ({progress:.0f}%)")
    time.sleep(10)

print("✓ Coffee water ready!")
kettle.buzzer_sos()
```

### 4. Tea Temperature Presets

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

# Tea temperature guide
TEMPS = {
    "green": 75,
    "white": 80,
    "oolong": 85,
    "black": 95,
    "herbal": 100
}

# Heat for green tea
tea_type = "green"
temp = TEMPS[tea_type]

print(f"Heating water for {tea_type} tea ({temp}°C)...")
kettle.heat_to_temperature(temp)
```

### 5. Auto-Shutdown After Heating

```python
from stagg_ekg_api import StaggEKGClient
import time

kettle = StaggEKGClient(host="192.168.1.100")

# Heat water
kettle.heat_to_temperature(85)

# Wait until at target
while not kettle.is_at_target():
    time.sleep(5)

print("Target reached!")

# Keep warm for 5 minutes
print("Keeping warm for 5 minutes...")
time.sleep(300)

# Auto shutdown
print("Shutting down...")
kettle.stop_heating()
```

### 6. Check Status

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

state = kettle.get_state()

print(f"""
Kettle Status:
  Mode: {state.mode}
  Current Temperature: {state.current_temp_c}°C
  Target Temperature: {state.set_temp_c}°C
  Heating: {'Yes' if state.heating else 'No'}
  Warming: {'Yes' if state.warming else 'No'}
  Display Unit: {'°C' if state.units == 1 else '°F'}
  Clock: {state.clock}
""")
```

### 7. Change Temperature Units

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

# Switch to Fahrenheit
kettle.set_units_fahrenheit()
print("Display now shows Fahrenheit")

# Switch to Celsius
kettle.set_units_celsius()
print("Display now shows Celsius")
```

### 8. Manual Temperature Adjustment

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

# Increase by 5°C (10 steps × 0.5°C)
for _ in range(10):
    kettle.rotate_dial_right()

# Decrease by 2.5°C (5 steps × 0.5°C)
for _ in range(5):
    kettle.rotate_dial_left()

# Check new target
state = kettle.get_state()
print(f"Target is now: {state.set_temp_c}°C")
```

### 9. Direct Heating Element Control

```python
from stagg_ekg_api import StaggEKGClient
import time

kettle = StaggEKGClient(host="192.168.1.100")

# Turn heating element on directly
kettle.heat_on()
print("Heating element ON")

# Heat for 30 seconds
time.sleep(30)

# Turn off
kettle.heat_off()
print("Heating element OFF")
```

### 10. Custom Automation Script

```python
#!/usr/bin/env python3
"""
Smart Kettle Scheduler
Heats water at specific times
"""

from stagg_ekg_api import StaggEKGClient
import schedule
import time

kettle = StaggEKGClient(host="192.168.1.100")

def morning_coffee():
    """Heat water for morning coffee"""
    print("☕ Morning coffee time!")
    kettle.heat_to_temperature(95)
    print("✓ Heating started")

def afternoon_tea():
    """Heat water for afternoon tea"""
    print("🍵 Afternoon tea time!")
    kettle.heat_to_temperature(85)
    print("✓ Heating started")

# Schedule tasks
schedule.every().day.at("07:00").do(morning_coffee)
schedule.every().day.at("15:00").do(afternoon_tea)

print("Smart Kettle Scheduler running...")
print("  7:00 AM - Coffee (95°C)")
print("  3:00 PM - Tea (85°C)")

while True:
    schedule.run_pending()
    time.sleep(60)
```

---

## Advanced Features

### Empty-Kettle Protection

The kettle has no water-level sensor, and the temperature on its own says
nothing about how much water is in it. While it heats, though, a nearly empty
kettle warms much faster than a full one. `watch_heat_cycle()` in
`custom_components/fellow/rise.py` watches one boil and turns the kettle off
if the temperature climbs too fast. `rise.py` has no Home Assistant imports,
so add its folder to your path too:
`PYTHONPATH=.:../custom_components/fellow python boil.py`.

```python
from rise import watch_heat_cycle
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

kettle.heat_to_temperature(95)
result = watch_heat_cycle(kettle.get_state, stop=kettle.stop_heating)

if result.outcome in ("stopped", "stop_failed"):
    print(f"⚠️  Rose at {result.triggered_rate:.1f} °C/s: the kettle may be empty")
    if result.outcome == "stop_failed":
        print("   It did not turn off. Check it now!")
```

### Temperature Monitoring Loop

```python
from stagg_ekg_api import StaggEKGClient
import time

kettle = StaggEKGClient(host="192.168.1.100")

print("Monitoring kettle temperature (Ctrl+C to stop)...")

try:
    while True:
        state = kettle.get_state()

        status = "Heating" if state.heating else "Off"

        print(f"{state.current_temp_c:.1f}°C → {state.set_temp_c}°C | {status} | {state.mode}")

        time.sleep(5)
except KeyboardInterrupt:
    print("\nMonitoring stopped")
```

### Get All Information

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

# State
state = kettle.get_state()
print("State:", state)

# Settings
settings = kettle.get_settings()
print("Settings:", settings)

# Firmware
firmware = kettle.get_firmware_info()
print("Firmware:", firmware)

# WiFi
wifi = kettle.get_wifi_info()
print("WiFi:", wifi)
```

---

## Error Handling

```python
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

try:
    # Try to set invalid temperature
    kettle.set_temperature(150)  # Too high!
except ValueError as e:
    print(f"Error: {e}")
    # Output: "Error: Temperature must be between 40°C and 100°C"

try:
    # Try to connect to wrong IP
    bad_kettle = StaggEKGClient(host="192.168.1.999")
    bad_kettle.get_state()
except Exception as e:
    print(f"Connection error: {e}")
```

---

## API Reference Summary

### Main Methods

| Method | Description | Example |
|--------|-------------|---------|
| `get_state()` | Get current kettle state | `state = kettle.get_state()` |
| `start_heating()` | Wake and start heating | `kettle.start_heating()` |
| `stop_heating()` | Stop and turn off | `kettle.stop_heating()` |
| `power_on()` | Wake screen (standby) | `kettle.power_on()` |
| `set_temperature(°C)` | Set target temperature | `kettle.set_temperature(85)` |
| `heat_to_temperature(°C)` | Set temp and start heating | `kettle.heat_to_temperature(95)` |
| `is_at_target()` | Check if at target temp | `if kettle.is_at_target():` |

### Temperature Control

| Method | Description |
|--------|-------------|
| `set_temperature(temp)` | Set target (40-100°C) |
| `rotate_dial_left()` | Decrease 0.5°C |
| `rotate_dial_right()` | Increase 0.5°C |
| `set_units_celsius()` | Display in °C |
| `set_units_fahrenheit()` | Display in °F |

### Direct Controls

| Method | Description |
|--------|-------------|
| `heat_on()` | Heating element ON |
| `heat_off()` | Heating element OFF |
| `warm_on()` | Warming mode ON |
| `warm_off()` | Warming mode OFF |
| `press_button_1()` | Press base button |
| `press_button_2()` | Press dial button |

### State Properties

| Property | Type | Description |
|----------|------|-------------|
| `state.current_temp_c` | float | Current water temp (°C) |
| `state.set_temp_c` | float | Target temp (°C) |
| `state.mode` | str | Operating mode |
| `state.heating` | bool | Heating element status |
| `state.warming` | bool | Warming mode status |
| `state.units` | int | Display units (0=°F, 1=°C) |
| `state.clock` | str | Kettle clock time |

---

## Tips

1. **Temperature Range**: Only 40-100°C is valid
2. **Step Size**: Each dial rotation = 0.5°C
3. **Button 2**: The dial button (wakes and starts heating)
4. **Water Level**: There's no water sensor. Use `watch_heat_cycle()` (see Empty-Kettle Protection) to catch a nearly empty kettle while it heats
5. **Delays**: Add small delays (0.1s) between dial rotations for reliability

---

Enjoy your automated kettle! ☕
