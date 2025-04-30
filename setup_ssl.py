#!/usr/bin/env python3

# Script to set up SSL certificates in the MyVNC configuration

import json
import os
import sys
from pathlib import Path

def main():
    # Get the absolute path to this script's directory
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    
    # Server config path
    config_path = script_dir / "config" / "default_server_config.json"
    
    # SSL cert paths
    ssl_cert = script_dir / "config" / "ssl" / "cert.pem"
    ssl_key = script_dir / "config" / "ssl" / "key.pem"
    ssl_ca_chain = script_dir / "config" / "ssl" / "ca-chain.pem"
    
    # Verify files exist
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    
    if not ssl_cert.exists():
        print(f"Error: SSL certificate not found: {ssl_cert}")
        sys.exit(1)
    
    if not ssl_key.exists():
        print(f"Error: SSL key not found: {ssl_key}")
        sys.exit(1)
    
    # Load current config
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in config file: {config_path}")
        sys.exit(1)
    
    # Update SSL configuration with absolute paths
    config['ssl_cert'] = str(ssl_cert.absolute())
    config['ssl_key'] = str(ssl_key.absolute())
    
    # Add CA chain if it exists
    if ssl_ca_chain.exists():
        config['ssl_ca_chain'] = str(ssl_ca_chain.absolute())
        print(f"CA chain bundle found: {ssl_ca_chain}")
    else:
        print(f"Note: CA chain bundle not found at {ssl_ca_chain} (optional)")
        # Set to empty string if not present
        config['ssl_ca_chain'] = ""
    
    # Save updated config
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Successfully updated config with SSL certificate paths:")
        print(f"Certificate: {config['ssl_cert']}")
        print(f"Key: {config['ssl_key']}")
        if config['ssl_ca_chain']:
            print(f"CA Chain: {config['ssl_ca_chain']}")
    except Exception as e:
        print(f"Error updating config file: {e}")
        sys.exit(1)
    
    print("\nYou can now restart the server with: python manage.py restart")

if __name__ == "__main__":
    main() 