#!/bin/bash

# The install script for lister_sound_system
# Define colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Define paths
PLUGIN_DIR="/home/pi/lister_sound_system"
KLIPPER_DIR="/home/pi/klipper"
MOONRAKER_DIR="/home/pi/moonraker"
KLIPPY_ENV="/home/pi/klippy-env"
LOG_DIR="/home/pi/printer_data/logs"
CONFIG_DIR="/home/pi/printer_data/config"
SOUND_DIR="${PLUGIN_DIR}/sounds"
INSTALL_LOG="${LOG_DIR}/sound_system_install.log"
MOONRAKER_CONF="${CONFIG_DIR}/moonraker.conf"

# Update manager configuration block
read -r -d '' UPDATE_MANAGER_CONFIG << 'EOL'

[update_manager lister_sound_system]
type: git_repo
path: ~/lister_sound_system
origin: https://github.com/CWE3D/lister_sound_system.git
is_system_service: False
primary_branch: main
managed_services: klipper moonraker
install_script: install.sh
EOL

# Function to log messages
log_message() {
    echo -e "${GREEN}$(date): $1${NC}" | tee -a "$INSTALL_LOG"
}

log_error() {
    echo -e "${RED}$(date): $1${NC}" | tee -a "$INSTALL_LOG"
}

log_warning() {
    echo -e "${YELLOW}$(date): $1${NC}" | tee -a "$INSTALL_LOG"
}

# Function to backup moonraker.conf
backup_moonraker_conf() {
    local backup_file="${MOONRAKER_CONF}.$(date +%Y%m%d_%H%M%S).backup"
    if cp "$MOONRAKER_CONF" "$backup_file"; then
        log_message "Created backup of moonraker.conf at $backup_file"
        return 0
    else
        log_error "Failed to create backup of moonraker.conf"
        return 1
    fi
}

# Function to check if update_manager section exists
section_exists() {
    if grep -q "^\[update_manager lister_sound_system\]" "$MOONRAKER_CONF"; then
        return 0
    else
        return 1
    fi
}

# Function to update moonraker.conf
update_moonraker_conf() {
    log_message "Checking moonraker.conf configuration..."

    if [ ! -f "$MOONRAKER_CONF" ]; then
        log_error "moonraker.conf not found at $MOONRAKER_CONF"
        return 1
    fi

    backup_moonraker_conf || return 1

    if ! section_exists; then
        log_message "Adding [update_manager lister_sound_system] configuration..."
        echo "$UPDATE_MANAGER_CONFIG" >> "$MOONRAKER_CONF"
        log_message "moonraker.conf updated successfully"
    else
        log_warning "[update_manager lister_sound_system] section already exists in moonraker.conf"
    fi
}

# Check if required directories exist
check_directories() {
    local missing_dirs=0

    for dir in "$KLIPPER_DIR" "$MOONRAKER_DIR" "$KLIPPY_ENV"; do
        if [ ! -d "$dir" ]; then
            log_error "Error: Directory $dir does not exist"
            missing_dirs=1
        fi
    done

    if [ $missing_dirs -eq 1 ]; then
        exit 1
    fi
}

# Install system dependencies
install_system_deps() {
    log_message "Installing system dependencies..."
    sudo apt-get update
    if ! sudo apt-get install -y alsa-utils; then
        log_error "Error: Failed to install system dependencies"
        exit 1
    fi
}

# Install Python dependencies
install_python_deps() {
    log_message "Installing Python dependencies..."
    
    # Install dependencies in Klippy virtual environment
    if ! "${KLIPPY_ENV}/bin/pip" install -r "${PLUGIN_DIR}/requirement.txt"; then
        log_error "Error: Failed to install Python dependencies in Klippy environment"
        return 1
    fi
    
    # Install dependencies in Moonraker virtual environment
    if ! "/home/pi/moonraker-env/bin/pip" install -r "${PLUGIN_DIR}/requirement.txt"; then
        log_error "Error: Failed to install Python dependencies in Moonraker environment"
        return 1
    fi
    
    log_message "Python dependencies installed successfully"
}

