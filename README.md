# Fellow EKG Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: Unlicense](https://img.shields.io/badge/License-Unlicense-blue.svg)](http://unlicense.org/)

A complete Home Assistant custom integration for Fellow EKG electric kettles (Stagg EKG, Stagg EKG+, Stagg EKG Pro, and Corvo EKG) with temperature control, automation support, and real-time monitoring.

Works with all Fellow kettles that have the HTTP CLI interface.


## Features

✨ **Complete Control**
- Turn kettle on/off from Home Assistant
- Set target temperature (40-100°C / 104-212°F), with a separate, lower hold temperature
- Monitor current water temperature in real-time
- View operating mode and heating status

🌡️ **Temperature Management**
- Choose between Celsius or Fahrenheit
- Syncs with kettle's LCD display
- Precise 0.5°C temperature steps
- Automatic temperature validation

🔒 **Safety Features**
- Rapid temperature-rise detection (likely empty kettle), with optional auto-stop
- Automatic power management
- Temperature range limits
- Safe heating cycle control

🤖 **Home Assistant Integration**
- 8 entities for complete control
- Water heater entity for climate integration
- Binary sensors for status monitoring
- Switches for direct control
- Full automation support

📡 **Local Control**
- No cloud connection required
- Works entirely on local network
- Fast response times
- Standalone Python API included

## Entities

