#!/bin/bash
# Setup script for Microsoft Entra ID authentication testing

# Set to 'entra' to use Entra ID authentication, or 'ldap' to use LDAP
export AUTH_METHOD="entra"

# Microsoft Entra ID settings
# Replace these with your actual tenant ID, client ID, and client secret
export ENTRA_TENANT_ID="your-tenant-id"
export ENTRA_CLIENT_ID="your-client-id"
export ENTRA_CLIENT_SECRET="your-client-secret"

# For local testing, use localhost
export ENTRA_REDIRECT_URI="http://localhost:8000/auth/callback"

# Start the server
cd "$(dirname "$0")"
echo "Starting VNC Manager with Entra ID authentication..."
python3 myvnc/web/server.py 