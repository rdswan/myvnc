#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0

import os
import json
import logging
from pathlib import Path
from myvnc.utils.config_manager import ConfigManager

# Global configuration manager instance
_config_manager = None

def get_config_manager(config_dir=None):
    """
    Get or create a ConfigManager instance
    
    Args:
        config_dir: Optional directory containing configuration files
        
    Returns:
        ConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    return _config_manager

def load_server_config(config_dir=None):
    """
    Load server configuration
    
    Args:
        config_dir: Optional directory containing configuration files
        
    Returns:
        Dictionary with server configuration
    """
    config_path = os.environ.get("MYVNC_SERVER_CONFIG_FILE")
    
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logging.error(f"Error loading server config from {config_path}: {e}")
    
    # If environment variable not set or file not found, load from config directory
    if config_dir is None:
        config_dir = os.environ.get("MYVNC_CONFIG_DIR")
        if not config_dir:
            # Use default path relative to this file
            config_dir = Path(__file__).parent.parent.parent / "config"
    
    config_path = Path(config_dir) / "server_config.json"
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logging.error(f"Error loading server config from {config_path}: {e}")
        # Return default configuration
        return {
            "host": "0.0.0.0",
            "port": 8080,
            "debug": False,
            "ssl": False
        }

def load_lsf_config(config_dir=None):
    """
    Load LSF configuration
    
    Args:
        config_dir: Optional directory containing configuration files
        
    Returns:
        Dictionary with LSF configuration
    """
    cm = get_config_manager(config_dir)
    return cm.lsf_config

def load_vnc_config(config_dir=None):
    """
    Load VNC configuration
    
    Args:
        config_dir: Optional directory containing configuration files
        
    Returns:
        Dictionary with VNC configuration
    """
    cm = get_config_manager(config_dir)
    return cm.vnc_config

def get_logger(name="myvnc"):
    """
    Get a configured logger
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure the logger if it hasn't already been configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
    
    return logger 