import os
import logging
import asyncio
import pathlib
from typing import Dict, List, Optional, Any


class SoundSystemService:
    def __init__(self, config):
        self.server = config.get_server()
        self.klippy = self.server.lookup_component('klippy_apis')

        # Get configuration and set up paths
        default_sound_dir = os.path.join(
            os.path.expanduser('~'),
            'lister_sound_system',
            'sounds'
        )
        self.sound_dir = config.get('sound_directory', default_sound_dir)

        # Cached sound list
        self._sound_cache: Dict[str, str] = {}
        self._last_scan_time = 0

        # Register endpoints
        self.server.register_endpoint(
            "/server/sound/list",
            ['GET'],
            self._handle_list_request
        )
        self.server.register_endpoint(
            "/server/sound/play",
            ['POST'],
            self._handle_play_request
        )
        self.server.register_endpoint(
            "/server/sound/scan",
            ['POST'],
            self._handle_scan_request
        )
        self.server.register_endpoint(
            "/server/sound/info",
            ['GET'],
            self._handle_info_request
        )

        # Register notification methods
        self.server.register_notification("sound_system:sound_played")
        self.server.register_notification("sound_system:sounds_updated")

        # Register events
        self.server.register_event_handler(
            "server:klippy_ready",
            self._handle_ready
        )

    async def _handle_ready(self) -> None:
        """Initialize when Klippy is ready"""
        logging.info("Sound System Service Ready")
        await self._scan_sounds()  # Initial scan of sounds

    def _verify_sound_file(self, path: str) -> bool:
        """Verify if file exists and is a valid WAV file"""
        try:
            if not os.path.isfile(path):
                return False
            # Basic WAV header check
            with open(path, 'rb') as f:
                header = f.read(4)
                return header == b'RIFF'
        except Exception:
            return False

    async def _scan_sounds(self) -> Dict[str, str]:
        """Scan sound directory and update cache"""
        sounds: Dict[str, str] = {}
        try:
            # Get predefined sounds from Klipper plugin
            result = await self.klippy.run_method("gcode/script", {"script": "SOUND_LIST"})

            # Scan directory for all WAV files
            sound_path = pathlib.Path(self.sound_dir)
            if sound_path.exists():
                for file_path in sound_path.glob("**/*.wav"):
                    if self._verify_sound_file(str(file_path)):
                        sound_id = file_path.stem
                        sounds[sound_id] = str(file_path)

            self._sound_cache = sounds
            self._last_scan_time = asyncio.get_event_loop().time()

            # Notify clients of updated sound list
            await self.server.send_event(
                "sound_system:sounds_updated",
                {'sounds': sounds}
            )

        except Exception as e:
            logging.exception(f"Error scanning sounds: {str(e)}")

        return sounds

    async def _handle_list_request(self, web_request) -> Dict[str, Any]:
        """Handle request to list available sounds"""
        # Rescan if cache is older than 5 minutes
        current_time = asyncio.get_event_loop().time()
        if current_time - self._last_scan_time > 300:  # 5 minutes
            await self._scan_sounds()

        return {
            'sounds': self._sound_cache,
            'sound_dir': self.sound_dir,
            'last_scan': self._last_scan_time
        }

    async def _handle_play_request(self, web_request) -> Dict[str, Any]:
        """Handle request to play a sound"""
        sound = web_request.get_str('sound')

        try:
            # Attempt to play sound through Klipper
            await self.klippy.run_method(
                "gcode/script",
                {"script": f"PLAY_SOUND SOUND={sound}"}
            )

            # Notify clients that sound was played
            await self.server.send_event(
                "sound_system:sound_played",
                {'sound': sound}
            )

            return {
                'status': 'success',
                'sound': sound
            }
        except Exception as e:
            raise self.server.error(f"Failed to play sound: {str(e)}")

    async def _handle_scan_request(self, web_request) -> Dict[str, Any]:
        """Handle request to rescan sounds directory"""
        sounds = await self._scan_sounds()
        return {
            'status': 'success',
            'sounds': sounds,
            'sound_dir': self.sound_dir,
            'last_scan': self._last_scan_time
        }

    async def _handle_info_request(self, web_request) -> Dict[str, Any]:
        """Return information about the sound system"""
        audio_info = {'devices': []}

        try:
            # Get audio device information
            proc = await asyncio.create_subprocess_exec(
                'aplay', '-l',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            if stdout:
                audio_info['devices'] = [
                    line.decode().strip()
                    for line in stdout.splitlines()
                    if b'card' in line
                ]
        except Exception as e:
            logging.exception(f"Error getting audio info: {str(e)}")

        return {
            'status': 'online',
            'sound_dir': self.sound_dir,
            'sound_count': len(self._sound_cache),
            'last_scan': self._last_scan_time,
            'audio_system': audio_info
        }

    async def close(self) -> None:
        """Clean up resources on shutdown"""
        self._sound_cache.clear()


def load_component(config):
    return SoundSystemService(config)