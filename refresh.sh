#!/bin/bash

# Update script for lister_sound_system plugin.
# Define colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Define paths
REPO_DIR="/home/pi/lister_sound_system"
LOG_DIR="/home/pi/printer_data/logs"
UPDATE_LOG="$LOG_DIR/sound_system_update.log"

# Function to log messages
log_message() {
    echo -e "${GREEN}$(date): $1${NC}" | tee -a "$UPDATE_LOG"
}

log_error() {
    echo -e "${RED}$(date): $1${NC}" | tee -a "$UPDATE_LOG"
}

log_warning() {
    echo -e "${YELLOW}$(date): $1${NC}" | tee -a "$UPDATE_LOG"
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root (sudo)"
        exit 1
    fi
}

# Function to update repository
update_repo() {
    log_message "Updating sound system repository..."

    if [ ! -d "$REPO_DIR" ]; then
        log_message "Repository not found. Cloning..."
        git clone https://github.com/CWE3D/lister_sound_system.git "$REPO_DIR"
    else
        cd "$REPO_DIR" || exit 1
        log_message "Resetting local changes..."
        git reset --hard
        git clean -fd
        git fetch
        git reset --hard origin/main
        return 0
    fi
}

# Function to update Python dependencies
update_python_deps() {
    log_message "Updating Python dependencies..."
    
    # Update dependencies in Klippy virtual environment
    if ! /home/pi/klippy-env/bin/pip install -r "${REPO_DIR}/requirement.txt"; then
        log_error "Error: Failed to update Python dependencies in Klippy environment"
        return 1
    fi
    
    # Update dependencies in Moonraker virtual environment
    if ! /home/pi/moonraker-env/bin/pip install -r "${REPO_DIR}/requirement.txt"; then
        log_error "Error: Failed to update Python dependencies in Moonraker environment"
        return 1
    fi
    
    log_message "Python dependencies updated successfully"
    return 0
}

# Function to restart services
restart_services() {
    log_message "Restarting services..."
    
    # Stop services
    log_message "Stopping Klipper and Moonraker services..."
    sudo systemctl stop klipper
    sudo systemctl stop moonraker
    
    # Small delay to ensure clean shutdown
    sleep 2
    
    # Start services
    log_message "Starting Klipper and Moonraker services..."
    sudo systemctl start klipper
    sudo systemctl start moonraker
}

# Function to verify services
verify_services() {
    local all_good=true

    # Check Klipper service
    if ! systemctl is-active --quiet klipper; then
        log_error "Klipper service failed to start"
        all_good=false
    else
        log_message "Klipper service is running"
    fi

    # Check Moonraker service
    if ! systemctl is-active --quiet moonraker; then
        log_error "Moonraker service failed to start"
        all_good=false
    else
        log_message "Moonraker service is running"
    fi

    if [ "$all_good" = false ]; then
        log_error "Services failed to start. Check the logs for details:"
        log_error "- Klipper log: ${LOG_DIR}/klippy.log"
        log_error "- Moonraker log: ${LOG_DIR}/moonraker.log"
        return 1
    fi

    return 0
}

# Add this function after the log functions
fix_permissions() {
    log_message "Running final permission check for all components..."

    # Fix repository directory permissions
    if [ -d "$REPO_DIR" ]; then
        log_message "Setting permissions for $REPO_DIR"
        
        # Make sure refresh.sh stays executable before setting other permissions
        chmod +x "$REPO_DIR/refresh.sh"
        
        # Set all directories to 755 first
        sudo find "$REPO_DIR" -type d -exec chmod 755 {} \;
        # Then set all files to non-executable
        sudo find "$REPO_DIR" -type f -exec chmod 644 {} \;
        
        # Set ownership
        sudo chown -R pi:pi "$REPO_DIR"
        
        # If it's a git repo, let git handle executable bits
        if [ -d "$REPO_DIR/.git" ]; then
            cd "$REPO_DIR" || exit 1
            git config core.fileMode true
            
            # Use git to set executable permissions based on .gitattributes
            git ls-files --stage | while read mode hash stage file; do
                if [ "$mode" = "100755" ]; then
                    chmod +x "$file"
                fi
            done
        fi
        
        # Make absolutely sure refresh.sh is executable after all operations
        chmod +x "$REPO_DIR/refresh.sh"
    fi

    # Fix symlink permissions
    if [ -L "/home/pi/klipper/klippy/extras/sound_system.py" ]; then
        sudo chown -h pi:pi "/home/pi/klipper/klippy/extras/sound_system.py"
    fi
    if [ -L "/home/pi/moonraker/moonraker/components/sound_system_service.py" ]; then
        sudo chown -h pi:pi "/home/pi/moonraker/moonraker/components/sound_system_service.py"
    fi

    # Fix log directory
    log_message "Fixing permissions for log directory"
    sudo chown -R pi:pi "$LOG_DIR"
    sudo chmod 755 "$LOG_DIR"
    sudo chmod 644 "$UPDATE_LOG"

    # Fix sound directory
    if [ -d "$REPO_DIR/sounds" ]; then
        log_message "Setting permissions for sound directory"
        sudo chown -R pi:pi "$REPO_DIR/sounds"
        sudo find "$REPO_DIR/sounds" -type d -exec chmod 755 {} \;
        sudo find "$REPO_DIR/sounds" -type f -exec chmod 644 {} \;
    fi
}

# Main update process
main() {
    log_message "Starting sound system update process..."

    check_root

    if update_repo; then
        update_python_deps
        fix_permissions
        verify_services
    else
        log_message "No updates found. Skipping service restart."
    fi

    restart_services

    log_message "Update process completed!"

    # Print verification steps
    echo -e "\n${GREEN}Verify the services:${NC}"
    echo -e "1. Check Klipper status: ${YELLOW}systemctl status klipper${NC}"
    echo -e "2. Check Moonraker status: ${YELLOW}systemctl status moonraker${NC}"
    echo -e "3. View logs: ${YELLOW}tail -f ${LOG_DIR}/klippy.log ${LOG_DIR}/moonraker.log${NC}"
}

# Run the update
main 