"""Stagg EKG+ Kettle API Client"""

import logging
import time
import requests
import re
from typing import Optional
from dataclasses import dataclass

from .rise import is_heating_mode, is_holding_mode

_LOGGER = logging.getLogger(__name__)

# Dial rotation constants
STEP_DELAY = 0.05        # 50ms between individual dial step commands
BATCH_SIZE = 20           # steps per batch before re-reading state
SETTLE_DELAY = 0.3        # 300ms pause before verification read
MAX_TOTAL_STEPS = 150     # safety cap (full range is ~120 steps, plus margin)

# Guide mode presets (Fahrenheit values, in dial order left-to-right)
GUIDE_PRESETS_F = (180, 195, 200, 205, 212)


class KettleTransientError(Exception):
    """Base class for transient kettle failures the caller can ride out.

    The kettle briefly stops answering HTTP (or returns truncated data)
    when it transitions to Off and at other moments. Callers can treat
    any subclass as a non-fatal hiccup and keep their last known state.
    """


class KettleTimeoutError(KettleTransientError):
    """Raised when the kettle's HTTP server doesn't respond in time."""


class KettleResponseError(KettleTransientError):
    """Raised when the kettle's response can't be parsed (missing fields)."""


class KettleWakeError(Exception):
    """The kettle could not be turned on in a way that lights the display."""


class KettleSettingError(Exception):
    """A setting written to the kettle didn't read back as written."""


# Hold durations the kettle's own hold menu offers, in minutes.
HOLD_MINUTES_OPTIONS = (15, 30, 45, 60)


class KettleStopError(Exception):
    """The kettle still reports heating or holding after an emergency stop."""


@dataclass
class EmergencyStopResult:
    """What emergency_stop() found and did."""

    mode_before: Optional[str]  # None if the kettle couldn't be read first
    attempts: int


@dataclass
class KettleState:
    """Represents the current state of the kettle"""
    mode: str
    current_temp_c: Optional[float]
    set_temp_c: float
    units: int  # 0=Fahrenheit, 1=Celsius (kettle's internal representation)
    clock: str
    ble_connected: bool
    heating: bool
    warming: bool
    screen_name: Optional[str] = None  # Current screen showing
    raw: str = ""  # `state` response text, HTML wrapper stripped

    @property
    def is_heating(self) -> bool:
        """Return if kettle is in a heating cycle (based on mode, not GPIO)."""
        return is_heating_mode(self.mode)

    @property
    def is_off(self) -> bool:
        """Return if kettle is in Off mode."""
        return self.mode == "S_Off"

    @property
    def is_holding(self) -> bool:
        """Return if kettle is in Hold (keep-warm) mode."""
        return is_holding_mode(self.mode)

    @property
    def is_powered_on(self) -> bool:
        """Return if kettle is powered on (not in Off mode)."""
        return not self.is_off

    @property
    def is_in_menu(self) -> bool:
        """Return if kettle is showing a menu screen."""
        return "menu" in self.mode.lower() if self.mode else False

    @property
    def is_docked(self) -> bool:
        """Whether the kettle is sitting on the base."""
        return self.current_temp_c is not None

    @property
    def current_temperature(self) -> Optional[float]:
        """Return current temperature in Celsius."""
        return self.current_temp_c

    @property
    def target_temperature(self) -> float:
        """Return target temperature in Celsius."""
        return self.set_temp_c


