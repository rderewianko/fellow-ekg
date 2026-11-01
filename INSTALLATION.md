# Stagg EKG+ Home Assistant Installation Guide

## Quick Start

1. **Copy the Integration**
   ```bash
   cd /config  # Your Home Assistant config directory
   mkdir -p custom_components
   cp -r /path/to/custom_components/fellow custom_components/
   ```

2. **Restart Home Assistant**
   - Go to Settings → System → Restart
   - Wait for Home Assistant to fully restart

3. **Add the Integration**
   - Go to Settings → Devices & Services
   - Click "+ ADD INTEGRATION"
   - Search for "Fellow Stagg EKG+"
   - Click on it to start setup

4. **Configure**
   - Enter your kettle's IP address (default: 192.168.1.100)
   - Select your preferred temperature unit (Celsius or Fahrenheit)
   - Click Submit

## Finding Your Kettle's IP Address

### Method 1: Check your router
- Log into your router's admin interface
- Look for connected devices
- Look for:
  - "Stagg EKG", "Fellow", or "EKG-XX-XX-XX"
  - "espressif" (ESP32 manufacturer)
  - May include MAC address like "espressif 16:b0"

### Method 2: Use nmap
```bash
nmap -sn 192.168.1.0/24  # Adjust to your network range
```

### Method 3: Try the default
- The kettle is often at `192.168.1.100`
- Try accessing `http://192.168.1.100/` in a browser
- You should see firmware information

## Temperature Units

The integration allows you to choose between Celsius and Fahrenheit:

- **Celsius (units=1)**: Kettle displays °C
- **Fahrenheit (units=0)**: Kettle displays °F

**Important**: The unit setting affects both:
1. Your Home Assistant display
2. The kettle's physical LCD display

You can change the unit later:
1. Go to Settings → Devices & Services
2. Find "Stagg EKG+"
3. Click "CONFIGURE"
4. Select your preferred unit
5. Submit

## Verifying Installation

After setup, you should see:

**Entities Created:**
- `water_heater.fellow_kettle` - Main control
- `sensor.fellow_current_temperature` - Current temp
- `sensor.fellow_target_temperature` - Target temp
- `sensor.fellow_mode` - Kettle mode
- `switch.fellow_heating` - Heating control
- `switch.fellow_warming` - Warming control

## Troubleshooting

### "Cannot connect to kettle"
1. Verify the kettle is powered on
2. Check that WiFi is enabled on the kettle
3. Verify the IP address
4. Try pinging the kettle: `ping 192.168.1.100`
5. Try accessing `http://[kettle-ip]/cli?cmd=state` in a browser

### Entities not showing up
1. Check the Home Assistant logs
2. Go to Settings → System → Logs
3. Search for "fellow"
4. Look for error messages

### Temperature unit not changing
1. Make sure the kettle is connected
2. Check if the kettle responds to: `http://[kettle-ip]/cli?cmd=prtsettings`
3. Look for `st: units=X` in the response
4. Try manually changing via: `http://[kettle-ip]/cli?cmd=setunitsf` (Fahrenheit) or `setunitsc` (Celsius)

## Advanced Configuration

### Custom Polling Interval

Use the integration's **Configure** options (Polling interval, 5–60 seconds). Or edit `custom_components/fellow/__init__.py`:

```python
# Change this line (default is 5 seconds)
update_interval=timedelta(seconds=5),
```

### Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.fellow: debug
```

## Uninstalling

1. Go to Settings → Devices & Services
2. Find "Stagg EKG+"
3. Click the three dots menu
4. Select "Delete"
5. Optionally, delete the `custom_components/fellow` folder
6. Restart Home Assistant

## Support

For issues, questions, or feature requests:
- Check the README.md for usage examples
- Review the CHANGELOG.md for recent changes
- Open an issue on GitHub (if applicable)
