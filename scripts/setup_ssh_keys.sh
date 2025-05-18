#!/bin/bash
# SSH Key Management for Proxmox VMs and Containers
# This script generates SSH keys and distributes them to Proxmox hosts and VMs

set -e

# Configuration
ANSIBLE_DIR="${HOME}/.ansible"
SSH_DIR="${HOME}/.ssh"
KEY_NAME="proxmox_ansible"
KEY_TYPE="ed25519"
KEY_FILE="${SSH_DIR}/${KEY_NAME}"
LOG_DIR="${ANSIBLE_DIR}/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="${LOG_DIR}/ssh_key_setup_${TIMESTAMP}.log"
INVENTORY="${ANSIBLE_DIR}/inventory/proxmox_hosts.yml"
SSH_CONFIG="${SSH_DIR}/config"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Check if inventory exists
if [ ! -f "${INVENTORY}" ]; then
    log "ERROR: Inventory file ${INVENTORY} not found!"
    exit 1
fi

# 1. Generate SSH key if it doesn't exist
if [ ! -f "${KEY_FILE}" ]; then
    log "Generating new SSH key: ${KEY_FILE}"
    mkdir -p "${SSH_DIR}"
    ssh-keygen -t ${KEY_TYPE} -f "${KEY_FILE}" -N "" -C "ansible-automation@$(hostname)"
else
    log "SSH key already exists at ${KEY_FILE}"
fi

# 2. Update SSH config if needed
if ! grep -q "${KEY_NAME}" "${SSH_CONFIG}" 2>/dev/null; then
    log "Updating SSH config file"
    cat >> "${SSH_CONFIG}" <<EOF

# Ansible Proxmox automation settings
Host proxmox-* pve-* *.proxmox
    IdentityFile ${KEY_FILE}
    User root
    StrictHostKeyChecking accept-new

Host vm-* ct-*
    IdentityFile ${KEY_FILE}
    User admin
    StrictHostKeyChecking accept-new
EOF
fi

# 3. Copy key to Proxmox hosts first (these should have SSH password access)
log "Copying SSH key to Proxmox nodes..."
NODES=$(ansible-inventory -i "${INVENTORY}" --list | jq -r '.all_nodes.hosts[]' 2>/dev/null)

# Get vault password if needed
VAULT_PASSWORD=""
if [ -f "${ANSIBLE_DIR}/vars/proxmox_secrets.yml" ]; then
    log "Vault file found, will use host-specific passwords if available"
    read -s -p "Enter your Ansible Vault password: " VAULT_PASSWORD
    echo ""
fi

for NODE in $NODES; do
    log "Copying SSH key to ${NODE}..."
    
    # Get host-specific credentials if available
    NODE_USER="root"
    NODE_PASSWORD=""
    
    if [ -n "$VAULT_PASSWORD" ]; then
        # Extract credentials from vault - this requires Python
        CREDS=$(python3 -c "
import yaml, os, subprocess
from ansible.constants import DEFAULT_VAULT_ID_MATCH
from ansible.parsing.vault import VaultLib, VaultSecret
vault_password = b'$VAULT_PASSWORD'
secret = [(DEFAULT_VAULT_ID_MATCH, VaultSecret(vault_password))]
vault = VaultLib(secret)
with open('${ANSIBLE_DIR}/vars/proxmox_secrets.yml', 'r') as f:
    content = f.read()
if content.startswith('\$ANSIBLE_VAULT;'):
    decrypted = vault.decrypt(content)
    data = yaml.safe_load(decrypted)
    if 'host_credentials' in data and '${NODE}' in data['host_credentials']:
        creds = data['host_credentials']['${NODE}']
        user = creds.get('ansible_user', 'root')
        password = creds.get('ansible_password', '')
        print(f'{user}:{password}')
" 2>/dev/null)

        if [ -n "$CREDS" ]; then
            NODE_USER=$(echo "$CREDS" | cut -d':' -f1)
            NODE_PASSWORD=$(echo "$CREDS" | cut -d':' -f2-)
            log "Using custom credentials for ${NODE}"
        fi
    fi
    
    # Try with password authentication if available
    if [ -n "$NODE_PASSWORD" ]; then
        log "Using password authentication for ${NODE}"
        sshpass -p "$NODE_PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no -i "${KEY_FILE}.pub" "${NODE_USER}@${NODE}" >> "${LOG_FILE}" 2>&1
        if [ $? -eq 0 ]; then
            log "Successfully copied key to ${NODE}"
        else
            log "WARNING: Failed to copy key to ${NODE} using password authentication."
        fi
    else
        # Try with simple authentication as before
        if ssh-copy-id -i "${KEY_FILE}.pub" "${NODE_USER}@${NODE}" >> "${LOG_FILE}" 2>&1; then
            log "Successfully copied key to ${NODE}"
        else
            log "WARNING: Failed to copy key to ${NODE}. May need manual intervention."
        fi
    fi
done

# 4. Set up SSH keys for VMs and containers using the Proxmox nodes
log "Setting up SSH access to VMs and containers..."
ansible-playbook "${ANSIBLE_DIR}/playbooks/setup_ssh_access.yml" -i "${INVENTORY}" || {
    log "ERROR: Failed to set up SSH access to VMs and containers"
    exit 1
}

log "SSH key setup completed successfully!"
log "You can now use automatic SSH authentication for Proxmox automation."
