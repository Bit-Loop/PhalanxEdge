#!/bin/bash
# filepath: /home/ubuntu/.ansible/scripts/test_proxmox_api.sh
# Script to test direct Proxmox API access

# Load password from file and trim whitespace
API_PASSWORD=$(cat ~/.ansible/.api_pass | tr -d '\n\r')
API_HOST="192.168.1.47"
API_USER="root@pam"
API_URL="https://${API_HOST}:8006/api2/json/version"

echo "Testing Proxmox API connection..."
echo "URL: ${API_URL}"
echo "User: ${API_USER}"
echo "Password length: ${#API_PASSWORD} characters"

# Print first and last character of password (safely)
echo "Password first char: ${API_PASSWORD:0:1}"
echo "Password last char: ${API_PASSWORD:$((${#API_PASSWORD}-1)):1}"

# Make the API call with curl
echo -e "\nAPI response:"
curl -s -k -u "${API_USER}:${API_PASSWORD}" \
     -X GET "${API_URL}"

echo -e "\n\nAPI response code:"
curl -s -k -u "${API_USER}:${API_PASSWORD}" \
     -X GET "${API_URL}" -o /dev/null -w "%{http_code}"
echo
