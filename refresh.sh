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
        git fetch

        LOCAL=$(git rev-parse @)
        REMOTE=$(git rev-parse @{u})

        if [ "$LOCAL" != "$REMOTE" ]; then
            log_message "Updates found. Pulling changes..."
            git pull
            return 0
        else
            log_message "Already up to date"
            return 1
        fi
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
    if ! /home/pi/moonraker/.venv/bin/pip install -r "${REPO_DIR}/requirement.txt"; then
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
    log_message "Stopping sound system service..."
    systemctl stop lister_sound_service
    
    # Small delay to ensure clean shutdown
    sleep 2
    
    # Start services
    log_message "Starting sound system service..."
    systemctl start lister_sound_service
}

# Function to verify services
verify_services() {
    local all_good=true

    # Check sound system service
    if ! systemctl is-active --quiet lister_sound_service; then
        log_error "Sound system service failed to start"
        all_good=false
    else
        log_message "Sound system service is running"
    fi

    if [ "$all_good" = false ]; then
        log_error "Service failed to start. Check the logs for details:"
        log_error "- Sound system log: ${LOG_DIR}/sound_system.log"
        return 1
    fi

    return 0
}

# Main update process
main() {
    log_message "Starting sound system update process..."

    check_root

    # Update repository
    if update_repo; then
        # Update Python dependencies
        update_python_deps
        verify_services
    else
        log_message "No updates found. Skipping service restart."
    fi

    restart_services

    log_message "Update process completed!"

    # Print verification steps
    echo -e "\n${GREEN}Verify the services:${NC}"
    echo -e "1. Check sound system status: ${YELLOW}systemctl status lister_sound_service${NC}"
    echo -e "2. View sound system logs: ${YELLOW}tail -f ${LOG_DIR}/sound_system.log${NC}"
}

# Run the update
main 