#!/usr/bin/env python3
"""
Stagg EKG+ Kettle API Client
Control your Fellow Stagg EKG+ kettle via HTTP CLI interface
"""

import requests
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Modes in which the kettle is heating or holding temperature. A screen on
# top of a mode adds a suffix (S_Heat+tset, S_Hold+menu), so compare the
# part before the `+`.
ON_BASE_MODES = ("S_Heat", "S_StartupToTempr", "S_Hold")


def _is_on(mode: str) -> bool:
    return (mode or "").split("+", 1)[0] in ON_BASE_MODES


@dataclass
class KettleState:
    """Represents the current state of the kettle"""
    mode: str
    current_temp_c: Optional[float]
    set_temp_c: float
    set_temp_f: float
    units: int  # 0=Fahrenheit, 1=Celsius (kettle's internal representation)
    clock: str
    ble_connected: bool
    heating: bool
    warming: bool
    screen_name: Optional[str] = None  # Current screen showing

    @property
    def is_powered_on(self) -> bool:
        """Return if kettle is powered on (not in Off mode)."""
        return "Off" not in self.mode

    @property
    def is_in_menu(self) -> bool:
        """Return if kettle is showing a menu screen."""
        return "menu" in self.mode.lower() if self.mode else False

    def __str__(self):
        temp_unit = "°C" if self.units == 1 else "°F"
        current = f"{self.current_temp_c}°C" if self.current_temp_c else "N/A"
        return f"Mode: {self.mode}, Current: {current}, Target: {self.set_temp_c}°C ({self.set_temp_f}°F), Time: {self.clock}, Display Unit: {temp_unit}"


