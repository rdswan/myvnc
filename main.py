#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""
Main entry point for the MyVNC application

This script starts the web server for the MyVNC application.

Configuration:
- server_config.json: Contains server settings (host, port, authentication, etc.)
- lsf_config.json: LSF-related settings, including the path to the LSF environment file
                  that will be sourced before starting the server to make LSF commands available
"""

import sys
import argparse
import socket
import subprocess
from pathlib import Path
import logging
import os
from myvnc.web.server import run_server, load_server_config, load_lsf_config, get_fully_qualified_hostname
from myvnc.utils.log_manager import setup_logging, get_logger, get_current_log_file

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="MyVNC Web Server")
    parser.add_argument('--host', help='Host to bind to (overrides config file)')
    parser.add_argument('--port', type=int, help='Port to bind to (overrides config file)')
    parser.add_argument('--config', help='Path to custom config file')
    parser.add_argument('--auth', choices=['', 'Entra'], default=None, 
                      help='Authentication method: empty for none, "Entra" for Microsoft Entra ID')
    parser.add_argument('--logdir', help='Path to log directory (overrides config file)')
    
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
    
    # Load configuration
    config = load_server_config()
    lsf_config = load_lsf_config()
    
    # Set a fallback log directory that is user-writable
    config_log_dir = config.get('logdir', '/localdev/myvnc/logs')
    
    # If command line arg for logdir is provided, use it
    if args.logdir:
        log_dir = args.logdir
    # Otherwise try to use the config value if it's writable
    elif os.access(config_log_dir, os.W_OK) or os.access(os.path.dirname(config_log_dir), os.W_OK):
        log_dir = config_log_dir
    # Otherwise fall back to a temp directory
    else:
        log_dir = '/tmp/myvnc/logs'
        print(f"Log directory {config_log_dir} is not writable, falling back to {log_dir}")
    
    # Update the config to use the correct log directory
    config['logdir'] = log_dir
    
    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)
    
    # Make sure server PID file uses the same log directory
    pid_file = os.path.join(log_dir, 'myvnc_server.pid')
    
    # Record our PID for other components to find
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
    
    # Reset any existing loggers to ensure we start fresh
    logging.getLogger('myvnc').handlers = []
    
    # Set up logging with explicit config
    logger = setup_logging(config=config)
    
    # Verify we have a log file
    log_file = get_current_log_file()
    if log_file:
        logger.info(f"Server starting - Log file: {log_file.absolute()}")
    else:
        logger.warning("No log file was created!")
    
    logger.info(f"Using LSF environment file: {lsf_config.get('env_file', 'Not configured')}")
    
    # Use command line arguments if provided, otherwise use config file
    host = args.host or config.get("host")
    port = args.port or config.get("port")
    
    # Always resolve to FQDN if host is localhost or simple hostname
    if host == "localhost" or host == "127.0.0.1" or host == "0.0.0.0" or (host and host.count('.') == 0):
        original_host = host
        host = get_fully_qualified_hostname(host)
        if host != original_host:
            logger.info(f"Resolved {original_host} to FQDN: {host}")
            # Update config to ensure consistency
            config["host"] = host
    
    # Override authentication setting if provided
    if args.auth is not None:
        config["authentication"] = args.auth
        logger.info(f"Using authentication method: {args.auth or 'None'}")
    else:
        logger.info(f"Using authentication method from config: {config.get('authentication') or 'None'}")
    
    # Run the server with the same config we've been using
    run_server(host=host, port=port, config=config) 