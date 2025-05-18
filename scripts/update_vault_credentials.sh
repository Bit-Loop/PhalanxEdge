#!/bin/bash
# filepath: /home/ubuntu/.ansible/scripts/update_vault_credentials.sh
# Script to update vault credentials for Proxmox

# Set variables
VAULT_FILE=~/.ansible/vars/proxmox_secrets.yml
VAULT_PASS_FILE=~/.ansible/.vault_pass
API_PASS_FILE=~/.ansible/.api_pass
TEMP_FILE=/tmp/proxmox_vault_temp.yml
INVENTORY_HOST=pve-test

# Check if files exist
if [ ! -f $VAULT_PASS_FILE ]; then
  echo "Error: Vault password file not found at $VAULT_PASS_FILE"
  exit 1
fi

if [ ! -f $API_PASS_FILE ]; then
  echo "Error: API password file not found at $API_PASS_FILE"
  exit 1
fi

# Get the API password (trim whitespace)
API_PASSWORD=$(cat $API_PASS_FILE | tr -d '\n\r')

# Create temporary template with current credentials
cat > $TEMP_FILE << EOF
# Proxmox API credentials
# These values should be encrypted with ansible-vault
vault_proxmox_api_password: "$API_PASSWORD"

# Host-specific credentials
# For accessing individual hosts with different credentials
host_credentials:
  $INVENTORY_HOST:
    ansible_user: root
    ansible_password: "$API_PASSWORD"
    api_password: "$API_PASSWORD"
EOF

# Encrypt the file with ansible-vault
echo "Encrypting vault file..."
ansible-vault encrypt $TEMP_FILE --vault-password-file=$VAULT_PASS_FILE

# Replace the vault file with our updated one
cp $TEMP_FILE $VAULT_FILE

# Clean up
rm $TEMP_FILE

echo "Vault credentials updated successfully at $VAULT_FILE"