# Create sound directory and ensure proper structure
setup_sound_directory() {
    log_message "Setting up sound directory..."

    # Create sounds directory if it doesn't exist
    if [ ! -d "${SOUND_DIR}" ]; then
        mkdir -p "${SOUND_DIR}"
        log_message "Created sounds directory at ${SOUND_DIR}"
    fi

    # Set appropriate permissions
    sudo chown -R pi:pi "${SOUND_DIR}"
    sudo chmod -R 755 "${SOUND_DIR}"
    log_message "Set permissions for sound directory"

    # Check for default sounds
    if [ -z "$(ls -A ${SOUND_DIR})" ]; then
        log_warning "Sound directory is empty. Please add .wav files to ${SOUND_DIR}"
    else
        log_message "Found existing sounds in ${SOUND_DIR}"
    fi
}

# Test audio system
test_audio_system() {
    log_message "Testing audio system..."
    if ! aplay -l | grep -q "card"; then
        log_warning "No audio devices found. Sound playback may not work."
    else
        log_message "Audio device(s) found:"
        aplay -l | grep "card" | tee -a "$INSTALL_LOG"
    fi
}

# Setup Klipper plugin symlink
setup_klipper_plugin() {
    log_message "Setting up Klipper plugin symlink..."
    EXTRAS_DIR="${PLUGIN_DIR}/extras"
    KLIPPER_EXTRAS_DIR="${KLIPPER_DIR}/klippy/extras"

    if [ ! -d "$KLIPPER_EXTRAS_DIR" ]; then
        log_error "Error: Klipper extras directory does not exist"
        exit 1
    fi

    if [ -f "${EXTRAS_DIR}/sound_system.py" ]; then
        # Remove existing symlink if it exists
        if [ -L "${KLIPPER_EXTRAS_DIR}/sound_system.py" ]; then
            rm "${KLIPPER_EXTRAS_DIR}/sound_system.py"
        fi

        # Create new symlink
        if ! ln -s "${EXTRAS_DIR}/sound_system.py" "${KLIPPER_EXTRAS_DIR}/sound_system.py"; then
            log_error "Error: Failed to create Klipper plugin symlink"
            exit 1
        fi
        log_message "Klipper plugin symlink created successfully"
    else
        log_error "Error: sound_system.py not found in ${EXTRAS_DIR}"
        exit 1
    fi
}

# Setup Moonraker component symlink
setup_moonraker_component() {
    log_message "Setting up Moonraker component symlink..."
    COMPONENTS_DIR="${PLUGIN_DIR}/components"
    MOONRAKER_COMPONENTS_DIR="${MOONRAKER_DIR}/moonraker/components"

    if [ ! -d "$MOONRAKER_COMPONENTS_DIR" ]; then
        log_error "Error: Moonraker components directory does not exist"
        exit 1
    fi

    if [ -f "${COMPONENTS_DIR}/sound_system_service.py" ]; then
        # Remove existing symlink if it exists
        if [ -L "${MOONRAKER_COMPONENTS_DIR}/sound_system_service.py" ]; then
            rm "${MOONRAKER_COMPONENTS_DIR}/sound_system_service.py"
        fi

        # Create new symlink
        if ! ln -s "${COMPONENTS_DIR}/sound_system_service.py" "${MOONRAKER_COMPONENTS_DIR}/sound_system_service.py"; then
            log_error "Error: Failed to create Moonraker component symlink"
            exit 1
        fi
        log_message "Moonraker component symlink created successfully"
    else
        log_error "Error: sound_system_service.py not found in ${COMPONENTS_DIR}"
        exit 1
    fi
}

# Verify installation
verify_installation() {
    log_message "Verifying installation..."
    local has_errors=0

    # Check Klipper plugin
    if [ ! -L "${KLIPPER_DIR}/klippy/extras/sound_system.py" ]; then
        log_error "Klipper plugin symlink not found"
        has_errors=1
    fi

    # Check Moonraker component
    if [ ! -L "${MOONRAKER_DIR}/moonraker/components/sound_system_service.py" ]; then
        log_error "Moonraker component symlink not found"
        has_errors=1
    fi

    # Check sound directory
    if [ ! -d "${SOUND_DIR}" ]; then
        log_error "Sound directory not found"
        has_errors=1
    fi

    # Check aplay installation
    if ! command -v aplay >/dev/null; then
        log_error "aplay not found"
        has_errors=1
    fi

    if [ $has_errors -eq 0 ]; then
        log_message "Installation verification completed successfully"
    else
        log_error "Installation verification failed"
        return 1
    fi
}

