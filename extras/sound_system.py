import os
import logging
import subprocess
from pathlib import Path
from threading import Thread
from typing import Optional


class SoundSystem:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')

        # Set up logging
        self.logger = self._setup_logger()
        self.logger.info("Initializing Sound System...")

        # Configure paths
        self.sound_dir = Path(config.get('sound_directory',
                                         '/home/pi/lister_sound_system/sounds')).resolve()
        self.logger.info(f"Sound directory: {self.sound_dir}")

        # Volume control configuration
        self.volume_step = config.getint('volume_step', 5)  # Default 5% steps
        self.max_volume = config.getint('max_volume', 100)
        self.min_volume = config.getint('min_volume', 0)
        self._current_volume = None  # Will be initialized when first needed

        # Find aplay and amixer
        self.aplay_path = self._get_aplay_path()
        self.amixer_path = self._get_amixer_path()
        if not self.aplay_path:
            self.logger.error("'aplay' not found in system path")
            return
        if not self.amixer_path:
            self.logger.error("'amixer' not found in system path")
            return

        # Initialize volume state
        self._init_volume_state()

        # Register commands
        self.gcode.register_command('PLAY_SOUND', self.cmd_PLAY_SOUND,
                                    desc="Play a sound file (PLAY_SOUND SOUND=filename)")
        self.gcode.register_command('SOUND_LIST', self.cmd_SOUND_LIST,
                                    desc="List available sound files")
        self.gcode.register_command('VOLUME_UP', self.cmd_VOLUME_UP,
                                    desc=f"Increase PCM volume by {self.volume_step}%")
        self.gcode.register_command('VOLUME_DOWN', self.cmd_VOLUME_DOWN,
                                    desc=f"Decrease PCM volume by {self.volume_step}%")

    def _init_volume_state(self):
        """Initialize volume state by getting current system volume"""
        try:
            cmd = [self.amixer_path, '-M', 'sget', 'PCM']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # Parse the output to get current volume percentage
                output = result.stdout
                if 'Mono:' in output:
                    try:
                        # Find the line with 'Mono: Playback'
                        mono_line = [line for line in output.split('\n') if 'Mono:' in line][0]
                        # Extract the percentage value
                        percentage = int(mono_line.split('[')[1].split('%]')[0])
                        self._current_volume = percentage
                        self.logger.info(f"Initial volume state: {self._current_volume}%")
                    except (IndexError, ValueError) as e:
                        self.logger.error(f"Error parsing volume output: {e}")
                        self._current_volume = 50  # Default to 50% if parsing fails
        except Exception as e:
            self.logger.error(f"Error getting initial volume state: {e}")
            self._current_volume = 50  # Default to 50% if command fails

    def _set_volume(self, volume: int) -> bool:
        """Set absolute volume level"""
        volume = max(self.min_volume, min(self.max_volume, volume))  # Clamp value
        try:
            cmd = [self.amixer_path, '-M', 'sset', 'PCM', f'{volume}%']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                self._current_volume = volume
                return True
            else:
                self.logger.error(f"Volume set failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("Volume set timeout")
            return False
        except Exception as e:
            self.logger.error(f"Volume set error: {e}")
            return False

    def _setup_logger(self):
        """Configure dedicated logger for sound system"""
        logger = logging.getLogger('SoundSystem')
        logger.setLevel(logging.INFO)

        # Create file handler
        log_path = Path('/home/pi/printer_data/logs/sound_system.log')
        handler = logging.FileHandler(log_path)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'))

        logger.addHandler(handler)
        return logger

    def _get_aplay_path(self):
        """Find aplay executable path"""
        try:
            return subprocess.check_output(['which', 'aplay'],
                                           text=True).strip()
        except subprocess.SubprocessError as e:
            self.logger.error(f"Error finding aplay: {e}")
            return None

    def _get_amixer_path(self):
        """Find amixer executable path"""
        try:
            return subprocess.check_output(['which', 'amixer'],
                                           text=True).strip()
        except subprocess.SubprocessError as e:
            self.logger.error(f"Error finding amixer: {e}")
            return None

    def _verify_sound_file(self, path: Path) -> bool:
        """Verify file exists and is a valid WAV"""
        try:
            if not path.is_file():
                return False

            # Basic WAV header check
            with open(path, 'rb') as f:
                header = f.read(12)
                return (header.startswith(b'RIFF') and
                        header[8:12] == b'WAVE')
        except Exception as e:
            self.logger.error(f"Error verifying {path}: {e}")
            return False

    def _find_sound_file(self, sound_name: str) -> Optional[Path]:
        """Find sound file by name, with or without .wav extension"""
        sound_path = self.sound_dir / sound_name

        # Try exact name first
        if self._verify_sound_file(sound_path):
            return sound_path

        # Try with .wav extension
        wav_path = sound_path.with_suffix('.wav')
        if self._verify_sound_file(wav_path):
            return wav_path

        return None

    def _play_sound_thread(self, sound_path: Path):
        """Handle sound playback in a separate thread"""
        try:
            # Use subprocess.Popen instead of os.popen for better process management
            process = subprocess.Popen(
                [self.aplay_path, '-D', 'plughw:0,0', str(sound_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Non-blocking wait with timeout
            try:
                stdout, stderr = process.communicate(timeout=30)  # 30 second timeout
                if process.returncode != 0:
                    self.logger.error(
                        f"Play failed (code {process.returncode}): {stderr.decode()}")
                else:
                    self.logger.debug("Play completed successfully")

            except subprocess.TimeoutExpired:
                self.logger.error("Play timeout - killing process")
                process.kill()
                process.communicate()  # Clean up

        except Exception as e:
            self.logger.error(f"Play thread error: {e}")

    def cmd_PLAY_SOUND(self, gcmd):
        """Handle PLAY_SOUND command"""
        if not self.aplay_path:
            raise gcmd.error("aplay not available")

        sound_name = gcmd.get('SOUND')
        if not sound_name:
            raise gcmd.error("Missing SOUND parameter")

        sound_path = self._find_sound_file(sound_name)
        if not sound_path:
            raise gcmd.error(f"Sound file not found: {sound_name}")

        # Start playback in a separate thread
        def start_playback(eventtime):
            Thread(target=self._play_sound_thread,
                   args=(sound_path,),
                   daemon=True).start()
            return False  # Don't reschedule

        reactor = self.printer.get_reactor()
        reactor.register_callback(start_playback)
        gcmd.respond_info(f"Playing sound: {sound_path.name}")

    def cmd_SOUND_LIST(self, gcmd):
        """List available sound files"""
        if not self.sound_dir.exists():
            gcmd.respond_info(f"Sound directory not found: {self.sound_dir}")
            return

        msg = [f"Sound directory: {self.sound_dir}\n", "Available sounds:"]

        try:
            for sound_file in sorted(self.sound_dir.glob("*.wav")):
                status = "✓" if self._verify_sound_file(sound_file) else "✗"
                msg.append(f"{status} {sound_file.name}")
        except Exception as e:
            self.logger.error(f"Error listing sounds: {e}")
            msg.append(f"Error: {e}")

        gcmd.respond_info("\n".join(msg))

    def cmd_VOLUME_UP(self, gcmd):
        """Increase PCM volume"""
        if self._current_volume is None:
            self._init_volume_state()

        new_volume = self._current_volume + self.volume_step
        if self._set_volume(new_volume):
            gcmd.respond_info(f"Volume set to {self._current_volume}%")
        else:
            raise gcmd.error("Volume adjustment failed")

    def cmd_VOLUME_DOWN(self, gcmd):
        """Decrease PCM volume"""
        if self._current_volume is None:
            self._init_volume_state()

        new_volume = self._current_volume - self.volume_step
        if self._set_volume(new_volume):
            gcmd.respond_info(f"Volume set to {self._current_volume}%")
        else:
            raise gcmd.error("Volume adjustment failed")


def load_config(config):
    return SoundSystem(config)