# Stagg EKG+ Kettle Technical Specifications

## Temperature Specifications

### Physical Limits
- **Minimum Temperature:** 40°C (104°F)
- **Maximum Temperature:** 100°C (212°F)
- **Temperature Step:** 0.5°C per dial click (value changes by 1)

### Internal Format
The kettle uses a "2C" format internally:
- Value = Temperature in Celsius × 2
- Examples:
  - 40°C = value 80
  - 50°C = value 100
  - 85°C = value 170
  - 100°C = value 200

### Setting Temperature

#### Method 1: Dial Rotation (ACTIVE TARGET)
```bash
# Increase temperature
curl 'http://192.168.1.100/cli?cmd=right'

# Decrease temperature
curl 'http://192.168.1.100/cli?cmd=left'
```
- ✅ Changes active/running target immediately
- ✅ Updates display in real-time
- ✅ Works while heating
- ❌ Requires multiple calls to reach specific temp
- ❌ Need to calculate steps (each step = 0.5°C)

#### Method 2: setsetting (SAVED PREFERENCE ONLY)
```bash
# Set saved preference to 85°C
curl -G --data-urlencode "cmd=setsetting settempr 185" 'http://192.168.1.100/cli'
```
- Format: Fahrenheit value directly
- Example: For 85°C, use 185 (Fahrenheit equivalent)
- ⚠️ **Only saves preference - does NOT change active target**
- ⚠️ Takes effect on next power cycle/button press
- ❌ Cannot be used to change temperature while heating

**Recommendation:** Use dial rotation for programmatic temperature control.

## CLI Command Reference

### State Commands
| Command | Response | Description |
|---------|----------|-------------|
| `state` | Full state | Returns mode, temps, settings |
| `temp` | Temp stats | Min/max/average readings |
| `prtsettings` | All settings | Saved preferences |

### Control Commands
| Command | Effect | Notes |
|---------|--------|-------|
| `1` | Button 1 press | Wake/Start/Menu navigation |
| `2` | Button 2 press | Cancel/Hold/Menu navigation |
| `left` | Dial left | Decrease temp by ~0.5°C |
| `right` | Dial right | Increase temp by ~0.5°C |
| `heaton` | GPIO heat on | Direct element control |
| `heatoff` | GPIO heat off | Direct element control |
| `warmon` | Warming on | Keep warm mode |
| `warmoff` | Warming off | Disable keep warm |

### Unit Commands
| Command | Effect |
|---------|--------|
| `setunitsf` | Display Fahrenheit (units=0) |
| `setunitsc` | Display Celsius (units=1) |

## State Response Format

### Key Fields
```
mode=S_Off|S_Standby|S_Heat|S_HeatOff
scrname=wnd|menu - hold.png|menu - schedule.png
value=<dial_value_2C>
tempr=<current_water_temp_C>
temprT=<target_temp_C>  (set via dial rotation)
temprB=<max_temp_C>  (appears to be maximum, typically 100°C)
temps=<set_temp_2C>  (target temp in "2C" format, matches value)
units=0|1 (0=F, 1=C)
ketl= ho <heating> wd <warming> nw 0 ipb 0 bf 0 tr 0
```

### Mode States
- `S_Off` - Powered off, screen dark
- `S_Standby` - On but not heating
- `S_StartupToTempr` - Starting heating cycle
- `S_Heat` - Actively heating
- `S_HeatOff` - Heat cycle complete
- `S_Heat+menu` - Heating with menu showing

### Kettle Flags
- `ho` - Heating On (0/1)
- `wd` - Warming Duty (0/1)
- Other flags (nw, ipb, bf, tr) - Purpose unknown

## Firmware Information

**Version:** 1.1.76SSP CLI
**Build Date:** May 9, 2024
**Build Time:** 13:53:38
**Platform:** ESP32 (Espressif)

**Partitions:**
- Factory: 1.1.14SSB (0x10000, 2MB)
- OTA_0: 1.1.75SSP (0x210000, 2MB)
- OTA_1: 1.1.76SSP (0x410000, 2MB) ← Active

## Network

**Protocol:** HTTP
**Port:** 80
**Endpoint:** `/cli?cmd=<command>`
**Response:** Plain text with structured data

## Safety Features

### Water Detection
- The kettle has no water-level sensor, and the `ketl=` flags don't change
  with the water level.
