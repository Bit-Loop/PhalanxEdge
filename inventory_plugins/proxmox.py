#!/usr/bin/env python
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
    name: proxmox
    plugin_type: inventory
    short_description: Proxmox dynamic inventory
    description:
        - Get inventory hosts from Proxmox virtualization platform.
        - Uses a YAML configuration file with the name 'proxmox.(yml|yaml)'.
    extends_documentation_fragment:
        - constructed
        - inventory_cache
    options:
        plugin:
            description: Token that ensures this is a source file for the 'proxmox' plugin.
            required: true
            choices: ['proxmox']
        url:
            description: URL of the Proxmox Web API.
            required: true
        user:
            description: Proxmox authentication user.
            required: true
        password:
            description: Proxmox authentication password.
            required: false
        token_id:
            description: Proxmox authentication token ID.
            required: false
        token_secret:
            description: Proxmox authentication token secret.
            required: false
        validate_certs:
            description: Verify SSL certificate validity.
            type: boolean
            default: true
        group_prefix:
            description: Prefix to apply to host groups.
            default: proxmox_
        want_facts:
            description: Generate and gather Proxmox facts.
            default: true
        want_proxmox_nodes_ansible_host:
            description: Add the Proxmox nodes' IP to ansible_host.
            default: true
        facts_prefix:
            description: Prefix to apply to facts gathered from Proxmox.
            default: proxmox_
        vm_status_filter:
            description: Filter VMs/containers by status
            default: ['running']
        strict_hostname_checking:
            description: Ensure hostnames conform to DNS standards
            default: false
'''

EXAMPLES = '''
# proxmox.yml
plugin: proxmox
url: https://proxmox.example.com:8006
user: ansible@pve
password: secure123
validate_certs: false
group_prefix: pve_
want_facts: true
facts_prefix: proxmox_

