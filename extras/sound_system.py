import logging
import subprocess
from pathlib import Path
from threading import Thread
from typing import Optional
import psutil
import signal
import os


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

        # Stream handling
        self.mpv_path = self._get_mpv_path()
        self._stream_process = None
        
        # Get streams from config
        default_streams = "\n".join([
            "https://stream.radioparadise.com/mellow-320",
            "https://stream.radioparadise.com/rock-320",
            "https://stream.radioparadise.com/eclectic-320"
        ])
        streams_config = config.get('radio_streams', default_streams)
        self.stream_urls = [url.strip() for url in streams_config.splitlines() if url.strip()]
        
        if not self.stream_urls:
            self.logger.warning("No radio streams configured")
        
        self.current_stream_index = 0
        self.last_stream_stop_time = None
        self.stream_switch_timeout = config.getint('stream_switch_timeout', 60)  # Default 60 seconds

        # Register commands
        self.gcode.register_command('PLAY_SOUND', self.cmd_PLAY_SOUND,
                                    desc="Play a sound file (PLAY_SOUND SOUND=filename)")
        self.gcode.register_command('SOUND_LIST', self.cmd_SOUND_LIST,
                                    desc="List available sound files")
        self.gcode.register_command('VOLUME_UP', self.cmd_VOLUME_UP,
                                    desc=f"Increase PCM volume by {self.volume_step}%")
        self.gcode.register_command('VOLUME_DOWN', self.cmd_VOLUME_DOWN,
                                    desc=f"Decrease PCM volume by {self.volume_step}%")
        self.gcode.register_command('STREAM_RADIO', self.cmd_STREAM_RADIO,
                                  desc="Toggle radio stream playback")

        # Add sound playback state tracking
        self._sound_playing = False

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
            # subprocess.run('play -n synth 0.2 sine 600', capture_output=True, text=True, timeout=0.22)

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
            # Set flag before starting playback
            self._sound_playing = True
            
            process = subprocess.Popen(
                [self.aplay_path, '-D', 'plughw:0,0', str(sound_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait for the process to complete
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
        finally:
            # Clear flag after playback is complete or on error
            self._sound_playing = False

    def cmd_PLAY_SOUND(self, gcmd):
        """Handle PLAY_SOUND command"""
        if not self.aplay_path:
            raise gcmd.error("aplay not available")

        # Check if NOW flag is set
        force_now = gcmd.get_int('NOW', 0)

        # Strict check for ongoing playback, unless NOW is set
        if self._sound_playing and not force_now:
            self.logger.info("Sound already playing, ignoring new request")
            gcmd.respond_info("Sound already playing, request ignored")
            return

        sound_name = gcmd.get('SOUND')
        if not sound_name:
            raise gcmd.error("Missing SOUND parameter")

        sound_path = self._find_sound_file(sound_name)
        if not sound_path:
            raise gcmd.error(f"Sound file not found: {sound_name}")

        # If NOW is set and there's a sound playing, kill existing playback
        if force_now and self._sound_playing:
            self.logger.info("Force playing new sound, stopping current playback")
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'] == 'aplay':
                        os.kill(proc.info['pid'], signal.SIGTERM)
                        self.logger.info(f"Killed existing aplay process: {proc.info['pid']}")
                self._sound_playing = False
            except Exception as e:
                self.logger.error(f"Error killing existing sound: {e}")

        # Start playback in a separate thread
        def start_playback(eventtime):
            # Double-check the flag right before starting the thread, unless NOW is set
            if not self._sound_playing or force_now:
                Thread(target=self._play_sound_thread,
                      args=(sound_path,),
                      daemon=True).start()
                gcmd.respond_info(f"Playing sound: {sound_path.name}")
            return False  # Don't reschedule

        reactor = self.printer.get_reactor()
        reactor.register_callback(start_playback)

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

    def _get_mpv_path(self):
        """Find mpv executable path"""
        try:
            return subprocess.check_output(['which', 'mpv'],
                                        text=True).strip()
        except subprocess.SubprocessError as e:
            self.logger.error(f"Error finding mpv: {e}")
            return None

    def _kill_existing_stream(self):
        """Kill any existing mpv processes"""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] == 'mpv':
                    os.kill(proc.info['pid'], signal.SIGTERM)
                    self.logger.info(f"Killed existing mpv process: {proc.info['pid']}")
        except Exception as e:
            self.logger.error(f"Error killing existing stream: {e}")

    def _start_stream_thread(self, url):
        """Handle stream playback in a separate thread"""
        try:
            # Kill any existing stream first
            if self._stream_process:
                self._stream_process.terminate()
                self._stream_process.wait()
            
            self._kill_existing_stream()  # Cleanup any orphaned processes
            
            # Start new stream
            self._stream_process = subprocess.Popen(
                [self.mpv_path, url, '--no-video', '--no-terminal'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.logger.info(f"Started streaming: {url}")
            
        except Exception as e:
            self.logger.error(f"Stream thread error: {e}")
            self._stream_process = None

    def cmd_STREAM_RADIO(self, gcmd):
        """Handle STREAM_RADIO command"""
        if not self.mpv_path:
            raise gcmd.error("mpv not available")

        current_time = self.printer.get_reactor().monotonic()

        # If stream is running, stop it
        if self._stream_process:
            try:
                self._stream_process.terminate()
                self._stream_process.wait()
                self._stream_process = None
                self._kill_existing_stream()  # Cleanup any orphaned processes
                self.last_stream_stop_time = current_time
                gcmd.respond_info("Stopped radio stream")
                return
            except Exception as e:
                self.logger.error(f"Error stopping stream: {e}")
                self._stream_process = None

        # Check if we should move to next stream or reset to current
        if (self.last_stream_stop_time is not None and 
            current_time - self.last_stream_stop_time <= self.stream_switch_timeout):
            # Within timeout, move to next stream
            self.current_stream_index = (self.current_stream_index + 1) % len(self.stream_urls)
        elif self.last_stream_stop_time is not None:
            # Beyond timeout, keep current stream
            self.logger.info("Beyond timeout, keeping current stream")

        # Get current URL
        url = self.stream_urls[self.current_stream_index]
        
        def start_stream(eventtime):
            Thread(target=self._start_stream_thread,
                  args=(url,),
                  daemon=True).start()
            return False  # Don't reschedule

        reactor = self.printer.get_reactor()
        reactor.register_callback(start_stream)
        gcmd.respond_info(f"Starting radio stream ({self.current_stream_index + 1}/{len(self.stream_urls)}): {url}")


def load_config(config):
    return SoundSystem(config)