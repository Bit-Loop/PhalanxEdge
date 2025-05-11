#!/usr/bin/python
# filepath: /home/ubuntu/.ansible/plugins/filter/tailscale_filters.py

def modify_tailscale_hosts(inventory_dict):
    """
    Add ansible_host and other variables to Tailscale hosts.
    """
    if 'all' in inventory_dict and 'children' in inventory_dict['all'] and 'tailscale' in inventory_dict['all']['children']:
        tailscale = inventory_dict['all']['children']['tailscale']
        if 'children' in tailscale:
            for group_name, group_data in tailscale['children'].items():
                if 'hosts' in group_data:
                    for hostname, host_data in group_data['hosts'].items():
                        # Ensure ansible_host is set from ip if not already present
                        if 'ip' in host_data and 'ansible_host' not in host_data:
                            host_data['ansible_host'] = host_data['ip']
    return inventory_dict

class FilterModule(object):
    def filters(self):
        return { 
            'modify_tailscale_hosts': modify_tailscale_hosts
        }