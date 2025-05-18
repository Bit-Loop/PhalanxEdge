import sys
import xml.etree.ElementTree as ET
import yaml
import time


def xml_to_yaml(xml_string):
    root = ET.fromstring(xml_string)
    hostname = root.find(".//hostname").text.strip()
    domain = root.find(".//domain").text.strip()

    # Parse interfaces to get descriptions for names
    interfaces_dict = {}
    for intf in root.findall(".//interfaces/*"):
        descr = intf.find("descr")
        if descr is not None:
            interfaces_dict[intf.tag] = descr.text.strip()

    # Initialize a dictionary to hold the rules structured for YAML
    rules_dict = {}

    # Function to get source or destination string
    def get_source_or_destination_text(
        element: ET.Element, current_interface: str, interfaces_dict: dict
    ):
        # Try to find an address element first
        address = element.find("address")
        if address is not None:
            return address.text.strip()

        # If no address, check for a network element
        network = element.find("network")
        if network is not None:
            # Get the descriptive name of the network/interface
            network_name = interfaces_dict.get(
                network.text.strip().upper(), network.text.strip()
            )

            # If the network name matches the current interface name, return "NET"
            if network_name == current_interface:
                return "NET"
            elif network_name == "(self)":
                return "(self)"
            else:
                return f"NET: {interfaces_dict.get(network_name, network_name)}"

        return "Any"

    # Function to get rule description
    def get_rule_description(rule_element):
        descr_elem = rule_element.find("descr")
        if descr_elem is not None and descr_elem.text:
            # Strip CDATA and leading/trailing whitespace, if necessary
            return descr_elem.text.strip()
        return "UnnamedRule"

    def get_destination_port(rule_element):
        port_elem = rule_element.find(".//destination/port")
        if port_elem is not None and port_elem.text:
            return port_elem.text.strip()
        return ""

    # Parse rules
    for rule in root.findall(".//filter/rule"):
        # skip automated rules, starts with "(m)"
        if (
            include_automated_rules != "y"
            and get_rule_description(rule).startswith("(M)")
            or get_rule_description(rule).startswith("pfB")
        ):
            continue

        # Extracting necessary information from each rule
        interface_tag = rule.find("interface").text
        interface_name = interfaces_dict.get(interface_tag, interface_tag)

        # Get Protocol
        if rule.find("protocol") is None:
            rule_protocol = ""
        else:
            rule_protocol = rule.find("protocol").text.strip()

        # Get Action
        if rule.find("type") is None:
            rule_type = ""
        else:
            rule_type = rule.find("type").text.strip()

        # Get Destination Port
        if rule.find(".//destination/port") is None:
            rule_destination_port = ""
        else:
            # if port is number, convert to int
            rule_destination_port = get_destination_port(rule)
            if rule_destination_port.isdigit():
                rule_destination_port = int(rule_destination_port)

        rule_info = {
            "name": get_rule_description(rule),
            "source": get_source_or_destination_text(
                rule.find("source"), interface_tag, interfaces_dict
            ),
            "destination": get_source_or_destination_text(
                rule.find("destination"), interface_tag, interfaces_dict
            ),
            "destination_port": rule_destination_port,
            "protocol": rule_protocol,
            "action": rule_type,
        }
        # remove empty values
        rule_info = {k: v for k, v in rule_info.items() if v}

        # Appending the rule to the appropriate interface section
        if interface_name not in rules_dict:
            rules_dict[interface_name] = [rule_info]
        else:
            # add rule and space
            rules_dict[interface_name].append(rule_info)
    # Generating YAML from the structured dictionary
    yaml_str = yaml.dump(
        rules_dict,
        indent=2,
        sort_keys=False,
        allow_unicode=True,
    )
    return yaml_str, hostname, domain


if __name__ == "__main__":
    # check if no arguments are provided
    if len(sys.argv) < 2:
        filename = input("Enter filename: ")
    else:
        filename = sys.argv[1]

    # Read the XML file
    with open(filename, "r") as f:
        xml_string = f.read()

    if len(sys.argv) < 3:
        # prompt user if automated rules should be included
        include_automated_rules = input("Include automated rules? (y/n): ").lower()
    else:
        include_automated_rules = sys.argv[2].lower()

    # Convert XML to YAML
    yaml_str, hostname, domain = xml_to_yaml(xml_string)

    # Write the YAML to a file
    with open(f"/tmp/rules_{hostname}.{domain}_{int(time.time())}.yml", "w") as f:
        f.write(yaml_str)
