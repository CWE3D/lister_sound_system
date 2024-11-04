# File: /home/pi/lister_sound_system/extras/sound_system.py

import os
import asyncio
import logging
from subprocess import DEVNULL


class SoundSystem:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')

        # Use absolute path - we know exactly where it is
        self.sound_dir = "/home/pi/lister_sound_system/sounds"

        # Default sounds mapping with absolute paths
        self.sounds = {
            'print_start': os.path.join(self.sound_dir, 'print_start.wav'),
            'print_complete': os.path.join(self.sound_dir, 'print_complete.wav'),
            'print_cancel': os.path.join(self.sound_dir, 'print_cancel.wav'),
            'error': os.path.join(self.sound_dir, 'error.wav'),
            'startup': os.path.join(self.sound_dir, 'startup.wav')
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

        # Try with and without .wav extension
        possible_paths = [
            os.path.join(self.sound_dir, sound_spec),
            os.path.join(self.sound_dir, f"{sound_spec}.wav")
        ]

        # Try each possible path
        for path in possible_paths:
            if self._verify_sound_file(path):
                return path

        return None

    cmd_SOUND_LIST_help = "List all available sounds"

    def cmd_SOUND_LIST(self, gcmd):
        """List all available sounds"""
        msg = ["Available sounds:\n"]

        # List predefined sounds
        msg.append("Predefined sounds:")
        for sound_id, path in sorted(self.sounds.items()):
            status = "✓" if self._verify_sound_file(path) else "✗"
            msg.append(f"{status} {sound_id}: {path}")

        # List all WAV files in sound directory
        msg.append("\nAvailable WAV files:")
        if os.path.exists(self.sound_dir):
            wav_files = [f for f in os.listdir(self.sound_dir) if f.endswith('.wav')]
            for wav_file in sorted(wav_files):
                path = os.path.join(self.sound_dir, wav_file)
                status = "✓" if self._verify_sound_file(path) else "✗"
                msg.append(f"{status} {wav_file}")

        msg.append(f"\nSound directory: {self.sound_dir}")
        gcmd.respond_info("\n".join(msg))

    cmd_PLAY_SOUND_help = "Play a sound file (e.g., PLAY_SOUND SOUND=print_complete)"

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
                f"Neither a predefined sound nor a valid WAV file."
            )

        # Verify sound file exists
        if not self._verify_sound_file(sound_path):
            raise gcmd.error(f"Sound file not accessible: {sound_path}")

        # Schedule sound playback asynchronously
        reactor = self.printer.get_reactor()
        reactor.register_async_callback(
            lambda e: self._play_sound_async(sound_path)
        )
        gcmd.respond_info(f"Playing sound: {sound_path}")

    async def _play_sound_async(self, sound_path):
        """Asynchronously play a sound file using aplay"""
        if not self.aplay_path:
            logging.error("SoundSystem: aplay not available")
            return

        try:
            process = await asyncio.create_subprocess_exec(
                self.aplay_path, sound_path,
                stdout=DEVNULL,
                stderr=DEVNULL
            )
            await process.wait()
        except Exception as e:
            logging.exception(f"Error playing sound {sound_path}: {str(e)}")


def load_config(config):
    return SoundSystem(config)