# How to Update Your Proxmox Vault Password

To securely update the password for your specific Proxmox host (pve-test at 192.168.1.47), follow these steps:

## Step 1: Create or Edit the Vault File

```bash
# Edit the encrypted vault file
ansible-vault edit ~/.ansible/vars/proxmox_secrets.yml
```

## Step 2: Use the Following Structure in the File

Ensure your vault file has this structure (replace the placeholders with your actual passwords):

```yaml
# Proxmox API credentials
# These values should be encrypted with ansible-vault
vault_proxmox_api_password: "your_default_proxmox_password_here"

# Host-specific credentials
# For accessing individual hosts with different credentials
host_credentials:
  pve-test:
    ansible_user: root
    ansible_password: "your_ssh_password_for_pve_test"
    api_password: "your_proxmox_api_password_for_pve_test"

# Additional credentials as needed
```

## Step 3: Save and Close the File

In the editor (usually vi), press ESC, then type `:wq` and press Enter to save and exit.

## Step 4: Test the Connection

```bash
# Test SSH connection
ansible pve-test -i ~/.ansible/inventory/proxmox_hosts.yml -m ping

# Test API connection (optional)
ansible-playbook ~/.ansible/playbooks/proxmox/check_connection.yml -i ~/.ansible/inventory/proxmox_hosts.yml --limit pve-test
```

## Notes:
- The `host_credentials` section allows you to define different credentials for each host
- The inventory file is already set up to use these credentials
- All passwords are securely encrypted in the vault file