| Entity | Type | Purpose |
|--------|------|---------|
| `water_heater.fellow_kettle` | Water Heater | Main control interface |
| `sensor.fellow_current_temperature` | Sensor | Real-time water temperature |
| `sensor.fellow_target_temperature` | Sensor | "Native Target Temperature": the kettle's own target, read-only: the Heat Up Target during a boil, the Hold Target during a lowered hold (`role` attribute says which) |
| `number.fellow_heat_up_target` | Number | What a boil heats to (the water heater's target) |
| `number.fellow_hold_target` | Number | What the kettle holds at after a boil |
| `number.fellow_hold_delay` | Number (minutes) | Time at the Heat Up Target after a boil, to pour, before dropping to the Hold Target (default 2) |
| `sensor.fellow_hold_ends` | Sensor (timestamp) | When the current hold ends, shown as a countdown |
| `sensor.fellow_mode` | Sensor | Operating mode (Off, Heat, Standby) |
| `switch.fellow_heating` | Switch | Heating element control |
| `switch.fellow_warming` | Switch | "Warming / Holding": on while the kettle holds the water at temperature after a boil; turning it off ends the hold |
| `binary_sensor.fellow_power` | Binary Sensor | On while the kettle answers Home Assistant; off after two failed polls in a row (about 15–30 s) |
| `binary_sensor.fellow_on_base` | Binary Sensor | "On base" while the kettle sits on its base, "Off base" when lifted |
| `select.fellow_hold_duration` | Select | How long the kettle holds temperature after a boil: 15, 30, 45 or 60 min |
| `button.fellow_emergency_stop` | Button | Kill switch: turns the heater and warmer off, whatever mode the kettle reports |
| `sensor.fellow_raw_status` | Sensor (diagnostic) | Mode and unrounded temperature from the latest poll; full `state` response in the `raw` attribute |
| `binary_sensor.fellow_rapid_temperature_rise` | Binary Sensor | Temperature climbing fast enough to suggest an empty kettle |

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed
2. Add this repository as a custom repository:
   - Go to HACS → Integrations
   - Click the three dots in the top right
   - Select "Custom repositories"
   - Add repository URL: `https://github.com/rderewianko/fellow-ekg`
   - Category: Integration
3. Click "Install" on the Stagg EKG+ integration
4. Restart Home Assistant
5. Add the integration:
   - Go to Settings → Devices & Services → Add Integration
   - Search for "Fellow Stagg EKG+"
   - Enter your kettle's IP address
   - Choose temperature unit (Celsius or Fahrenheit)

### Manual Installation

1. Download the `custom_components/fellow` folder
2. Copy it to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant
4. Add the integration via Settings → Devices & Services

## Configuration

### Finding Your Kettle's IP Address

The kettle connects to your WiFi network. Find its IP address:

1. Check your router's DHCP client list
2. Look for a device named:
   - "Stagg EKG" or "Fellow"
   - "espressif" (the ESP32 manufacturer)
   - May include part of the MAC address (e.g., "espressif 16:b0")
3. Note the IP address (e.g., `192.168.1.100`)

**Tip:** Set a static IP or DHCP reservation for your kettle to prevent the address from changing.

### Setup

1. Go to Settings → Devices & Services → Add Integration
2. Search for "Fellow Stagg EKG+"
3. Enter configuration:
   - **Host:** Your kettle's IP address
   - **Temperature Unit:** Choose Celsius or Fahrenheit
4. Click Submit

The integration will sync the temperature unit with your kettle's LCD display.

### Changing Temperature Units

1. Go to Settings → Devices & Services
2. Find "Stagg EKG+"
3. Click "CONFIGURE"
4. Select your preferred unit
5. Submit - the kettle display updates immediately

### Heat Up Target and Hold Target

The kettle has a single target temperature: it heats to it, then holds there.
To boil hot but keep the water at a gentler temperature, set **Hold Target**
below **Heat Up Target**.

When a boil finishes and the kettle starts holding, the integration waits
**Hold Delay** minutes (default 2), so there's time to pour at the full
temperature, then lowers the kettle's target to the Hold Target. Lifting the
kettle to pour during the delay doesn't restart it; set it to 0 to drop
straight away. The Hold Target's `drops_at` attribute shows when the drop is
due. The water then cools to it, and the kettle
holds it there; on a Stagg EKG Pro, a hold lowered to 85 °C stayed within
84.2–85.7 °C. When the hold runs out or the kettle is turned off, the
integration puts the Heat Up Target back, so the next boil, even one started
with the dial, heats to the Heat Up Target again. Lifting the kettle to pour
mid-hold keeps the Hold Target. Starting a boil from Home Assistant during a
lowered hold boils to the Heat Up Target.

Changing Heat Up Target while the kettle is holding only applies to future
boils: the kettle keeps holding where it is, and the new target is set when
the hold ends. During a boil it applies to that boil, like turning the dial.

Outside a lowered hold, Heat Up Target follows the kettle's own target, so
turning the dial still works. A Hold Target at or above the Heat Up Target
means the kettle holds at the Heat Up Target, as before. Both are kept by
Home Assistant, so lowering the hold only works while it's running.

The kettle's Hold Duration counts from the boil, so the delay and the cooling
come out of it. With a 2-minute delay, cooling from 100 °C to 85 °C takes
about another 8 minutes, so a 15-minute Hold Duration leaves only a few
minutes at 85; 30 or 45 suits a lower Hold Target better.

In automations, `water_heater.set_temperature` sets the Heat Up Target, as it
always set the kettle's target, so existing automations keep working. Set the
Hold Target with `number.set_value`; the water heater also shows it as a
`hold_temperature` attribute.

```yaml
# Boil to 100°C, then hold at 85°C
- service: water_heater.set_temperature
  target:
    entity_id: water_heater.fellow_kettle
  data:
    temperature: 100
- service: number.set_value
  target:
    entity_id: number.fellow_hold_target
  data:
    value: 85
- service: water_heater.turn_on
  target:
    entity_id: water_heater.fellow_kettle
```

If you lower the Heat Up Target below the water's current temperature
mid-boil, the kettle stays in its heating mode while the water cools, and
starts holding once the water reaches the target. The Mode sensor shows
**Cooling to target** meanwhile, and **Cooling to hold target** while the
water cools to a lower Hold Target, so neither looks like heating.

### Hold Ends

`sensor.fellow_hold_ends` shows when the current hold ends, as a countdown.
The kettle restarts its Hold Duration every time it settles back into its
hold (after a boil or reheat, after you set it down from pouring, or when you
close a menu on its display), and the countdown follows that, to within one
poll. It's empty when the kettle isn't holding. If Home Assistant restarts
mid-hold, the countdown starts from its first poll, so it can run a little
late for that hold.

The `ends_at` attribute has the end as a clock time (e.g. `23:06`). On a
dashboard, an entities card can show the time instead of the countdown:

```yaml
type: entities
entities:
  - entity: sensor.fellow_hold_ends
    format: time  # "11:06 PM" instead of "in 12 minutes"
```

### Hold Duration

`select.fellow_hold_duration` sets how long the kettle keeps the water at
temperature after a boil, with the same choices as the kettle's hold menu:
15, 30, 45 or 60 minutes. The kettle's display shows the change straight
away. A change made from the kettle's menu shows up in Home Assistant within
about a minute.

### Warming / Holding

The kettle has no separate warming mode: once a boil reaches the target, it
holds the water there for the Hold Duration. The **Warming / Holding** switch
shows that hold.

- It turns **on by itself** when a boil finishes and the kettle starts
  holding.
- Turning it **off** ends the hold early, and the kettle turns off.
- Turning it **on** yourself is refused: a hold only comes from a boil, so it
  never runs longer than the Hold Duration. To keep water warm again, start a
  new boil with Heating.

The water heater entity's warm mode follows the same rule.

### Emergency Stop

`button.fellow_emergency_stop` turns everything off. It sends `ss S_Off`,
then switches the heating and warming elements off directly, and repeats up
to three times until the kettle reports Off. Unlike the Heating switch, it
never skips a step because the kettle already says it is off, since the
heater has been seen running while the kettle reported Off. The button stays
pressable even when polling is failing.

Each press reports what happened in a notification (replaced by the next
press) and in the button's `last_result` attribute, for example:

- "Kettle was heating (S_Heat). Stop sent; it now reports Off."
- "Kettle already reported Off. Stop sent anyway, since the heater has been
  seen running while the kettle reports Off."

If the kettle still reports heating after three tries, the notification says
so and the press fails with an error. Like every Home Assistant button, its
state is the time it was last pressed, which is why it shows "2 minutes ago".

### Raw Status

`sensor.fellow_raw_status` is a diagnostic sensor that shows what the kettle
returned on the latest poll: its state is the mode and the unrounded
temperature (for example `S_Heat 74.280831 C`), and the `raw` attribute holds
the full `state` response. `raw` isn't saved to history, so use **Current
Temperature** to graph the temperature over time.

### Rapid Temperature Rise Detection

The kettle has no water-level sensor, but while it heats, the rate at which
the temperature climbs tracks how much water is in it: the same heater warms
a small amount of water, or an empty kettle, much faster than a full one.
Measured on a Stagg EKG Pro (1200 W):

| Fill | Average rise | Peak (10 s average) |
|------|--------------|---------------------|
| Nearly full (~0.9 L) | ~0.44 °C/s | ~0.5 °C/s |
| Low (~0.2 L) | ~1.25 °C/s | ~1.5 °C/s |

During a heat cycle the integration averages the temperature rise over a
10-second window, ignoring the first 20 seconds, when the reading hasn't
moved yet. If the rate goes above the threshold (default **3.0 °C/s**):

- `binary_sensor.fellow_rapid_temperature_rise` turns on. It stays on until
  the next heat cycle starts or the kettle is lifted off the base. Attributes:
  `rise_rate` (live 10 s average, empty when not heating), `triggered_rate`
  (the rate that tripped the alert), `threshold`, `auto_stop` and
  `stop_status` (`pending`, `stopped` or `failed`; empty if auto-stop is off).
- A `fellow_rapid_rise` event fires with `rate`, `threshold` and `auto_stop`.
- If **Stop heating on rapid temperature rise** is enabled (the default), the
  kettle is turned off. The kettle sometimes ignores a stop command or stops
  answering for a few seconds, so the integration keeps retrying on each poll
  until the kettle reports Off. If it is still on after 10 attempts or 60
  seconds, it gives up, fires a `fellow_rapid_rise_stop_failed` event (`rate`,
  `attempts`) and shows a persistent notification.

Detection works however the boil is started: from the Heating switch or
water heater entity, from an automation, or with the buttons on the kettle
itself. It runs on every poll, so no automation is needed, and neither is
auto-stop. It only works while Home Assistant is running. If the integration
reloads mid-boil (for example after saving these options), detection starts
again with a new 20-second grace period.

Both settings are under Settings → Devices & Services → Fellow → Configure.
The threshold can be set from 1.0 to 10.0 °C/s.

This is a heuristic, not a water sensor. The default comes from one kettle
at two fill levels; an empty kettle was not measured. The kettle's own
boil-dry protection is still the real safeguard.

The automation below is optional: it only sends a phone notification. It is
most useful with auto-stop turned off, when the alert would otherwise only
show up on the sensor:

```yaml
automation:
  - alias: "Kettle may be empty"
    trigger:
      - platform: event
        event_type: fellow_rapid_rise
    action:
      - service: notify.mobile_app_phone
        data:
          message: >
            Kettle temperature rising at {{ trigger.event.data.rate }} °C/s.
            Is there water in it?
```

## Usage

### Basic Control

```yaml
# Heat water to 95°C
service: water_heater.turn_on
target:
  entity_id: water_heater.fellow_kettle
data:
  temperature: 95
```

### Automations

**Morning Coffee**
```yaml
automation:
  - alias: "Morning Coffee"
    trigger:
      platform: time
      at: "07:00:00"
    action:
      - service: water_heater.set_temperature
        target:
          entity_id: water_heater.fellow_kettle
        data:
          temperature: 95
      - service: water_heater.turn_on
        target:
          entity_id: water_heater.fellow_kettle
```

**Water Ready Notification**
```yaml
automation:
  - alias: "Water Ready Notification"
    trigger:
      - platform: template
        value_template: >
          {{ states('sensor.fellow_current_temperature')|float >=
             states.water_heater.fellow_kettle.attributes.temperature|float - 2 }}
    condition:
      - condition: state
        entity_id: water_heater.fellow_kettle
        attribute: current_operation
        state: "heat"
    action:
      - service: notify.mobile_app
        data:
          message: "Kettle water is ready!"
          title: "☕ Coffee Time"
```

**Tea Temperature Presets**
```yaml
script:
  heat_green_tea:
    alias: "Heat for Green Tea"
    sequence:
      - service: water_heater.set_temperature
        target:
          entity_id: water_heater.fellow_kettle
        data:
          temperature: 75
      - service: water_heater.turn_on
        target:
          entity_id: water_heater.fellow_kettle

  heat_black_tea:
    alias: "Heat for Black Tea"
    sequence:
      - service: water_heater.set_temperature
        target:
          entity_id: water_heater.fellow_kettle
        data:
          temperature: 95
      - service: water_heater.turn_on
        target:
          entity_id: water_heater.fellow_kettle
```

### Dashboard Card

```yaml
type: thermostat
entity: water_heater.fellow_kettle
name: Coffee Kettle
```

A Markdown card next to **Native Target Temperature** explains it without a
click. The note is also in the sensor's `note` attribute, but Home Assistant
only shows attributes in a collapsed section of the entity dialog.

```yaml
type: markdown
content: >
  **Native Target Temperature** is the kettle's own setting. The
  integration sets it to Heat Up Target for boils and lowers it to
  Hold Target while holding. Change those two instead.
```

## Standalone Python API

The repository includes a standalone Python API in [`examples/stagg_ekg_api.py`](examples/stagg_ekg_api.py) for use outside Home Assistant.

### Quick Start

This boils water only after you confirm the kettle has water in it.
`watch_heat_cycle()` then blocks until the boil ends. If it sees a
temperature rise too fast for a kettle with water in it (see
[Rapid Temperature Rise Detection](#rapid-temperature-rise-detection)), it
turns the kettle off, retrying until the kettle reports Off. `rise.py` has no
Home Assistant imports, so run the script from the repository root with both
folders on your path: `PYTHONPATH=examples:custom_components/fellow python boil.py`.

```python
from rise import watch_heat_cycle
from stagg_ekg_api import StaggEKGClient

kettle = StaggEKGClient(host="192.168.1.100")

if input("Did you add water to the kettle? [y/N] ").strip().lower() != "y":
    raise SystemExit("Not heating. Fill the kettle and run this again.")

kettle.heat_to_temperature(95)

result = watch_heat_cycle(
    kettle.get_state,
    stop=kettle.stop_heating,
    on_poll=lambda state, rate: print(f"{state.current_temp_c}°C"),
)
print(result.outcome)  # done, stopped, stop_failed or not_started
if result.triggered_rate is not None:
    print(f"Rose at {result.triggered_rate:.1f} °C/s: the kettle may be empty.")
```

See [examples/README.md](examples/README.md) for complete usage examples.

## Technical Details

### Kettle Information

- **Firmware:** 1.1.76SSP CLI (May 9, 2024)
- **Platform:** ESP32 (Espressif)
- **Protocol:** HTTP
- **Port:** 80
- **API:** CLI interface at `/cli?cmd=<command>`

### Temperature Control

- **Range:** 40-100°C (104-212°F)
- **Step Size:** 0.5°C per dial click
- **Internal Format:** "2C" (temperature × 2)
- **Control Method:** Dial rotation (no direct API)

### Physical Buttons

The kettle has two buttons:
- **Button 1:** Separate button on base (opens menus)
- **Button 2:** The dial itself is pressable (wakes and starts heating)

The integration uses Button 2 for power/start operations.

### Update Frequency

- **Automatic polling:** Every 30 seconds
- **Command response:** Immediate refresh after control actions
- **Typical latency:** 1-2 seconds for commands

See [KETTLE_SPECS.md](KETTLE_SPECS.md) for complete technical documentation.

## Troubleshooting

### Kettle Not Responding

1. Verify the kettle is powered on and WiFi is enabled
2. Check the IP address hasn't changed
3. Ensure Home Assistant can reach the kettle's network
4. Try pinging the kettle: `ping 192.168.1.100`

### Temperature Unit Mismatch

- Check integration configuration (Settings → Integrations → Stagg EKG → Configure)
- Changing units in HA updates the kettle's LCD display
- Restart integration if sync fails

### Screen Doesn't Turn On

- The integration automatically wakes the screen
- Commands may take 1-2 seconds to complete
- Check entity state updates after a moment

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This is free and unencumbered software released into the public domain. See the [LICENSE](LICENSE) file for details.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software for any purpose, commercial or non-commercial, and by any means.

## Acknowledgments

- Built for [Fellow EKG electric kettles](https://fellowproducts.com/) (Stagg EKG, Stagg EKG+, Stagg EKG Pro, Corvo EKG)
- Uses the kettle's built-in HTTP CLI interface
- Developed and tested with firmware version 1.1.76SSP CLI on Home Assistant 2025.12.5
- **Created with AI assistance** - This integration was developed using Claude Code

## Disclaimer

This is an unofficial integration not affiliated with Fellow Products. Use at your own risk.

---

**Enjoy your smart kettle!** ☕

If you find this integration helpful, consider starring the repository!
