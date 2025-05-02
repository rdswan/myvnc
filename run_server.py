#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""
Simple script to start the MyVNC server
"""

import sys
import argparse
from pathlib import Path
import os

# Get the absolute path of the script directory
script_dir = Path(__file__).resolve().parent

# Change to the script directory to ensure configs are found
os.chdir(script_dir)

# Add the current directory to the path
sys.path.insert(0, str(script_dir))

# Import the server module and other necessary functions
from myvnc.web.server import run_server, load_server_config
from myvnc.utils.log_manager import setup_logging, get_logger

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="MyVNC Web Server")
    parser.add_argument('--host', default="0.0.0.0", help='Host to bind to (overrides config file)')
    parser.add_argument('--port', type=int, default=9143, help='Port to bind to (overrides config file)')
    
    # Add configuration file path arguments
    parser.add_argument('--config_dir', help='Path to config directory (env var: MYVNC_CONFIG_DIR)')
    parser.add_argument('--server_config_file', help='Path to server config file (env var: MYVNC_SERVER_CONFIG_FILE)')
    parser.add_argument('--vnc_config_file', help='Path to VNC config file (env var: MYVNC_VNC_CONFIG_FILE)')
    parser.add_argument('--lsf_config_file', help='Path to LSF config file (env var: MYVNC_LSF_CONFIG_FILE)')
    
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Set environment variables from command-line arguments if provided
    if args.config_dir:
        os.environ["MYVNC_CONFIG_DIR"] = args.config_dir
    if args.server_config_file:
        os.environ["MYVNC_SERVER_CONFIG_FILE"] = args.server_config_file
    if args.vnc_config_file:
        os.environ["MYVNC_VNC_CONFIG_FILE"] = args.vnc_config_file
    if args.lsf_config_file:
        os.environ["MYVNC_LSF_CONFIG_FILE"] = args.lsf_config_file
        
    # Load server configuration
    config = load_server_config()
    
    # Set up logging with config
    setup_logging(config=config)
    logger = get_logger()
    
    # Run the server
    logger.info(f"Starting MyVNC server from directory: {os.getcwd()}")
    run_server(host=args.host, port=args.port, config=config) 