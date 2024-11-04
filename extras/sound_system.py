def __init__(self, config):
    self.printer = config.get_printer()
    self.gcode = self.printer.lookup_object('gcode')

    # Ensure home directory is properly expanded
    default_sound_dir = os.path.expanduser(os.path.join('~', 'lister_sound_system', 'sounds'))
    self.sound_dir = os.path.expanduser(config.get('sound_directory', default_sound_dir))

    # Default sounds mapping with expanded paths
    self.sounds = {
        'print_start': os.path.join(self.sound_dir, 'print_start.wav'),
        'print_complete': os.path.join(self.sound_dir, 'print_complete.wav'),
        'print_cancel': os.path.join(self.sound_dir, 'print_cancel.wav'),
        'error': os.path.join(self.sound_dir, 'error.wav')
    }


def _verify_sound_file(self, sound_path):
    """Verify sound file exists and is accessible"""
    # Ensure path is expanded
    expanded_path = os.path.expanduser(sound_path)
    return os.path.isfile(expanded_path) and os.access(expanded_path, os.R_OK)


def _resolve_sound_path(self, sound_spec):
    """
    Resolve sound specification to an actual file path.
    Can handle both predefined sounds and direct file paths.
    """
    # First check if it's a predefined sound
    if sound_spec in self.sounds:
        return self.sounds[sound_spec]

    # List of possible paths to try (with expansion)
    possible_paths = [
        os.path.expanduser(sound_spec),  # Expand if absolute path
        os.path.join(self.sound_dir, f"{sound_spec}.wav"),  # Without .wav extension
        os.path.join(self.sound_dir, sound_spec),  # With or without .wav extension
        os.path.expanduser(os.path.join('~', sound_spec))  # Expand if relative to home
    ]

    # Try each possible path
    for path in possible_paths:
        if self._verify_sound_file(path):
            return path

    # If we get here, no valid sound file was found
    return None