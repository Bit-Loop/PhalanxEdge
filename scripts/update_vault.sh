#!/bin/zsh
# Script to update Proxmox vault file with correct structure

set -e

# Check if vault exists
VAULT_FILE="$HOME/.ansible/vars/proxmox_secrets.yml"
if [ ! -f "$VAULT_FILE" ]; then
  echo "Error: Vault file not found at $VAULT_FILE"
  exit 1
fi

# Create temporary directory
TEMP_DIR=$(mktemp -d)
TEMP_FILE="$TEMP_DIR/vault_content.yml"
DECRYPT_FILE="$TEMP_DIR/decrypted.yml"
NEW_FILE="$TEMP_DIR/new_vault.yml"

# Decrypt the vault file to a temporary location
ansible-vault decrypt --output="$DECRYPT_FILE" "$VAULT_FILE" || {
  echo "Failed to decrypt vault file. Make sure to enter the correct password."
  rm -rf "$TEMP_DIR"
  exit 1
}

# Display current structure
echo "=== CURRENT VAULT STRUCTURE ==="
cat "$DECRYPT_FILE" | grep -v "password\|secret"
echo "==============================="

# Create new structure template
cat > "$TEMP_FILE" << 'EOF'
# Proxmox API credentials
# These values should be encrypted with ansible-vault

# Default Proxmox API password
vault_proxmox_api_password: "your_default_proxmox_api_password"

# Host-specific passwords (for pve-test)
vault_pve_test_password: "your_ssh_password_for_pve_test" 
vault_pve_test_api_password: "your_proxmox_api_password_for_pve_test"

# Additional credentials as needed
EOF

# Ask user if they want to update
echo "Do you want to update your vault file with the correct structure? (y/n)"
read answer
if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
  echo "Operation cancelled."
  rm -rf "$TEMP_DIR"
  exit 0
fi

# Open the template in an editor for user to update
echo "Opening template file for editing. Replace the placeholder values with your actual passwords."
echo "Press Enter to continue..."
read
$EDITOR "$TEMP_FILE"

# Encrypt the new file
ansible-vault encrypt --output="$NEW_FILE" "$TEMP_FILE" || {
  echo "Failed to encrypt the new vault file."
  rm -rf "$TEMP_DIR"
  exit 1
}

# Backup old vault
BACKUP_FILE="$VAULT_FILE.$(date +%Y%m%d%H%M%S).bak"
cp "$VAULT_FILE" "$BACKUP_FILE"
echo "Created backup at $BACKUP_FILE"

# Replace the vault file
cp "$NEW_FILE" "$VAULT_FILE"
echo "Vault file updated successfully!"

# Cleanup
rm -rf "$TEMP_DIR"

echo "Now you can run: ansible pve-test -i $HOME/.ansible/inventory/proxmox_hosts.yml -m ping"