# With token authentication
plugin: proxmox
url: https://proxmox.example.com:8006
user: ansible@pve
token_id: ansible
token_secret: afcc8309-a64a-45d2-893f-8d42853a692a
validate_certs: false
'''

import re
import json
from distutils.version import LooseVersion
from ansible.errors import AnsibleError
from ansible.module_utils._text import to_native
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from proxmoxer import ProxmoxAPI
    HAS_PROXMOXER = True
except ImportError:
    HAS_PROXMOXER = False


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = 'proxmox'

    def verify_file(self, path):
        valid = False
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(('proxmox.yaml', 'proxmox.yml')):
                valid = True
        return valid

    def _get_proxmox_version(self, proxmox_api):
        try:
            api_result = proxmox_api.version.get()
            return api_result['version']
        except Exception as e:
            self.display.error("Error getting Proxmox version: %s" % to_native(e))
            return None

    def _get_node_ip(self, proxmox_api, node):
        try:
            node_ip = None
            network_interfaces = proxmox_api.nodes(node).network.get()
            for interface in network_interfaces:
                if interface.get('type') == 'bridge' and interface.get('active') == 1:
                    if 'address' in interface:
                        node_ip = interface['address']
                        break
            return node_ip
        except Exception as e:
            self.display.warning("Error getting IP for node %s: %s" % (node, to_native(e)))
            return None

    def _to_safe_hostname(self, hostname):
        if self.get_option('strict_hostname_checking'):
            return hostname
        return re.sub(r'[^a-zA-Z0-9_-]', '_', hostname)

    def _process_qemu(self, proxmox_api, node, vm_list, node_ip):
        for vm in vm_list:
            if vm['status'] not in self.vm_status_filter:
                continue

            vm_id = vm['vmid']
            vm_name = vm.get('name', '')
            if not vm_name:
                vm_name = f"vm-{vm_id}"
                
            safe_vm_name = self._to_safe_hostname(vm_name)
            
            # Extract network info
            try:
                vm_config = proxmox_api.nodes(node).qemu(vm_id).config.get()
                
                vm_ip = None
                for k, v in vm_config.items():
                    if k.startswith('net') and isinstance(v, str) and 'ip=' in v:
                        match = re.search(r'ip=(\d+\.\d+\.\d+\.\d+)', v)
                        if match:
                            vm_ip = match.group(1)
                            break
            except Exception as e:
                self.display.warning(f"Error retrieving VM {vm_id} config: {to_native(e)}")
                vm_ip = None
                vm_config = {}

            # Add to inventory
            self.inventory.add_host(safe_vm_name)
            self.inventory.add_child('all_vms', safe_vm_name)
            self.inventory.add_child(f"{self.group_prefix}qemu", safe_vm_name)
            self.inventory.add_child(f"{self.group_prefix}node_{node}", safe_vm_name)

            # Set VM-specific variables
            self.inventory.set_variable(safe_vm_name, 'proxmox_type', 'qemu')
            self.inventory.set_variable(safe_vm_name, 'proxmox_vmid', vm_id)
            self.inventory.set_variable(safe_vm_name, 'proxmox_node', node)
            self.inventory.set_variable(safe_vm_name, 'proxmox_name', vm_name)
            self.inventory.set_variable(safe_vm_name, 'proxmox_status', vm['status'])
            
            if vm_ip:
                self.inventory.set_variable(safe_vm_name, 'ansible_host', vm_ip)

            # Add facts if requested
            if self.want_facts:
                facts_dict = {f"{self.facts_prefix}{k}": v for k, v in vm.items()}
                
                # Add config options as facts
                for k, v in vm_config.items():
                    facts_dict[f"{self.facts_prefix}config_{k}"] = v
                
                for k, v in facts_dict.items():
                    self.inventory.set_variable(safe_vm_name, k, v)

    def _process_lxc(self, proxmox_api, node, lxc_list, node_ip):
        for lxc in lxc_list:
            if lxc['status'] not in self.vm_status_filter:
                continue

            lxc_id = lxc['vmid']
            lxc_name = lxc.get('name', '')
            if not lxc_name:
                lxc_name = f"lxc-{lxc_id}"
                
            safe_lxc_name = self._to_safe_hostname(lxc_name)
            
            # Get container config and network info
            try:
                lxc_config = proxmox_api.nodes(node).lxc(lxc_id).config.get()
                
                lxc_ip = None
                for k, v in lxc_config.items():
                    if k.startswith('net') and isinstance(v, str) and 'ip=' in v:
                        match = re.search(r'ip=([^/]+)', v)
                        if match:
                            lxc_ip = match.group(1)
                            break
            except Exception as e:
                self.display.warning(f"Error retrieving LXC {lxc_id} config: {to_native(e)}")
                lxc_ip = None
                lxc_config = {}

            # Add to inventory
            self.inventory.add_host(safe_lxc_name)
            self.inventory.add_child('all_containers', safe_lxc_name)
            self.inventory.add_child(f"{self.group_prefix}lxc", safe_lxc_name)
            self.inventory.add_child(f"{self.group_prefix}node_{node}", safe_lxc_name)

            # Set container-specific variables
            self.inventory.set_variable(safe_lxc_name, 'proxmox_type', 'lxc')
            self.inventory.set_variable(safe_lxc_name, 'proxmox_vmid', lxc_id)
            self.inventory.set_variable(safe_lxc_name, 'proxmox_node', node)
            self.inventory.set_variable(safe_lxc_name, 'proxmox_name', lxc_name)
            self.inventory.set_variable(safe_lxc_name, 'proxmox_status', lxc['status'])
            
            if lxc_ip:
                self.inventory.set_variable(safe_lxc_name, 'ansible_host', lxc_ip)

            # Add facts if requested
            if self.want_facts:
                facts_dict = {f"{self.facts_prefix}{k}": v for k, v in lxc.items()}
                
                # Add config options as facts
                for k, v in lxc_config.items():
                    facts_dict[f"{self.facts_prefix}config_{k}"] = v
                
                for k, v in facts_dict.items():
                    self.inventory.set_variable(safe_lxc_name, k, v)

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        
        self._read_config_data(path)
        
        # Check for required dependencies
        if not HAS_REQUESTS:
            raise AnsibleError('This inventory plugin requires the requests Python library')
        if not HAS_PROXMOXER:
            raise AnsibleError('This inventory plugin requires the proxmoxer Python library')

        # Set options
        self.proxmox_url = self.get_option('url')
        self.proxmox_user = self.get_option('user')
        self.proxmox_password = self.get_option('password', None)
        self.token_id = self.get_option('token_id', None)
        self.token_secret = self.get_option('token_secret', None)
        self.validate_certs = self.get_option('validate_certs')
        self.group_prefix = self.get_option('group_prefix')
        self.want_facts = self.get_option('want_facts')
        self.facts_prefix = self.get_option('facts_prefix')
        self.want_node_ip = self.get_option('want_proxmox_nodes_ansible_host')
        self.vm_status_filter = self.get_option('vm_status_filter')
        
        # Set up connection to Proxmox API
        auth_args = {}
        if self.proxmox_password:
            auth_args['password'] = self.proxmox_password
        elif self.token_id and self.token_secret:
            auth_args['token_name'] = self.token_id
            auth_args['token_value'] = self.token_secret
        else:
            raise AnsibleError('Either password or token_id/token_secret is required for authentication')

        try:
            self.proxmox_api = ProxmoxAPI(
                self.proxmox_url, 
                user=self.proxmox_user,
                verify_ssl=self.validate_certs,
                **auth_args
            )
        except Exception as e:
            raise AnsibleError(f"Could not connect to Proxmox API: {to_native(e)}")
            
        # Create base groups
        self.inventory.add_group('all_nodes')
        self.inventory.add_group('all_vms')
        self.inventory.add_group('all_containers')
        self.inventory.add_group(f"{self.group_prefix}qemu")
        self.inventory.add_group(f"{self.group_prefix}lxc")

        # Process Proxmox nodes and VMs
        try:
            proxmox_version = self._get_proxmox_version(self.proxmox_api)
            self.display.debug(f"Connected to Proxmox version: {proxmox_version}")

            # Get and process nodes
            nodes = self.proxmox_api.nodes.get()
            for node in nodes:
                node_name = node['node']
                
                # Add node to inventory
                self.inventory.add_host(node_name)
                self.inventory.add_child('all_nodes', node_name)
                self.inventory.add_group(f"{self.group_prefix}node_{node_name}")
                
                # Add node status to inventory
                self.inventory.set_variable(node_name, 'proxmox_status', node['status'])
                self.inventory.set_variable(node_name, 'proxmox_type', 'node')
                
                # Get node IP if configured
                node_ip = None
                if self.want_node_ip:
                    node_ip = self._get_node_ip(self.proxmox_api, node_name)
                    if node_ip:
                        self.inventory.set_variable(node_name, 'ansible_host', node_ip)
                
                # Add node facts
                if self.want_facts:
                    for k, v in node.items():
                        self.inventory.set_variable(node_name, f"{self.facts_prefix}{k}", v)

                # Get and process VMs for this node
                try:
                    vm_list = self.proxmox_api.nodes(node_name).qemu.get()
                    self._process_qemu(self.proxmox_api, node_name, vm_list, node_ip)
                except Exception as e:
                    self.display.warning(f"Error getting QEMU VMs for node {node_name}: {to_native(e)}")

                # Get and process containers for this node
                try:
                    lxc_list = self.proxmox_api.nodes(node_name).lxc.get()
                    self._process_lxc(self.proxmox_api, node_name, lxc_list, node_ip)
                except Exception as e:
                    self.display.warning(f"Error getting LXC containers for node {node_name}: {to_native(e)}")
                    
        except Exception as e:
            raise AnsibleError(f"Error populating inventory: {to_native(e)}")
            
        # Add additional groups based on hostvars
        self._set_composite_vars(
            self.get_option('compose'),
            self.inventory.get_hosts(),
            self.get_option('strict'),
        )
        self._add_host_to_keyed_groups(
            self.get_option('keyed_groups'), 
            self.inventory.get_hosts(), 
            self.get_option('strict'),
        )
