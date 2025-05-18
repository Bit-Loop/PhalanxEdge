#!/bin/zsh
# This script creates a direct SSH connection to your Proxmox host
# It bypasses the inventory system to test connectivity

HOST=192.168.1.47
USER=root
PASSWORD="" #changing in the future. Testing/wip

# Test SSH connection with sshpass
echo "Testing direct SSH connection to $HOST..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no $USER@$HOST "hostname && uptime"

echo ""
echo "If you see the hostname and uptime above, your SSH connection is working!"
echo "Now let's set up SSH keys for passwordless access..."

# Create SSH key if it doesn't exist
SSH_KEY=~/.ssh/proxmox_ansible
if [ ! -f "$SSH_KEY" ]; then
  echo "Generating new SSH key: $SSH_KEY"
  ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "ansible-automation@$(hostname)"
else
  echo "Using existing SSH key: $SSH_KEY"
fi

# Copy the key to the Proxmox host
echo "Copying SSH key to $HOST..."
sshpass -p "$PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no -i "$SSH_KEY.pub" "$USER@$HOST"

echo ""
echo "Testing passwordless connection..."
ssh -i "$SSH_KEY" "$USER@$HOST" "echo 'SSH key authentication working!'"

echo ""
echo "If no password was requested, your SSH key is successfully installed."
