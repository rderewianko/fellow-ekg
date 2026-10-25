# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Rapid temperature-rise detection as a proxy for an empty or nearly empty
  kettle. New `Rapid Temperature Rise` binary sensor and `fellow_rapid_rise`
  event; the kettle is turned off automatically unless disabled, retrying
  until it reports Off. If it doesn't, a `fellow_rapid_rise_stop_failed`
  event fires and a persistent notification is shown.
- Options: `rapid_rise_auto_stop` (default on) and `rapid_rise_threshold`
  (default 3.0 °C/s, range 1.0–10.0).
- `watch_heat_cycle()` in `rise.py` for scripts outside Home Assistant: it
  watches one boil and turns the kettle off on a rapid rise. The standalone
  quickstart in the README asks whether you added water, then uses it.
- `Heat Up Target` and `Hold Target` numbers: hold lower than you boil. When
  the kettle starts holding, its target is lowered to the Hold Target, and
  the Heat Up Target is put back when the hold runs out or the kettle is
  turned off (not when it's lifted to pour). Outside a lowered hold, Heat Up
  Target follows the kettle's own target. Both are saved across restarts.
  The water heater's target is the Heat Up Target, so
  `water_heater.set_temperature` keeps working as before; it also shows the
  Hold Target as a `hold_temperature` attribute.
- `Hold Delay` number (minutes, default 2): after a boil, the water stays at
  the Heat Up Target this long, so there's time to pour, before the target
  drops to the Hold Target. Pours during the delay don't restart it. The Hold
  Target's `drops_at` attribute shows when the drop is due.
- `Hold Ends` sensor: when the current hold ends, as a countdown, with the
  end as a clock time in an `ends_at` attribute.
- `Mode` shows "Cooling to target" or "Cooling to hold target" while the
  water is more than 1 °C above the kettle's target, which the kettle itself
  reports as heating or holding.
- `Hold Duration` select: 15, 30, 45 or 60 minutes, the same choices as the
  kettle's hold menu. It writes `setsetting hold <n>` and reads it back, and
  re-reads the setting about once a minute to pick up changes made on the
  kettle.
- `Emergency Stop` button: sends `ss S_Off` and switches both elements off
  directly, repeating until the kettle reports Off, without first checking
  whether it already claims to be off. Each press reports what the kettle
  was doing and whether it stopped, in a notification and a `last_result`
  attribute.
- `Raw Status` diagnostic sensor: the mode and unrounded temperature from the
  latest poll, with the full `state` response in a `raw` attribute that isn't
  recorded to history.
- Unit tests for the detector in `tests/test_rise.py`.

### Changed
- `Target Temperature` is renamed `Native Target Temperature` (same entity
  ID) and is explicitly the kettle's own target, read-only.
  During a lowered hold it shows the Hold Target; its `role` attribute says
  whether it's the `heat_up` or `hold` target. Set `Heat Up Target` and
  `Hold Target` instead.
- `Warming` is now `Warming / Holding` and follows the kettle's hold
  instead of driving the warming element directly (`warmon` / `warmoff`),
  which the kettle's own state and display don't reflect. It turns on when a
  boil finishes and the kettle holds; turning it off ends the hold with
  `ss S_Off`. Turning it on is refused, so a hold only ever comes from a boil
  and never runs past the Hold Duration. The water heater's warm and off
  modes match.
- `Power` now means the kettle answers Home Assistant: on while polls
  succeed, off after two failed polls in a row (about 15–30 s), and never
  unavailable. It used to be on whenever the kettle wasn't in `S_Off`, which
  the Mode sensor already shows, so it read Off for a kettle that was plugged
  in and reachable.

### Removed
- **Breaking:** the `Lifted` binary sensor (`binary_sensor.fellow_lifted`),
  replaced by `On Base` (`binary_sensor.fellow_on_base`). Note the flip: On
  Base is on while the kettle sits on its base, and reads "On base" / "Off
  base" instead of "Moving" / "Not moving". It also tracks the base
  properly: Lifted stayed on for a fixed 90 s after every lift, while On
  Base switches back about 5–10 s after the kettle is set down (two polls in
  a row with a temperature reading; the kettle reports `tempr=nan` off the
  base). It has `last_lifted` and `last_set_down` attributes.
- **Breaking:** the `Low Water Warning` binary sensor
  (`binary_sensor.fellow_low_water_warning`). It was on whenever the water
  was below 30 °C, so it tracked how cold the water was, not how much there
  was: on for a full kettle of cold water, off for a nearly empty one that
  was just boiled. Use `Rapid Temperature Rise`, which reflects the water
  level while heating. Automations that use the old entity need updating;
  Home Assistant will list it as no longer provided until it's deleted.
- **Breaking:** `KettleState.may_have_no_water` in the standalone example
  client (`examples/stagg_ekg_api.py`), the same 30 °C check, and the
  `[LOW WATER WARNING]` suffix in its `str()`. The examples README shows
  `watch_heat_cycle()` instead.

### Fixed
- Turning the dial or opening a menu no longer makes the integration think
  the kettle is off. The kettle adds a suffix to its mode while a screen is
  shown on top (`S_Heat+tset`, `S_Hold+menu`), and only a few exact modes
  were recognized, so rapid-rise detection paused and restarted its grace
  period, auto-stop could count a holding kettle as stopped, and
  `stop_heating()` could skip sending. Modes are now compared by the part
  before the `+`. The standalone example client gets the same fix.
- Starting a boil from Home Assistant no longer bypasses the kettle's
  display. `ss S_Heat` sent from Off ran the heater on firmware 1.1.75SSP
  while the kettle kept reporting Off with the display dark, so neither the
  user nor the integration could tell it was heating. `start_heating()` now
  presses the dial from Off, like starting it by hand, and raises an error if
  the kettle doesn't wake. Turning on warming while the kettle is off is
  refused for the same reason.
- The example client's `stop_heating()` sends `ss S_Off` and checks that it
  took, like the integration's client. It used to press the dial, which
  toggles, so it could start a stopped kettle again.

## [2.0.0] - 2026-01-03

### Breaking Changes
- **Domain renamed from `stagg_ekg` to `fellow`** to match Home Assistant brands repository and support all Fellow EKG models
- **Entity IDs have changed**:
  - `water_heater.stagg_ekg_kettle` → `water_heater.fellow_kettle`
  - `sensor.stagg_ekg_current_temperature` → `sensor.fellow_current_temperature`
  - `sensor.stagg_ekg_target_temperature` → `sensor.fellow_target_temperature`
  - `sensor.stagg_ekg_mode` → `sensor.fellow_mode`
  - `switch.stagg_ekg_heating` → `switch.fellow_heating`
  - `switch.stagg_ekg_warming` → `switch.fellow_warming`
  - `binary_sensor.stagg_ekg_power` → `binary_sensor.fellow_power`
  - `binary_sensor.stagg_ekg_low_water_warning` → `binary_sensor.fellow_low_water_warning`
- **Directory renamed**: `custom_components/stagg_ekg/` → `custom_components/fellow/`

### Migration Instructions
1. Remove the old integration from Home Assistant (Settings → Devices & Services)
2. Delete the `custom_components/stagg_ekg` folder
3. Install v2.0.0 with the new `custom_components/fellow` folder
4. Re-add the integration
5. Update all automations, scripts, and dashboard cards to use new entity IDs

### Added
- Added `issue_tracker` to manifest.json for better HACS compliance
- GitHub Actions for HACS and Hassfest validation

### Fixed
- Fixed HACS validation errors (removed invalid keys from hacs.json)
- Fixed manifest key ordering to meet Home Assistant requirements
- Integration now aligns with Home Assistant brands repository entry

## [1.0.0] - 2025-12-27

### Added
- Initial release of Fellow Stagg EKG+ Home Assistant integration
- Water heater entity for main temperature control
- Temperature sensors (current and target)
- Operating mode sensor
- Heating and warming switches
- Power status binary sensor
- Low water warning binary sensor
- Temperature unit selection (Celsius/Fahrenheit) with LCD sync
- Standalone Python API (`stagg_ekg_api.py`)
- Comprehensive documentation and examples
- HACS compatibility

### Features
- Local control (no cloud required)
- Temperature range: 40-100°C (104-212°F)
- Precise 0.5°C temperature steps
- Automatic screen wake and power management
- Water detection heuristic (temperature-based)
- Real-time status monitoring (30-second polling)
- Full automation support

### Technical Details
- Discovered correct temperature field mappings (tempr vs temprT)
- Implemented dial rotation for temperature setting (only method available)
- Identified two physical buttons (base button and dial button)
- Button 2 (dial button) used for optimal power/start behavior
- Added delays for reliable command execution
- Fixed step calculation (0.5°C per step, not 5.5°C)

### Documentation
- README.md with installation and usage
- KETTLE_SPECS.md with complete technical reference
- PYTHON_API_EXAMPLES.md with 10 real-world examples
- Automation examples for common use cases

### Notes
- Tested with firmware version 1.1.76SSP CLI
- No direct temperature setting API exists (must use dial rotation)
- Temperature unit changes sync with kettle's LCD display
- Integration uses local HTTP CLI interface on port 80
