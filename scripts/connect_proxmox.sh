#!/bin/zsh
# Script to connect to Proxmox host with SSH host key checking disabled

# Define credentials
PROXMOX_HOST=192.168.1.47
SSH_USER=root
SSH_PASSWORD=""  # Testing/WIP Your actual password

# First, manually accept host key
echo "Accepting SSH host key (you'll be prompted for the password)..."
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=accept-new $SSH_USER@$PROXMOX_HOST "echo 'SSH connection successful!'" || {
  echo "Failed to connect with sshpass. Trying alternative method..."
  
  # Alternative: Direct SSH with manual "yes" response
  echo "Connecting to host. When prompted with 'Are you sure you want to continue connecting', type 'yes'"
  ssh -o StrictHostKeyChecking=ask $SSH_USER@$PROXMOX_HOST
}

# After this is done, test Ansible connection
echo -e "\nTesting Ansible connection..."
cd ~/.ansible
ansible pve-test -i inventory/proxmox_hosts.yml -m ping -e "ansible_password=$SSH_PASSWORD"

echo -e "\nIf the ping was successful, you can now run:"
echo "cd ~/.ansible && ansible-playbook playbooks/quick_check.yml -i inventory/proxmox_hosts.yml"