class StaggEKGClient:
    """Client for interacting with Stagg EKG+ kettle"""

    def __init__(self, host: str, port: int = 80):
        """
        Initialize the client

        Args:
            host: IP address or hostname of the kettle
            port: HTTP port (default: 80)
        """
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'StaggEKG-Python-Client/1.0'})

    def _send_command(self, cmd: str) -> str:
        """
        Send a CLI command to the kettle

        Args:
            cmd: Command to execute

        Returns:
            Raw response text from the kettle
        """
        url = f"{self.base_url}/cli"
        params = {"cmd": cmd}

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to send command '{cmd}': {e}")

    def get_state(self) -> KettleState:
        """
        Get the current state of the kettle

        Returns:
            KettleState object with current kettle status
        """
        response = self._send_command("state")

        # Parse the response
        mode_match = re.search(r'mode=(\S+)', response)
        screen_match = re.search(r'scrname=(.+?)(?:\n|$)', response)
        # tempr = current water temperature
        # temprT = target temperature (set via dial)
        temp_c_match = re.search(r'tempr=([\d.]+)\s*C', response)
        temp_set_c_match = re.search(r'temprT=([\d.]+)\s*C', response)
        temp_set_f_match = re.search(r'temps=(\d+)', response)
        units_match = re.search(r'units=(\d+)', response)
        clock_match = re.search(r'clock=(\d+:\d+)', response)
        ble_match = re.search(r'ble conn=(\d+)', response)
        heating_match = re.search(r'ho\s+(\d+)', response)
        warming_match = re.search(r'wd\s+(\d+)', response)

        # Parse set temp in Fahrenheit (stored in 2C units, so divide by 2)
        set_temp_f = int(temp_set_f_match.group(1)) / 2 if temp_set_f_match else 0

        return KettleState(
            mode=mode_match.group(1) if mode_match else "Unknown",
            screen_name=screen_match.group(1).strip() if screen_match else None,
            current_temp_c=float(temp_c_match.group(1)) if temp_c_match else None,
            set_temp_c=float(temp_set_c_match.group(1)) if temp_set_c_match else 0,
            set_temp_f=set_temp_f,
            units=int(units_match.group(1)) if units_match else 1,
            clock=clock_match.group(1) if clock_match else "00:00",
            ble_connected=bool(int(ble_match.group(1))) if ble_match else False,
            heating=bool(int(heating_match.group(1))) if heating_match else False,
            warming=bool(int(warming_match.group(1))) if warming_match else False,
        )

    def get_settings(self) -> Dict[str, Any]:
        """
        Get all kettle settings

        Returns:
            Dictionary of settings
        """
        response = self._send_command("prtsettings")
        settings = {}

        # Parse settings
        for line in response.split('\n'):
            if line.startswith('st: '):
                match = re.search(r'st: (\w+)=(.+)', line)
                if match:
                    key, value = match.groups()
                    settings[key] = value.strip()

        return settings

    def heat_on(self) -> str:
        """Turn heating on"""
        return self._send_command("heaton")

    def heat_off(self) -> str:
        """Turn heating off"""
        return self._send_command("heatoff")

    def warm_on(self) -> str:
        """Turn warming on"""
        return self._send_command("warmon")

    def warm_off(self) -> str:
        """Turn warming off"""
        return self._send_command("warmoff")

    def set_warm_duty(self, duty_percent: int) -> str:
        """
        Set warming duty cycle

        Args:
            duty_percent: Duty cycle percentage (0-100)
        """
        if not 0 <= duty_percent <= 100:
            raise ValueError("Duty percent must be between 0 and 100")
        return self._send_command(f"warmduty {duty_percent}")

    def set_units_fahrenheit(self) -> str:
        """Set temperature units to Fahrenheit"""
        return self._send_command("setunitsf")

    def set_units_celsius(self) -> str:
        """Set temperature units to Celsius"""
        return self._send_command("setunitsc")

    def set_clock(self, hour: int, minute: int, second: int = 0) -> str:
        """
        Set the kettle clock

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59), optional
        """
        return self._send_command(f"setclock {hour} {minute} {second}")

    def press_button_1(self) -> str:
        """Simulate pressing button 1"""
        return self._send_command("1")

    def press_button_2(self) -> str:
        """Simulate pressing button 2"""
        return self._send_command("2")

    def rotate_dial_left(self) -> str:
        """Rotate dial counter-clockwise"""
        return self._send_command("left")

    def rotate_dial_right(self) -> str:
        """Rotate dial clockwise"""
        return self._send_command("right")

    def power_on(self) -> str:
        """
        Power on the kettle and wake the screen.
        Ensures the kettle is ready for operation.
        Button 2 is the dial button - pressing it wakes the kettle directly to main screen.
        """
        # Press button 2 (dial button) to wake and go to main screen
        return self._send_command("2")

    def start_heating(self) -> str:
        """
        Start a heating cycle.
        Wakes the kettle if needed and initiates heating.
        Button 2 (dial button) wakes the kettle and starts heating directly.
        """
        # Press button 2 (dial button) - wakes if off and starts heating
        return self._send_command("2")

    def stop_heating(self, max_attempts: int = 3) -> str:
        """
        Stop heating or holding and turn the kettle off.

        Sends `ss S_Off`, which puts the firmware in the Off state directly,
        and checks that it took, retrying because the kettle sometimes drops
        the command during a state change. Pressing the dial (button 2)
        instead toggles, so it can start the kettle again. Never send a bare
        `ss`: it reboots the kettle.
        """
        import time

        for _ in range(max_attempts):
            if not _is_on(self.get_state().mode):
                return "stopped"
            self._send_command("ss S_Off")
            time.sleep(0.5)

        if _is_on(self.get_state().mode):
            return "still on"
        return "stopped"

    def get_wifi_info(self) -> str:
        """Get WiFi configuration and status"""
        return self._send_command("wifiprt")

    def wifi_on(self) -> str:
        """Turn WiFi on"""
        return self._send_command("wifion")

    def wifi_off(self) -> str:
        """Turn WiFi off"""
        return self._send_command("wifioff")

    def ble_enable(self) -> str:
        """Enable Bluetooth"""
        return self._send_command("bleen")

    def ble_disable(self) -> str:
        """Disable Bluetooth"""
        return self._send_command("bledis")

    def get_firmware_info(self) -> str:
        """Get firmware version and partition information"""
        return self._send_command("fwinfo")

    def get_heap_info(self) -> str:
        """Get memory/heap information"""
        return self._send_command("heapprt")

    def buzzer(self, freq_hz: int, duty: int, duration_ms: int) -> str:
        """
        Control the buzzer

        Args:
            freq_hz: Frequency in Hz
            duty: Duty cycle (13-bit value)
            duration_ms: Duration in milliseconds
        """
        return self._send_command(f"buz {freq_hz} {duty} {duration_ms}")

    def buzzer_sos(self) -> str:
        """Play SOS pattern on buzzer"""
        return self._send_command("buz sos")

    def refresh_gui(self) -> str:
        """Refresh the GUI display"""
        return self._send_command("refresh")

    def reset(self) -> str:
        """Reset the kettle (WARNING: This will reboot the device)"""
        return self._send_command("reset")

    def set_temperature(self, target_celsius: float) -> str:
        """
        Set target temperature by rotating the dial.

        Args:
            target_celsius: Target temperature in Celsius (40-100°C)

        Returns:
            Status message
        """
        import time

        # Validate temperature range
        if not 40 <= target_celsius <= 100:
            raise ValueError("Temperature must be between 40°C and 100°C")

        # Get current state
        state = self.get_state()
        current_target = state.set_temp_c

        # Calculate steps needed (each step = 0.5°C)
        temp_diff = target_celsius - current_target
        steps = int(round(temp_diff * 2))

        if steps == 0:
            return f"Already at {target_celsius}°C"

        # Rotate dial
        if steps > 0:
            for _ in range(steps):
                self._send_command("right")
                time.sleep(0.1)
            return f"Increased temperature by {temp_diff:.1f}°C to {target_celsius}°C"
        else:
            for _ in range(abs(steps)):
                self._send_command("left")
                time.sleep(0.1)
            return f"Decreased temperature by {abs(temp_diff):.1f}°C to {target_celsius}°C"

    def heat_to_temperature(self, target_celsius: float) -> str:
        """
        Set temperature and start heating in one operation.

        Args:
            target_celsius: Target temperature in Celsius (40-100°C)

        Returns:
            Status message
        """
        # Set temperature first
        result = self.set_temperature(target_celsius)

        # Start heating
        self.start_heating()

        return f"{result} and started heating"

    def is_at_target(self, tolerance: float = 2.0) -> bool:
        """
        Check if current temperature is at or near target.

        Args:
            tolerance: Acceptable difference in °C (default 2.0°C)

        Returns:
            True if within tolerance of target
        """
        state = self.get_state()

        if state.current_temp_c is None:
            return False

        diff = abs(state.current_temp_c - state.set_temp_c)
        return diff <= tolerance

    def get_raw_response(self, cmd: str) -> str:
        """
        Send a raw CLI command

        Args:
            cmd: Raw command string

        Returns:
            Raw response from kettle
        """
        return self._send_command(cmd)


