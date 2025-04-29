#!/usr/bin/env python3
"""
Simple script to start the MyVNC server
"""

import sys
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

if __name__ == "__main__":
    # Load server configuration
    config = load_server_config()
    
    # Set up logging with config
    setup_logging(config=config)
    logger = get_logger()
    
    # Run the server
    logger.info(f"Starting MyVNC server from directory: {os.getcwd()}")
    run_server(host="0.0.0.0", port=9143, config=config) 