import os
import asyncio
import logging
from subprocess import DEVNULL

class SoundSystem:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')

        # Default sound directory in plugin
        default_sound_dir = os.path.join(
            os.path.expanduser('~'),
            'lister_sound_system',
            'sounds'
        )
        self.sound_dir = config.get('sound_directory', default_sound_dir)

        # Default sounds mapping
        self.sounds = {
            'print_start': os.path.join(self.sound_dir, 'print_start.wav'),
            'print_complete': os.path.join(self.sound_dir, 'print_complete.wav'),
            'print_cancel': os.path.join(self.sound_dir, 'print_cancel.wav'),
            'error': os.path.join(self.sound_dir, 'error.wav'),
            'startup': os.path.join(self.sound_dir, 'startup.wav'),
        }

        # Register commands
        self.gcode.register_command(
            'PLAY_SOUND',
            self.cmd_PLAY_SOUND,
            desc=self.cmd_PLAY_SOUND_help
        )

        self.gcode.register_command(
            'SOUND_LIST',
            self.cmd_SOUND_LIST,
            desc=self.cmd_SOUND_LIST_help
        )

        # Tell the OS to locate aplay
        self.aplay_path = os.popen('which aplay').read().strip()
        if not self.aplay_path:
            logging.error("SoundSystem: 'aplay' not found in system path")

    def _verify_sound_file(self, sound_path):
        """Verify sound file exists and is accessible"""
        return os.path.isfile(sound_path) and os.access(sound_path, os.R_OK)

    def _resolve_sound_path(self, sound_spec):
        """
        Resolve sound specification to an actual file path.
        Can handle both predefined sounds and direct file paths.
        """
        # First check if it's a predefined sound
        if sound_spec in self.sounds:
            return self.sounds[sound_spec]

        # If not, check if it's a direct path
        if sound_spec.endswith('.wav'):
            # Try different path possibilities
            possibilities = [
                sound_spec,  # Absolute path
                os.path.join(self.sound_dir, sound_spec),  # Relative to sound dir
                os.path.expanduser(sound_spec)  # Expand user directory
            ]

            for path in possibilities:
                if self._verify_sound_file(path):
                    return path

        return None

    async def _play_sound_async(self, sound_path):
        """Asynchronously play a sound file using aplay"""
        if not self.aplay_path:
            logging.error("SoundSystem: aplay not available")
            return

        try:
            # Create subprocess using asyncio
            process = await asyncio.create_subprocess_exec(
                self.aplay_path, sound_path,
                stdout=DEVNULL,
                stderr=DEVNULL
            )
            await process.wait()
        except Exception as e:
            logging.exception(f"Error playing sound {sound_path}: {str(e)}")

    cmd_PLAY_SOUND_help = """Play a sound file.
    PLAY_SOUND SOUND=name_or_path - Play either a predefined sound or a WAV file

    Examples:
    PLAY_SOUND SOUND=print_complete    ; Play predefined print complete sound
    PLAY_SOUND SOUND=custom.wav        ; Play custom.wav from sound directory
    PLAY_SOUND SOUND=/path/to/sound.wav ; Play sound using absolute path"""

    def cmd_PLAY_SOUND(self, gcmd):
        """Handle PLAY_SOUND command"""
        sound_spec = gcmd.get('SOUND')
        if not sound_spec:
            raise gcmd.error("No sound specified")

        # Resolve the sound path
        sound_path = self._resolve_sound_path(sound_spec)

        if not sound_path:
            raise gcmd.error(
                f"Could not find sound '{sound_spec}'. "
                f"Neither a predefined sound nor a valid WAV file path."
            )

        # Verify sound file exists
        if not self._verify_sound_file(sound_path):
            raise gcmd.error(f"Sound file not accessible: {sound_path}")

        # Log the sound being played
        gcmd.respond_info(f"Playing sound: {sound_path}")

        # Schedule sound playback asynchronously
        reactor = self.printer.get_reactor()
        reactor.register_async_callback(
            lambda e: self._play_sound_async(sound_path)
        )

    cmd_SOUND_LIST_help = "List all available predefined sounds and sound directory location"

    def cmd_SOUND_LIST(self, gcmd):
        """List all available sounds"""
        msg = ["Available predefined sounds:"]
        for sound_id, path in sorted(self.sounds.items()):
            status = "✓" if self._verify_sound_file(path) else "✗"
            msg.append(f"{status} {sound_id}: {path}")

        msg.append("\nSound directory location:")
        msg.append(f"  {self.sound_dir}")

        # List any additional WAV files in sound directory
        if os.path.exists(self.sound_dir):
            custom_sounds = [f for f in os.listdir(self.sound_dir)
                             if f.endswith('.wav') and
                             os.path.join(self.sound_dir, f) not in self.sounds.values()]
            if custom_sounds:
                msg.append("\nAdditional WAV files in sound directory:")
                for sound_file in sorted(custom_sounds):
                    msg.append(f"  {sound_file}")

        gcmd.respond_info("\n".join(msg))


def load_config(config):
    return SoundSystem(config)