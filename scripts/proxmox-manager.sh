#!/bin/zsh
# Proxmox Management Controller
# This script orchestrates Proxmox infrastructure deployment, updates, and monitoring

set -e

SCRIPT_DIR="${HOME}/.ansible/scripts"
ANSIBLE_DIR="${HOME}/.ansible"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_DIR="${ANSIBLE_DIR}/logs"
LOG_FILE="${LOG_DIR}/proxmox_manager_${TIMESTAMP}.log"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Function to display usage information
usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  setup       Set up SSH keys and initial inventory"
    echo "  update      Update inventory and SSH keys"
    echo "  monitor     Run monitoring and generate reports"
    echo "  deploy      Deploy infrastructure changes"
    echo "  backup      Create backups of VMs and containers"
    echo "  scale       Scale infrastructure up or down"
    echo "  all         Run all routine maintenance tasks"
    echo ""
    echo "Options:"
    echo "  --force     Force operations even if checks fail"
    echo "  --quiet     Reduce output verbosity"
    echo "  --help      Display this help message"
}

# Check for command
if [ $# -eq 0 ] || [ "$1" = "--help" ]; then
    usage
    exit 0
fi

COMMAND=$1
shift

# Parse options
FORCE=false
QUIET=false
while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        --quiet)
            QUIET=true
            shift
            ;;
        *)
            log "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Check if required scripts exist
if [ ! -x "${SCRIPT_DIR}/update_proxmox_inventory.sh" ]; then
    log "ERROR: Required script not found or not executable: ${SCRIPT_DIR}/update_proxmox_inventory.sh"
    exit 1
fi

# Command implementations
run_setup() {
    log "Setting up SSH keys and initial Proxmox inventory..."
    
    # Run SSH key setup first
    if [ -x "${SCRIPT_DIR}/setup_ssh_keys.sh" ]; then
        log "Setting up SSH keys..."
        "${SCRIPT_DIR}/setup_ssh_keys.sh"
    else
        log "SSH key script not found or not executable. Creating it..."
        chmod +x "${SCRIPT_DIR}/setup_ssh_keys.sh"
        "${SCRIPT_DIR}/setup_ssh_keys.sh"
    fi
    
    log "Setup complete!"
}

run_update() {
    log "Updating Proxmox inventory..."
    "${SCRIPT_DIR}/update_proxmox_inventory.sh"
}

run_monitor() {
    log "Running Proxmox monitoring and generating reports..."
    cd "${ANSIBLE_DIR}/playbooks" || { log "Failed to change directory to ${ANSIBLE_DIR}/playbooks"; exit 1; }
    ansible-playbook proxmox/monitoring.yml
    
    # Open the report
    if [ -f "${ANSIBLE_DIR}/inventory/generated/resource_report_$(date +"%Y-%m-%d").html" ]; then
        log "Report generated successfully!"
        echo "Report is available at: ${ANSIBLE_DIR}/inventory/generated/resource_report_$(date +"%Y-%m-%d").html"
    else
        log "Warning: Report generation may have failed!"
    fi
}

run_deploy() {
    log "Deploying Proxmox infrastructure changes..."
    cd "${ANSIBLE_DIR}/playbooks" || { log "Failed to change directory to ${ANSIBLE_DIR}/playbooks"; exit 1; }
    ansible-playbook proxmox.yml
}

run_backup() {
    log "Creating backups of VMs and containers..."
    cd "${ANSIBLE_DIR}/playbooks" || { log "Failed to change directory to ${ANSIBLE_DIR}/playbooks"; exit 1; }
    ansible-playbook proxmox/backup.yml
}

run_scale() {
    log "Scaling infrastructure..."
    cd "${ANSIBLE_DIR}/playbooks" || { log "Failed to change directory to ${ANSIBLE_DIR}/playbooks"; exit 1; }
    ansible-playbook proxmox/scale.yml
}

# Main command handler
case "${COMMAND}" in
    setup)
        run_setup
        ;;
    update)
        run_update
        ;;
    monitor)
        run_monitor
        ;;
    deploy)
        run_deploy
        ;;
    backup)
        run_backup
        ;;
    scale)
        run_scale
        ;;
    all)
        log "Running all routine maintenance tasks..."
        run_update
        run_monitor
        ;;
    *)
        log "Unknown command: ${COMMAND}"
        usage
        exit 1
        ;;
esac

log "Proxmox management tasks completed successfully!"
exit 0