class StaggEKGClient:
    """Client for interacting with Stagg EKG+ kettle"""

    def __init__(
        self,
        host: str = "10.1.1.177",
        port: int = 80,
        temp_method: str = "direct",
    ):
        """Initialize the client.

        temp_method controls how `set_temperature` reaches the target:
          - "direct": single `setsetting settempr <F>` firmware call (fast)
          - "dial":   emulate physical dial (works on older/quirky firmwares)
        """
        self.base_url = f"http://{host}:{port}"
        self.temp_method = temp_method
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'StaggEKG-HA/1.0'})

    def _send_command(self, cmd: str, retries: int = 1, timeout: float = 5.0) -> str:
        """Send a CLI command to the kettle, retrying on timeout.

        The kettle's HTTP server goes unresponsive for several seconds
        during mode transitions (especially when turning off), so a single
        read timeout is not a reliable signal that anything is wrong.
        Worst-case wall time with the defaults is ~10.5s (2 × 5s + 0.5s
        backoff) — short enough that the coordinator's 5s poll won't pile
        up too far behind. If the kettle is still unresponsive after the
        final attempt, raise KettleTimeoutError so callers can distinguish
        it from other request failures.
        """
        url = f"{self.base_url}/cli"
        params = {"cmd": cmd}

        last_timeout: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.text
            except requests.exceptions.Timeout as e:
                last_timeout = e
                if attempt < retries:
                    _LOGGER.debug(
                        "Kettle timeout on '%s' (attempt %d/%d), retrying",
                        cmd, attempt + 1, retries + 1,
                    )
                    time.sleep(0.5)
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to send command '{cmd}': {e}")

        raise KettleTimeoutError(
            f"Kettle did not respond to '{cmd}' after {retries + 1} attempts: {last_timeout}"
        )

    def get_state(self) -> KettleState:
        """Get the current state of the kettle"""
        response = self._send_command("state")

        # Parse the response
        mode_match = re.search(r'mode=(\S+)', response)
        if not mode_match:
            # Treat a malformed response the same as a transient timeout —
            # the kettle occasionally returns truncated data and there's no
            # safe default for `mode` (returning "Unknown" silently flips
            # is_off/is_heating to False, which downstream entities then
            # show as a real state change).
            raise KettleResponseError(
                f"Kettle response missing 'mode' field: {response!r}"
            )

        screen_match = re.search(r'scrname=(.+?)(?:\n|$)', response)
        # tempr = current water temperature
        # temprT = target temperature (set via dial)
        temp_c_match = re.search(r'tempr=([\d.]+)\s*C', response)
        temp_set_c_match = re.search(r'temprT=([\d.]+)\s*C', response)
        units_match = re.search(r'units=(\d+)', response)
        clock_match = re.search(r'clock=(\d+:\d+)', response)
        ble_match = re.search(r'ble conn=(\d+)', response)
        heating_match = re.search(r'ho\s+(\d+)', response)
        warming_match = re.search(r'wd\s+(\d+)', response)

        return KettleState(
            mode=mode_match.group(1),
            screen_name=screen_match.group(1).strip() if screen_match else None,
            raw="\n".join(
                line.strip() for line in response.splitlines()
                if line.strip() and not line.strip().startswith("<")
            ),
            current_temp_c=float(temp_c_match.group(1)) if temp_c_match else None,
            set_temp_c=float(temp_set_c_match.group(1)) if temp_set_c_match else 0,
            units=int(units_match.group(1)) if units_match else 1,
            clock=clock_match.group(1) if clock_match else "00:00",
            ble_connected=bool(int(ble_match.group(1))) if ble_match else False,
            heating=bool(int(heating_match.group(1))) if heating_match else False,
            warming=bool(int(warming_match.group(1))) if warming_match else False,
        )

    def heat_on(self) -> str:
        """Turn heating element on (direct GPIO)"""
        return self._send_command("heaton")

    def heat_off(self) -> str:
        """Turn heating element off (direct GPIO)"""
        return self._send_command("heatoff")

    def warm_on(self) -> str:
        """Turn warming on.

        Refused while the kettle is off: `warmon` drives the warming element
        directly, so from Off it would heat with the display dark.
        """
        state = self.get_state()
        if state.is_off:
            raise KettleWakeError("Turn the kettle on before enabling warming")
        return self._send_command("warmon")

    def warm_off(self) -> str:
        """Turn warming off"""
        return self._send_command("warmoff")

    def press_button_1(self) -> str:
        """Simulate pressing button 1 (base button - opens menus)"""
        return self._send_command("1")

    def press_button_2(self) -> str:
        """Simulate pressing button 2 (dial press - wakes & starts heating)"""
        return self._send_command("2")

    def start_heating(self) -> str:
        """Start a heating cycle the way pressing the dial does.

        From Off this presses button 2, which wakes the display and starts
        heating. Never use `ss S_Heat` from Off: on firmware 1.1.75SSP it ran
        the heater while the kettle kept reporting S_Off with the display
        dark, hiding the boil from the user and from rapid-rise detection.
        `ss S_Heat` is only sent once the kettle is awake (e.g. holding),
        where the display shows the change.
        """
        state = self._ensure_awake()
        if state.is_heating:
            return "heating"
        if state.is_off:
            raise KettleWakeError(
                f"Kettle did not wake when the dial was pressed (mode={state.mode})"
            )
        self._send_command("ss S_Heat")
        return "heating"

    def stop_heating(self, max_attempts: int = 3) -> str:
        """Stop heating or holding via direct state command.

        `ss S_Off` puts the firmware in the Off state directly. We retry
        and verify because some firmware revisions occasionally drop the
        first command during a state transition.
        """
        for attempt in range(max_attempts):
            state = self.get_state()
            if not state.is_heating and not state.is_holding:
                return "stopped"

            _LOGGER.debug(
                "Sending stop command (attempt %d/%d, mode=%s)",
                attempt + 1, max_attempts, state.mode,
            )
            self._send_command("ss S_Off")
            time.sleep(0.5)

        # Final check
        state = self.get_state()
        if state.is_heating or state.is_holding:
            _LOGGER.error(
                "Failed to stop kettle after %d attempts (mode=%s)",
                max_attempts, state.mode,
            )
        return "stopped"

    def emergency_stop(self, max_attempts: int = 3) -> EmergencyStopResult:
        """Turn everything off, whatever mode the kettle reports.

        Unlike stop_heating(), this never skips sending because the kettle
        already reports Off: on firmware 1.1.75SSP the heater has been seen
        running while the mode read S_Off. Each attempt sends `ss S_Off`,
        then switches both elements off directly (`heatoff`, `warmoff`); a
        failed command doesn't stop the others. Never send a bare `ss`, which
        reboots the kettle.
        """
        try:
            mode_before: Optional[str] = self.get_state().mode
        except Exception:  # pylint: disable=broad-except
            mode_before = None
        errors = []
        for attempt in range(1, max_attempts + 1):
            for cmd in ("ss S_Off", "heatoff", "warmoff"):
                try:
                    self._send_command(cmd)
                except Exception as err:  # pylint: disable=broad-except
                    errors.append(f"{cmd}: {err}")
            time.sleep(0.5)
            try:
                state = self.get_state()
            except Exception as err:  # pylint: disable=broad-except
                errors.append(f"state: {err}")
                continue
            if not state.is_heating and not state.is_holding:
                return EmergencyStopResult(mode_before, attempt)
        raise KettleStopError(
            f"Kettle may still be on after {max_attempts} emergency stop "
            f"attempt(s): {'; '.join(errors[-3:]) or 'mode still on'}"
        )

    def end_hold(self) -> str:
        """Stop keeping the water warm.

        Ends a hold with stop_heating() (`ss S_Off`), and clears the warming
        element if its flag is set. A boil in progress is left alone.
        """
        state = self.get_state()
        if state.is_holding:
            self.stop_heating()
        if state.warming:
            self.warm_off()
        return "off"

    def _ensure_awake(self) -> KettleState:
        """Wake the kettle if it's off via button 2. Returns current state.

        Button 2 is the only clean wake path; it also starts heating as a
        side effect. The kettle passes through transitional states (logo,
        S_StartupToTempr, possibly S_Heat+menu) before settling.
        """
        state = self.get_state()
        if not state.is_off:
            return state

        _LOGGER.debug("Kettle is off — waking with button 2")
        self._send_command("2")
        for _ in range(10):  # up to 5 seconds
            time.sleep(0.5)
            state = self.get_state()
            if not state.is_off:
                return state

        _LOGGER.warning("Kettle did not wake after button 2 (mode=%s)", state.mode)
        return state

    def get_guide_mode(self) -> bool:
        """Check if guide mode is enabled."""
        response = self._send_command("prtsettings")
        match = re.search(r'guide=(\d+)', response)
        return bool(int(match.group(1))) if match else False

    def write_target(self, target_celsius: float) -> float:
        """Set the kettle's target with `setsetting settempr` and check it.

        Unlike set_temperature(), this never falls back to turning the dial,
        so it's safe while the kettle is holding. It takes effect at once,
        including mid-hold, and is saved as the kettle's target setting.
        """
        target_f = round(target_celsius * 9 / 5 + 32)
        self._send_command(f"setsetting settempr {target_f}")
        time.sleep(SETTLE_DELAY)
        actual_c = self.get_state().set_temp_c
        if abs(round(actual_c * 9 / 5 + 32) - target_f) > 1:
            raise KettleSettingError(
                f"Kettle reports a {actual_c} C target after setting {target_celsius} C"
            )
        return actual_c

    def get_hold_minutes(self) -> Optional[int]:
        """How long the kettle holds temperature after a boil, in minutes."""
        match = re.search(r"st: hold=(\d+)", self._send_command("prtsettings"))
        return int(match.group(1)) if match else None

    def set_hold_minutes(self, minutes: int) -> int:
        """Set the hold duration and check that it took.

        Only the values the kettle's hold menu offers are accepted. The
        kettle's display shows the new value straight away.
        """
        if minutes not in HOLD_MINUTES_OPTIONS:
            raise ValueError(
                f"Hold must be one of {HOLD_MINUTES_OPTIONS} minutes, not {minutes}"
            )
        self._send_command(f"setsetting hold {minutes}")
        actual = self.get_hold_minutes()
        if actual != minutes:
            raise KettleSettingError(
                f"Kettle reports hold={actual} after setting it to {minutes}"
            )
        return actual

    def set_guide_mode(self, enabled: bool) -> str:
        """Enable or disable guide mode."""
        return self._send_command(f"setsetting guide {1 if enabled else 0}")

    def set_temperature(self, target_celsius: float) -> float:
        """
        Set target temperature, respecting guide mode when possible.

        If guide mode is on and the target matches a preset, navigates to
        that preset via dial rotation (left to reset, right to select).

        If guide mode is on but the target doesn't match a preset,
        temporarily disables guide mode, uses batched dial rotation, then
        re-enables guide mode.

        If guide mode is off, uses batched dial rotation directly.

        Wakes the kettle if it's off (which also starts heating as a side
        effect — there's no way to wake without heating).

        Args:
            target_celsius: Desired target temperature in Celsius (40-100).

        Returns:
            The actual target temperature (Celsius) achieved on the kettle.
        """
        target_celsius = max(40.0, min(100.0, target_celsius))
        target_f = round(target_celsius * 9 / 5 + 32)

        if self.temp_method == "direct":
            return self._set_temperature_direct(target_f)

        guide_on = self.get_guide_mode()
        preset_index = (
            GUIDE_PRESETS_F.index(target_f)
            if guide_on and target_f in GUIDE_PRESETS_F
            else None
        )

        if preset_index is not None:
            return self._set_temperature_preset(preset_index, target_f)

        return self._set_temperature_dial(target_celsius, guide_on)

    def _set_temperature_direct(self, target_f: int) -> float:
        """Set target temperature via direct firmware command.

        Sends `setsetting settempr <F>` and reads back the actual target
        to confirm. Falls back to the dial-rotation method if the kettle
        doesn't accept the command (older firmwares may not implement it).
        """
        self._send_command(f"setsetting settempr {target_f}")
        time.sleep(SETTLE_DELAY)
        state = self.get_state()

        # Verify: kettle should now report the requested target (within
        # the precision of its display: 1F or 0.5C). If it didn't change,
        # the firmware likely doesn't accept this command — fall back.
        actual_f = round(state.set_temp_c * 9 / 5 + 32)
        if abs(actual_f - target_f) > 1:
            _LOGGER.warning(
                "Direct settempr appears unsupported (asked %dF, got %dF); "
                "falling back to dial rotation. Switch this device to the "
                "'dial' temperature-setting method in options to skip this "
                "probe in the future.",
                target_f, actual_f,
            )
            target_celsius = (target_f - 32) * 5 / 9
            guide_on = self.get_guide_mode()
            return self._set_temperature_dial(target_celsius, guide_on)

        _LOGGER.debug(
            "Direct settempr set %dF (%.1fC), actual=%.1fC",
            target_f, (target_f - 32) * 5 / 9, state.set_temp_c,
        )
        return state.set_temp_c

    def _set_temperature_preset(self, preset_index: int, target_f: int) -> float:
        """Navigate to a guide mode preset by index."""
        self._ensure_awake()

        # Reset to leftmost preset
        for _ in range(len(GUIDE_PRESETS_F)):
            self._send_command("left")
            time.sleep(STEP_DELAY)
        time.sleep(SETTLE_DELAY)

        # Navigate to target preset
        for _ in range(preset_index):
            self._send_command("right")
            time.sleep(STEP_DELAY)
        time.sleep(SETTLE_DELAY)

        state = self.get_state()
        _LOGGER.debug(
            "Preset selected: %dF (index %d), actual=%.1fC",
            target_f, preset_index, state.set_temp_c,
        )
        return state.set_temp_c

    def _set_temperature_dial(self, target_celsius: float, guide_on: bool) -> float:
        """Set temperature using batched dial rotation with verification."""
        if guide_on:
            _LOGGER.debug("Target doesn't match a preset — temporarily disabling guide mode")
            self.set_guide_mode(False)
            time.sleep(0.3)

        try:
            self._ensure_awake()

            total_steps_sent = 0

            while total_steps_sent < MAX_TOTAL_STEPS:
                state = self.get_state()
                current_target_c = state.set_temp_c

                if state.units == 0:
                    # Fahrenheit mode: each dial step is 1F
                    target_f = round(target_celsius * 9 / 5 + 32)
                    current_f = round(current_target_c * 9 / 5 + 32)
                    steps_needed = target_f - current_f
                else:
                    # Celsius mode: each dial step is 0.5C
                    steps_needed = int(round((target_celsius - current_target_c) * 2))

                if steps_needed == 0:
                    _LOGGER.debug(
                        "Temperature set complete: target=%.1fC, actual=%.1fC, total_steps=%d",
                        target_celsius, current_target_c, total_steps_sent,
                    )
                    return current_target_c

                # Send up to BATCH_SIZE steps
                batch = min(abs(steps_needed), BATCH_SIZE)
                cmd = "right" if steps_needed > 0 else "left"

                _LOGGER.debug(
                    "Sending %d dial steps (%s): current=%.1fC, target=%.1fC, remaining=%d",
                    batch, cmd, current_target_c, target_celsius, abs(steps_needed),
                )

                for _ in range(batch):
                    self._send_command(cmd)
                    time.sleep(STEP_DELAY)

                total_steps_sent += batch
                time.sleep(SETTLE_DELAY)

            # Exhausted step budget - return whatever we achieved
            final_state = self.get_state()
            _LOGGER.warning(
                "Temperature set exhausted step budget (%d steps): target=%.1fC, actual=%.1fC",
                total_steps_sent, target_celsius, final_state.set_temp_c,
            )
            return final_state.set_temp_c
        finally:
            if guide_on:
                _LOGGER.debug("Restoring guide mode")
                self.set_guide_mode(True)

    def rotate_dial_left(self, steps: int = 1) -> str:
        """Rotate dial left (decrease temperature)"""
        result = ""
        for _ in range(steps):
            result = self._send_command("left")
            if steps > 1:
                time.sleep(STEP_DELAY)
        return result

    def rotate_dial_right(self, steps: int = 1) -> str:
        """Rotate dial right (increase temperature)"""
        result = ""
        for _ in range(steps):
            result = self._send_command("right")
            if steps > 1:
                time.sleep(STEP_DELAY)
        return result

    def set_units_fahrenheit(self) -> str:
        """Set temperature units to Fahrenheit"""
        return self._send_command("setunitsf")

    def set_units_celsius(self) -> str:
        """Set temperature units to Celsius"""
        return self._send_command("setunitsc")