# Restart services
restart_services() {
    log_message "Restarting Klipper and Moonraker services..."
    sudo systemctl restart klipper
    sudo systemctl restart moonraker
}

# Print help information
print_help() {
    echo -e "${GREEN}Lister Sound System Help${NC}"
    echo -e "\nAfter installation, you can use these commands:"
    echo -e "  ${YELLOW}SOUND_LIST${NC} - List all available sounds"
    echo -e "  ${YELLOW}PLAY_SOUND SOUND=print_complete${NC} - Play a predefined sound"
    echo -e "  ${YELLOW}PLAY_SOUND SOUND=custom.wav${NC} - Play a custom sound file"
    echo -e "\nSound files should be placed in: ${YELLOW}${SOUND_DIR}${NC}"
}

# Add this function after the log functions
fix_permissions() {
    log_message "Running final permission check for all components..."

    # Fix plugin directory permissions
    if [ -d "$PLUGIN_DIR" ]; then
        log_message "Setting permissions for $PLUGIN_DIR"
        
        # Make sure install.sh and refresh.sh stay executable before setting other permissions
        chmod +x "$PLUGIN_DIR/install.sh"
        chmod +x "$PLUGIN_DIR/refresh.sh"
        
        # Set all directories to 755 first
        sudo find "$PLUGIN_DIR" -type d -exec chmod 755 {} \;
        # Then set all files to non-executable
        sudo find "$PLUGIN_DIR" -type f -exec chmod 644 {} \;
        
        # Set ownership
        sudo chown -R pi:pi "$PLUGIN_DIR"
        
        # If it's a git repo, let git handle executable bits
        if [ -d "$PLUGIN_DIR/.git" ]; then
            cd "$PLUGIN_DIR" || exit 1
            git config core.fileMode true
            
            # Use git to set executable permissions based on .gitattributes
            git ls-files --stage | while read mode hash stage file; do
                if [ "$mode" = "100755" ]; then
                    chmod +x "$file"
                fi
            done
        fi
        
        # Make absolutely sure both scripts are executable after all operations
        chmod +x "$PLUGIN_DIR/install.sh"
        chmod +x "$PLUGIN_DIR/refresh.sh"
    fi

    # Fix symlink permissions
    if [ -L "${KLIPPER_DIR}/klippy/extras/sound_system.py" ]; then
        sudo chown -h pi:pi "${KLIPPER_DIR}/klippy/extras/sound_system.py"
    fi
    if [ -L "${MOONRAKER_DIR}/moonraker/components/sound_system_service.py" ]; then
        sudo chown -h pi:pi "${MOONRAKER_DIR}/moonraker/components/sound_system_service.py"
    fi

    # Fix config and log directories
    log_message "Fixing permissions for config and log directories"
    sudo chown -R pi:pi "$CONFIG_DIR" "$LOG_DIR"
    sudo chmod 755 "$CONFIG_DIR" "$LOG_DIR"
    sudo chmod 644 "$INSTALL_LOG"

    # Fix sound directory specifically
    if [ -d "$SOUND_DIR" ]; then
        log_message "Setting permissions for sound directory"
        sudo chown -R pi:pi "$SOUND_DIR"
        sudo find "$SOUND_DIR" -type d -exec chmod 755 {} \;
        sudo find "$SOUND_DIR" -type f -exec chmod 644 {} \;
    fi
}

# Main installation process
main() {
    log_message "Starting Lister Sound System installation..."

    check_directories
    install_system_deps
    install_python_deps
    setup_sound_directory
    test_audio_system
    setup_klipper_plugin
    setup_moonraker_component
    update_moonraker_conf
    fix_permissions
    verify_installation
    restart_services

    log_message "Installation completed successfully!"

    # Print verification steps and help
    print_help

    echo -e "\n${GREEN}Verify installation:${NC}"
    echo -e "  ${YELLOW}1. ls -l ${KLIPPER_DIR}/klippy/extras/sound_system.py${NC}"
    echo -e "  ${YELLOW}2. ls -l ${MOONRAKER_DIR}/moonraker/components/sound_system_service.py${NC}"
    echo -e "  ${YELLOW}3. ls -l ${SOUND_DIR}${NC}"
    echo -e "  ${YELLOW}4. aplay -l${NC}"
}

# Run the installation
main