def main():
    """Example usage of the Stagg EKG API"""

    # Initialize client
    kettle = StaggEKGClient(host="192.168.1.100")

    print("=" * 60)
    print("Stagg EKG+ Kettle Control")
    print("=" * 60)

    # Get current state
    print("\n[Current State]")
    state = kettle.get_state()
    print(state)

    # Get settings
    print("\n[Settings]")
    settings = kettle.get_settings()
    for key, value in settings.items():
        print(f"  {key}: {value}")

    # Get firmware info
    print("\n[Firmware Info]")
    fw_info = kettle.get_firmware_info()
    for line in fw_info.split('\n'):
        if 'version' in line.lower() or 'partition' in line.lower():
            print(f"  {line.strip()}")

    # Get WiFi info
    print("\n[WiFi Info]")
    wifi_info = kettle.get_wifi_info()
    for line in wifi_info.split('\n'):
        if 'ssid' in line.lower() or 'mode' in line.lower():
            print(f"  {line.strip()}")

    print("\n" + "=" * 60)
    print("Common Usage Examples:")
    print("=" * 60)
    print("\n# Basic Control:")
    print("  kettle.start_heating()           # Turn on and start heating")
    print("  kettle.stop_heating()            # Stop and turn off")
    print("  kettle.power_on()                # Wake screen (standby mode)")
    print()
    print("# Temperature Control:")
    print("  kettle.set_temperature(85)       # Set target to 85°C")
    print("  kettle.heat_to_temperature(95)   # Set to 95°C and start heating")
    print("  kettle.is_at_target()            # Check if at target temp")
    print()
    print("# Manual Controls:")
    print("  kettle.heat_on() / heat_off()    # Direct heating element")
    print("  kettle.warm_on() / warm_off()    # Warming mode")
    print("  kettle.rotate_dial_left()        # Decrease temp 0.5°C")
    print("  kettle.rotate_dial_right()       # Increase temp 0.5°C")
    print()
    print("# Settings:")
    print("  kettle.set_units_celsius()       # Display in Celsius")
    print("  kettle.set_units_fahrenheit()    # Display in Fahrenheit")
    print()
    print("# Fun:")
    print("  kettle.buzzer_sos()              # Play SOS on buzzer")
    print("=" * 60)


if __name__ == "__main__":
    main()
