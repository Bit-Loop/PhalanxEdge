#!/bin/bash
# filepath: /home/ubuntu/.ansible/scripts/create_proxmox_api_token.sh
# Script to create a Proxmox API token for Ansible authentication

# Set variables
API_USER="root@pam"
API_PASSWORD=$(cat ~/.ansible/.api_pass | tr -d '\n\r')
API_HOST="192.168.1.47"
API_URL="https://${API_HOST}:8006"
TOKEN_ID="ansible-automation"
TOKEN_FILE=~/.ansible/.proxmox_token
TOKEN_VALUE_FILE=~/.ansible/.proxmox_token_value

# Get ticket first for authentication
echo "Getting authentication ticket..."
TICKET_RESPONSE=$(curl -s -k -d "username=${API_USER}&password=${API_PASSWORD}" \
    "${API_URL}/api2/json/access/ticket")

echo "Ticket response:"
echo "$TICKET_RESPONSE" | grep -v password

# Extract ticket and CSRF token
TICKET=$(echo "$TICKET_RESPONSE" | grep -o '"ticket":"[^"]*' | cut -d'"' -f4)
CSRF_TOKEN=$(echo "$TICKET_RESPONSE" | grep -o '"CSRFPreventionToken":"[^"]*' | cut -d'"' -f4)

if [ -z "$TICKET" ]; then
    echo "Failed to get authentication ticket. Check credentials."
    exit 1
fi

echo "Successfully authenticated"
echo "Ticket: ${TICKET:0:10}..."
echo "CSRF Token: ${CSRF_TOKEN:0:10}..."

# Check if token already exists
echo "Checking if token already exists..."
TOKEN_CHECK=$(curl -s -k \
    -b "PVEAuthCookie=$TICKET" \
    -H "CSRFPreventionToken: $CSRF_TOKEN" \
    "${API_URL}/api2/json/access/users/${API_USER}/token/${TOKEN_ID}")

# Parse response to check if token exists
if echo "$TOKEN_CHECK" | grep -q '"privsep"'; then
    echo "Token $TOKEN_ID already exists. Deleting it first..."
    # Delete the existing token
    curl -s -k \
        -b "PVEAuthCookie=$TICKET" \
        -H "CSRFPreventionToken: $CSRF_TOKEN" \
        -X DELETE \
        "${API_URL}/api2/json/access/users/${API_USER}/token/${TOKEN_ID}"
    echo "Existing token deleted."
fi

# Create a new API token
echo "Creating API token for $TOKEN_ID..."
TOKEN_CREATE_RESPONSE=$(curl -s -k \
    -b "PVEAuthCookie=$TICKET" \
    -H "CSRFPreventionToken: $CSRF_TOKEN" \
    -X POST \
    "${API_URL}/api2/json/access/users/${API_USER}/token/${TOKEN_ID}" \
    -d "privsep=0")

echo "Token creation response: $TOKEN_CREATE_RESPONSE"

# Extract the token value from the creation response
TOKEN_VALUE=$(echo "$TOKEN_CREATE_RESPONSE" | grep -o '"value":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN_VALUE" ]; then
    echo "Failed to extract token value from response. Check permissions."
    exit 1
fi

# Save token ID and token value to files
echo "${TOKEN_ID}" > $TOKEN_FILE
chmod 600 $TOKEN_FILE

echo "${TOKEN_VALUE}" > $TOKEN_VALUE_FILE
chmod 600 $TOKEN_VALUE_FILE

# Create token info file for Ansible
cat > ~/.ansible/.proxmox_token_info << EOF
# Proxmox API token information
# Created: $(date)
proxmox_api_token_id: "${API_USER}!${TOKEN_ID}"
proxmox_api_token_value: "${TOKEN_VALUE}"
EOF
chmod 600 ~/.ansible/.proxmox_token_info

echo "Token ID saved to $TOKEN_FILE"
echo "Token value saved to $TOKEN_VALUE_FILE"
echo "Token information for Ansible saved to ~/.ansible/.proxmox_token_info"
