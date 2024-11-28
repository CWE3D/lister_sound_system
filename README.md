# Lister Sound System Plugin Documentation

## Version 2.1.0

## Overview
The Lister Sound System Plugin enables audio feedback for your 3D printer events through the Raspberry Pi's audio system. Play sounds for print completion, errors, and custom events using either predefined sounds or your own WAV files.

## Features
- Asynchronous sound playback (won't interrupt printer operations)
- Support for predefined and custom WAV files
- Web API integration through Moonraker
- Easy installation and configuration
- Real-time sound scanning and caching
- System audio verification

## Installation

### Prerequisites
- Klipper and Moonraker installed
- Raspberry Pi with working audio output
- Git installed (`sudo apt-get install git`)

### Automatic Installation

1. Clone the repository:
```bash
cd ~
git clone https://github.com/CWE3D/lister_sound_system.git
```

2. Run the installation script:
```bash
cd ~/lister_sound_system
chmod +x install.sh
./install.sh
```

3. Add configuration to your `printer.cfg`:
```ini
[sound_system]
sound_directory: ~/lister_sound_system/sounds
```

### Verifying Installation

1. Check that services are running:
```bash
systemctl status klipper
systemctl status moonraker
```

2. Test audio system:
```bash
# In Klipper console:
SOUND_LIST
```

## Configuration

### Default Sound Events
The plugin comes with several predefined sound events:
- `print_start` - When a print begins
- `print_complete` - When a print finishes successfully
- `print_cancel` - When a print is canceled
- `error` - When an error occurs

### Adding Custom Sounds

1. Prepare your WAV file (44.1kHz, 16-bit recommended)
2. Copy to the sounds directory:
```bash
cp your-sound.wav ~/lister_sound_system/sounds/
```
3. Rescan sounds (optional):
```bash
# In Klipper console:
SOUND_LIST
```

## Usage

### Klipper Console Commands

1. List available sounds:
```gcode
SOUND_LIST
```

2. Play a predefined sound:
```gcode
PLAY_SOUND SOUND=print_complete
```

3. Play a custom sound:
```gcode
PLAY_SOUND SOUND=my-custom.wav
```

### Integration with Macros

Add sound notifications to your existing macros:

```gcode
[gcode_macro START_PRINT]
gcode:
    # Your existing start print commands
    PLAY_SOUND SOUND=print_start

[gcode_macro END_PRINT]
gcode:
    # Your existing end print commands
    PLAY_SOUND SOUND=print_complete

[gcode_macro CANCEL_PRINT]
gcode:
    # Your existing cancel print commands
    PLAY_SOUND SOUND=print_cancel
```

### Web API Usage

The plugin provides several REST API endpoints through Moonraker:

1. List available sounds:
```http
GET /server/sound/list
```
Response:
```json
{
    "sounds": {
        "print_complete": "/path/to/print_complete.wav",
        "custom_sound": "/path/to/custom_sound.wav"
    },
    "sound_dir": "/home/pi/lister_sound_system/sounds",
    "last_scan": 1234567890
}
```

2. Play a sound:
```http
POST /server/sound/play
Content-Type: application/json

{
    "sound": "print_complete"
}
```

3. Rescan sounds directory:
```http
POST /server/sound/scan
```

4. Get system information:
```http
GET /server/sound/info
```

## Troubleshooting

### No Sound Playing

1. Check audio device:
```bash
aplay -l
```

2. Test audio directly:
```bash
aplay ~/lister_sound_system/sounds/print_complete.wav
```

3. Check file permissions:
```bash
ls -l ~/lister_sound_system/sounds/
```

### Common Issues

1. **"Sound file not found" error**
   - Verify the file exists in the sounds directory
   - Check file permissions
   - Ensure the filename matches exactly

2. **"aplay not available" error**
   - Reinstall alsa-utils:
   ```bash
   sudo apt-get install --reinstall alsa-utils
   ```

3. **No audio device found**
   - Configure Raspberry Pi audio:
   ```bash
   sudo raspi-config
   ```
   Navigate to System Options > Audio and configure appropriately

### Fixing Permissions
If you encounter permission issues:
```bash
sudo chown -R pi:pi ~/lister_sound_system/sounds/
sudo chmod -R 755 ~/lister_sound_system/sounds/
```

## System Maintenance

### Updating the Plugin
```bash
cd ~/lister_sound_system
git pull
./install.sh
```

### Backing Up Sounds
```bash
cp -r ~/lister_sound_system/sounds/ ~/sounds_backup/
```

## Best Practices

1. Sound Files
   - Keep WAV files short (1-2 seconds)
   - Use consistent volume levels
   - Standard format: 44.1kHz, 16-bit
   - Descriptive filenames without spaces

2. System Performance
   - Limit total number of sound files
   - Keep file sizes reasonable
   - Use asynchronous playback (default)

3. Implementation
   - Test sounds before production use
   - Back up custom sounds
   - Document custom sound usage

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Support
For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact the Lister 3D support team

## License
GNU General Public License v3.0

## Additional Resources

- [Klipper Documentation](https://www.klipper3d.org/)
- [Moonraker Documentation](https://moonraker.readthedocs.io/)
- [Raspberry Pi Audio Configuration](https://www.raspberrypi.com/documentation/computers/config_txt.html#audio)
- [WAV File Format](https://en.wikipedia.org/wiki/WAV)

This plugin is part of the Lister 3D printer ecosystem, designed to enhance the user experience with audio feedback for important printer events.