import os
import asyncio
import logging
from subprocess import DEVNULL
from datetime import datetime

class SoundSystem:
    def __init__(self, config):
        self._setup_logging()
        self.logger.info("Initializing Lister Sound System...")

        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')

        # Register config option properly
        self.sound_dir = config.get('sound_directory',
                                    "/home/pi/lister_sound_system/sounds")
        self.logger.info(f"Sound directory set to: {self.sound_dir}")

        # Default sounds mapping with absolute paths
        self.sounds = {
            'startup': os.path.join(self.sound_dir, 'startup.wav')
        }
        self.logger.info(f"Registered default sounds: {list(self.sounds.keys())}")

        # Tell the OS to locate aplay
        self.aplay_path = os.popen('which aplay').read().strip()
        if not self.aplay_path:
            self.logger.error("'aplay' not found in system path")
        else:
            self.logger.info(f"Found aplay at: {self.aplay_path}")

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

    def get_status(self, eventtime):
        return {
            'sound_directory': self.sound_dir
        }

    def _setup_logging(self):
        """Set up dedicated logging for the sound system"""
        log_file = "/home/pi/printer_data/logs/lister_sound_system.log"

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Create file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)

        # Create logger
        self.logger = logging.getLogger('ListerSoundSystem')
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(file_handler)

        # Log startup
        self.logger.info("=" * 50)
        self.logger.info("Sound System Logger Initialized")
        self.logger.info("=" * 50)

    def _verify_sound_file(self, sound_path):
        """Verify sound file exists and is accessible"""
        self.logger.debug(f"Verifying sound file: {sound_path}")
        exists = os.path.isfile(sound_path)
        readable = os.access(sound_path, os.R_OK)
        self.logger.debug(f"File exists: {exists}, Is readable: {readable}")
        return exists and readable

    def _resolve_sound_path(self, sound_spec):
        """Resolve sound specification to an actual file path"""
        self.logger.debug(f"Resolving sound path for: {sound_spec}")

        # Check predefined sounds
        if sound_spec in self.sounds:
            self.logger.debug(f"Found predefined sound: {self.sounds[sound_spec]}")
            return self.sounds[sound_spec]

        # Try with and without .wav extension
        possible_paths = [
            os.path.join(self.sound_dir, sound_spec),
            os.path.join(self.sound_dir, f"{sound_spec}.wav")
        ]

        self.logger.debug(f"Checking possible paths: {possible_paths}")

        # Try each possible path
        for path in possible_paths:
            if self._verify_sound_file(path):
                self.logger.debug(f"Found valid sound file at: {path}")
                return path

        self.logger.warning(f"No valid sound file found for: {sound_spec}")
        return None

    cmd_PLAY_SOUND_help = "Play a sound file (e.g., PLAY_SOUND SOUND=print_complete)"

    def cmd_PLAY_SOUND(self, gcmd):
        """Handle PLAY_SOUND command"""
        self.logger.info("Received PLAY_SOUND command")

        sound_spec = gcmd.get('SOUND')
        self.logger.info(f"Requested sound: {sound_spec}")

        if not sound_spec:
            self.logger.error("No sound specified")
            raise gcmd.error("No sound specified")

        # Resolve the sound path
        sound_path = self._resolve_sound_path(sound_spec)

        if not sound_path:
            error_msg = f"Could not find sound '{sound_spec}'. Neither a predefined sound nor a valid WAV file."
            self.logger.error(error_msg)
            raise gcmd.error(error_msg)

        # Verify sound file exists
        if not self._verify_sound_file(sound_path):
            error_msg = f"Sound file not accessible: {sound_path}"
            self.logger.error(error_msg)
            raise gcmd.error(error_msg)

        # Log playback attempt
        self.logger.info(f"Attempting to play sound: {sound_path}")

        # Use synchronous playback instead
        def play_sound(eventtime):
            self.logger.info(f"Starting sound playback for: {sound_path}")
            try:
                # Execute aplay directly
                cmd = [self.aplay_path, '-D', 'plughw:0,0', sound_path]
                self.logger.debug(f"Executing command: {' '.join(cmd)}")

                process = os.popen(f"{' '.join(cmd)} 2>&1")
                output = process.read()
                return_code = process.close()

                if output:
                    self.logger.debug(f"aplay output: {output}")

                if return_code is not None:
                    self.logger.error(f"aplay failed with return code {return_code}")
                else:
                    self.logger.info("Sound playback completed successfully")

            except Exception as e:
                self.logger.exception(f"Error playing sound {sound_path}: {str(e)}")

        # Schedule the synchronous playback
        reactor = self.printer.get_reactor()
        reactor.register_callback(play_sound)

        self.logger.info("Sound playback scheduled")
        gcmd.respond_info(f"Playing sound: {sound_path}")

    async def _play_sound_async(self, sound_path):
        """Asynchronously play a sound file using aplay"""
        self.logger.info(f"Starting async sound playback for: {sound_path}")

        # Log user and group information
        import pwd
        import grp
        current_uid = os.getuid()
        current_gid = os.getgid()
        current_user = pwd.getpwuid(current_uid).pw_name
        current_groups = [g.gr_name for g in grp.getgrall() if current_user in g.gr_mem]

        self.logger.info(f"Running as user: {current_user} (UID: {current_uid})")
        self.logger.info(f"Primary group ID: {current_gid}")
        self.logger.info(f"User groups: {current_groups}")

        if not self.aplay_path:
            self.logger.error("aplay not available")
            return

        try:
            # Use the exact same device specification that worked with speaker-test
            cmd = [
                self.aplay_path,
                '-D', 'plughw:0,0',
                sound_path
            ]
            self.logger.debug(f"Executing command: {' '.join(cmd)}")

            # Create process with pipe for output
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for completion and get output
            stdout, stderr = await process.communicate()
            return_code = process.returncode

            # Log all output
            if stdout:
                self.logger.debug(f"aplay stdout: {stdout.decode()}")
            if stderr:
                self.logger.warning(f"aplay stderr: {stderr.decode()}")

            self.logger.info(f"Sound playback completed with return code: {return_code}")

            if return_code != 0:
                self.logger.error(f"aplay failed with return code {return_code}")

        except Exception as e:
            self.logger.exception(f"Error playing sound {sound_path}: {str(e)}")

    cmd_SOUND_LIST_help = "List all available sounds"

    def cmd_SOUND_LIST(self, gcmd):
        """List all available sounds"""
        self.logger.info("Executing SOUND_LIST command")

        msg = ["Available sounds:\n"]

        # List predefined sounds
        self.logger.debug("Checking predefined sounds...")
        msg.append("Predefined sounds:")
        for sound_id, path in sorted(self.sounds.items()):
            status = "✓" if self._verify_sound_file(path) else "✗"
            msg.append(f"{status} {sound_id}: {path}")
            self.logger.debug(f"Predefined sound {sound_id}: {status} at {path}")

        # List all WAV files in sound directory
        self.logger.debug(f"Scanning sound directory: {self.sound_dir}")
        msg.append("\nAvailable WAV files:")
        if os.path.exists(self.sound_dir):
            wav_files = [f for f in os.listdir(self.sound_dir) if f.endswith('.wav')]
            for wav_file in sorted(wav_files):
                path = os.path.join(self.sound_dir, wav_file)
                status = "✓" if self._verify_sound_file(path) else "✗"
                msg.append(f"{status} {wav_file}")
                self.logger.debug(f"WAV file {wav_file}: {status} at {path}")
        else:
            self.logger.warning(f"Sound directory not found: {self.sound_dir}")

        msg.append(f"\nSound directory: {self.sound_dir}")

        response = "\n".join(msg)
        self.logger.info("SOUND_LIST command completed")
        gcmd.respond_info(response)


def load_config(config):
    return SoundSystem(config)