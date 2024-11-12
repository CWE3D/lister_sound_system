import os
import logging
import subprocess
from pathlib import Path
from threading import Thread


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

        # Find aplay and amixer
        self.aplay_path = self._get_aplay_path()
        self.amixer_path = self._get_amixer_path()
        if not self.aplay_path:
            self.logger.error("'aplay' not found in system path")
            return
        if not self.amixer_path:
            self.logger.error("'amixer' not found in system path")
            return

        # Register commands
        self.gcode.register_command('PLAY_SOUND', self.cmd_PLAY_SOUND,
                                    desc="Play a sound file (PLAY_SOUND SOUND=filename)")
        self.gcode.register_command('SOUND_LIST', self.cmd_SOUND_LIST,
                                    desc="List available sound files")
        self.gcode.register_command('VOLUME_UP', self.cmd_VOLUME_UP,
                                    desc="Increase PCM volume by 2%")
        self.gcode.register_command('VOLUME_DOWN', self.cmd_VOLUME_DOWN,
                                    desc="Decrease PCM volume by 2%")

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

    def _find_sound_file(self, sound_name: str) -> Path:
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

    def _adjust_volume(self, increase: bool):
        """Adjust PCM volume"""
        if not self.amixer_path:
            self.logger.error("amixer not available")
            return False

        try:
            cmd = [self.amixer_path, 'set', 'PCM', '2%+' if increase else '2%-']
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )

            if process.returncode != 0:
                self.logger.error(f"Volume adjustment failed: {process.stderr}")
                return False

            # Extract current volume from amixer output
            output = process.stdout
            if 'Playback' in output:
                try:
                    volume = output.split('[')[1].split('%')[0]
                    return f"Volume set to {volume}%"
                except:
                    return "Volume adjusted"
            return "Volume adjusted"

        except subprocess.TimeoutExpired:
            self.logger.error("Volume adjustment timeout")
            return False
        except Exception as e:
            self.logger.error(f"Volume adjustment error: {e}")
            return False

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
        result = self._adjust_volume(True)
        if result:
            gcmd.respond_info(result)
        else:
            raise gcmd.error("Volume adjustment failed")

    def cmd_VOLUME_DOWN(self, gcmd):
        """Decrease PCM volume"""
        result = self._adjust_volume(False)
        if result:
            gcmd.respond_info(result)
        else:
            raise gcmd.error("Volume adjustment failed")


def load_config(config):
    return SoundSystem(config)