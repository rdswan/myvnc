#!/usr/bin/env python3
"""
Main entry point for the MyVNC application
"""

import sys
import argparse
from pathlib import Path
from myvnc.web.server import run_server, load_server_config

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="MyVNC Web Server")
    parser.add_argument('--host', help='Host to bind to (overrides config file)')
    parser.add_argument('--port', type=int, help='Port to bind to (overrides config file)')
    parser.add_argument('--config', help='Path to custom config file')
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Load configuration
    config = load_server_config()
    
    # Use command line arguments if provided, otherwise use config file
    host = args.host or config.get("host")
    port = args.port or config.get("port")
    
    # Run the server
    run_server(host=host, port=port) 