- `tempr` alone says nothing about the water level: cold water reads low
  whether the kettle is full or nearly empty.
- While heating, the rise rate does track the amount of water: about
  0.5 °C/s full and 1.5 °C/s at ~0.2 L on a Stagg EKG Pro. The integration's
  rapid-rise detection (`rise.py`) is based on this.

### Temperature Limits Enforcement
- Dial physically limited to 40-100°C range
- Cannot set outside this range via rotation
- `setsetting` accepts any value but kettle will cap at 100°C

## Power Management

### Physical Buttons
**IMPORTANT:** The kettle has TWO different buttons:
- **Button 1** (CLI: `cmd=1`): Separate button on base - opens startup menu when pressed from S_Off
- **Button 2** (CLI: `cmd=2`): The dial itself is pressable - wakes and starts heating directly

### Wake Sequence
**Recommended (Simple):**
1. Press button 2 (dial button) → Wakes from S_Off, shows Fellow logo, goes to main screen and starts heating

**Alternative (Button 1 - Opens Menu):**
1. Press button 1 → Wakes and opens startup menu (schedule, etc.)
2. Navigate menu with dial rotation
3. Press button 1 to select and exit

### Heating Sequence
1. Press button 2 (dial button) → Mode changes: `S_Off` → `S_Heat`
2. Heating element activates (ho=1)
3. Temperature increases toward target
4. When reached: `S_Heat` → `S_HeatOff`

### Stop Sequence
1. Press button 2 (dial button) → Cancel heating
2. Or use `heatoff` command → Heating element deactivates (ho=0)
3. Mode changes to `S_Standby` or `S_Off`

## Programming Notes

### Temperature Conversion
```python
# Celsius to "2C" value
value_2c = int(temp_celsius * 2)

# "2C" value to Celsius
temp_celsius = value_2c / 2

# Celsius to Fahrenheit
temp_f = temp_c * 9/5 + 32

# Fahrenheit to Celsius
temp_c = (temp_f - 32) * 5/9
```

### Dial Steps Calculation
```python
# Each dial step is 0.5°C (value increases by 1 in "2C" format)
# Verified: 90 steps = 45°C change (from 40°C to 85°C)
temp_diff = target_celsius - current_celsius
steps = int(round(temp_diff * 2))  # or temp_diff / 0.5

if steps > 0:
    for _ in range(steps):
        rotate_right()
elif steps < 0:
    for _ in range(abs(steps)):
        rotate_left()
```

### Setting Exact Temperature
```python
import requests
import re
import time

# Get current dial value
response = requests.get('http://192.168.1.100/cli?cmd=state')
current_value = int(re.search(r'value=(\d+)', response.text).group(1))

# Calculate target value (in "2C" format)
target_celsius = 85
target_value = int(target_celsius * 2)  # 85°C = 170

# Calculate steps needed
steps = target_value - current_value

# Rotate to target
if steps > 0:
    for _ in range(steps):
        requests.get('http://192.168.1.100/cli?cmd=right')
        time.sleep(0.1)
elif steps < 0:
    for _ in range(abs(steps)):
        requests.get('http://192.168.1.100/cli?cmd=left')
        time.sleep(0.1)

# Verify final value
response = requests.get('http://192.168.1.100/cli?cmd=state')
final_value = int(re.search(r'value=(\d+)', response.text).group(1))
print(f"Set to {final_value/2}°C")
```

## Tested Limits

- ✅ Minimum settable: 40°C (80 value)
- ✅ Maximum settable: 100°C (200 value)
- ✅ Temperature step: 0.5°C per click
- ✅ Dial wraps: No (hits limit and stops)
- ✅ Temperature units: Sync with display
- ✅ Multiple concurrent commands: Works with delays
- ✅ Command timeout: ~10 seconds
- ✅ Polling frequency: 30 seconds recommended

## Known Issues

1. **setsetting doesn't update active target**
   - Only updates saved preference
   - Use dial rotation for live changes

2. **Menu navigation can interfere**
   - Kettle can get stuck in menus
   - Always exit to main screen before control

3. **Temperature sensor lag**
   - Reading may lag actual water temp by few seconds
   - Allow time for stabilization

4. **No native "set to X°C" command**
   - Must use dial rotation in loop
   - Requires feedback to verify reached target
