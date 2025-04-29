#!/usr/bin/env python3
"""
Main entry point for the MyVNC application

This script starts the web server for the MyVNC application.

Configuration:
- default_server_config.json: Contains server settings (host, port, authentication, etc.)
- default_lsf_config.json: LSF-related settings, including the path to the LSF environment file
                        that will be sourced before starting the server to make LSF commands available
"""

import sys
import argparse
from pathlib import Path
import logging
from myvnc.web.server import run_server, load_server_config, load_lsf_config
from myvnc.utils.log_manager import setup_logging, get_logger, get_current_log_file

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="MyVNC Web Server")
    parser.add_argument('--host', help='Host to bind to (overrides config file)')
    parser.add_argument('--port', type=int, help='Port to bind to (overrides config file)')
    parser.add_argument('--config', help='Path to custom config file')
    parser.add_argument('--auth', choices=['', 'Entra'], default=None, 
                      help='Authentication method: empty for none, "Entra" for Microsoft Entra ID')
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Load configuration
    config = load_server_config()
    lsf_config = load_lsf_config()
    
    # Reset any existing loggers to ensure we start fresh
    logging.getLogger('myvnc').handlers = []
    
    # Set up logging with explicit config
    logger = setup_logging(config=config)
    
    # Verify we have a log file
    log_file = get_current_log_file()
    if log_file:
        logger.info(f"Created log file at: {log_file.absolute()}")
    else:
        logger.warning("No log file was created!")
    
    logger.info(f"Using LSF environment file: {lsf_config.get('env_file', 'Not configured')}")
    
    # Use command line arguments if provided, otherwise use config file
    host = args.host or config.get("host")
    port = args.port or config.get("port")
    
    # Override authentication setting if provided
    if args.auth is not None:
        config["authentication"] = args.auth
        logger.info(f"Using authentication method: {args.auth or 'None'}")
    else:
        logger.info(f"Using authentication method from config: {config.get('authentication') or 'None'}")
    
    # Run the server with the same config we've been using
    run_server(host=host, port=port, config=config) 