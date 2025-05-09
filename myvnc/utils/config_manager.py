# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
import json
import os
import logging
from pathlib import Path

class ConfigManager:
    """Manages application configuration loaded from JSON files"""
    
    def __init__(self, config_dir=None):
        """
        Initialize the configuration manager
        
        Args:
            config_dir: Directory containing configuration files. 
                       If None, defaults to ../config relative to this file
        """
        # Set up logging
        self.logger = logging.getLogger('myvnc')
        
        # Check for environment variable for config directory
        if config_dir is None:
            # Priority: Provided argument, environment variable, default path
            env_config_dir = os.environ.get("MYVNC_CONFIG_DIR")
            if env_config_dir:
                self.config_dir = Path(env_config_dir)
                # Check the source of the config directory
                config_source = os.environ.get("MYVNC_CONFIG_SOURCE", "env")
                if config_source == "cli":
                    self.logger.info(f"ConfigManager: Using config directory from command-line argument: {env_config_dir}")
                else:
                    self.logger.info(f"ConfigManager: Using config directory from environment variable: {env_config_dir}")
            else:
                # Use default path
                default_path = Path(__file__).parent.parent.parent / "config"
                self.config_dir = default_path
                self.logger.info(f"ConfigManager: Using default config directory: {default_path}")
        else:
            # Explicit path provided to constructor
            self.config_dir = Path(config_dir)
            self.logger.info(f"ConfigManager: Using explicitly provided config directory: {config_dir}")
        
        # Load configurations - use the default_prefix in filenames
        self.vnc_config = self._load_config("vnc_config.json", os.environ.get("MYVNC_VNC_CONFIG_FILE"))
        self.lsf_config = self._load_config("lsf_config.json", os.environ.get("MYVNC_LSF_CONFIG_FILE"))
    
    def _load_config(self, filename, env_path=None):
        """
        Load a configuration file
        
        Args:
            filename: Name of the configuration file
            env_path: Path from environment variable if available
            
        Returns:
            Dict containing the configuration
        
        Raises:
            RuntimeError: If the file is not found or contains invalid JSON
        """
        # Priority: Environment variable path, config_dir/filename
        if env_path and os.path.exists(env_path):
            config_path = Path(env_path)
            self.logger.info(f"ConfigManager: Loading {filename} from environment variable path: {config_path}")
        else:
            config_path = self.config_dir / filename
            self.logger.info(f"ConfigManager: Loading {filename} from config directory: {config_path}")
            
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.logger.info(f"ConfigManager: Successfully loaded {filename} from {config_path}")
                return config
        except FileNotFoundError:
            # If the file has default_ prefix and is not found, try without prefix for backward compatibility
            if filename.startswith("default_"):
                alt_filename = filename.replace("default_", "", 1)
                alt_path = self.config_dir / alt_filename
                self.logger.info(f"ConfigManager: Trying alternate filename: {alt_path}")
                try:
                    with open(alt_path, 'r') as f:
                        config = json.load(f)
                        self.logger.info(f"ConfigManager: Successfully loaded {alt_filename} from {alt_path}")
                        return config
                except FileNotFoundError:
                    self.logger.error(f"ConfigManager: Configuration file {filename} not found at {config_path} (also tried {alt_path})")
                    raise RuntimeError(f"Configuration file {filename} not found at {config_path} (also tried {alt_path})")
                except json.JSONDecodeError:
                    self.logger.error(f"ConfigManager: Invalid JSON in configuration file {alt_filename}")
                    raise RuntimeError(f"Invalid JSON in configuration file {alt_filename}")
            self.logger.error(f"ConfigManager: Configuration file {filename} not found at {config_path}")
            raise RuntimeError(f"Configuration file {filename} not found at {config_path}")
        except json.JSONDecodeError:
            self.logger.error(f"ConfigManager: Invalid JSON in configuration file {filename}")
            raise RuntimeError(f"Invalid JSON in configuration file {filename}")
    
    def get_vnc_defaults(self):
        """Get the default VNC settings"""
        return self.vnc_config["default_settings"]
    
    def get_lsf_defaults(self):
        """Get the default LSF settings"""
        defaults = self.lsf_config["default_settings"].copy()
        
        # Convert memory_mb to memory_gb if needed for backward compatibility
        if "memory_mb" in defaults and "memory_gb" not in defaults:
            defaults["memory_gb"] = max(1, defaults.get("memory_mb", 16384) // 1024)
            
        # Ensure memory_gb is always present
        if "memory_gb" not in defaults:
            defaults["memory_gb"] = 16
            
        return defaults
    
    def get_available_window_managers(self):
        """Get the list of available window managers"""
        return self.vnc_config["available_window_managers"]
    
    def get_available_resolutions(self):
        """Get the list of available resolutions"""
        return self.vnc_config["available_resolutions"]
    
    def get_available_sites(self):
        """Get the list of available sites"""
        try:
            sites = self.lsf_config.get("available_sites", [])
            # Return just the site names
            return [site["name"] for site in sites]
        except (KeyError, TypeError):
            print("Warning: available_sites not found or has invalid format in lsf_config.json")
            # Return a default list of sites if none are found
            return ["Toronto", "Austin", "Bangalore"]
    
    def get_site_domain(self, site_name):
        """
        Get the domain for a specific site
        
        Args:
            site_name: Name of the site
            
        Returns:
            Domain name or None if not found
        """
        try:
            sites = self.lsf_config.get("available_sites", [])
            for site in sites:
                if site["name"] == site_name:
                    return site["domain"]
            
            # If not found in config, use default mappings
            default_mappings = {
                "Toronto": "yyz",
                "Austin": "aus",
                "Bangalore": "bglr"
            }
            return default_mappings.get(site_name)
        except (KeyError, TypeError):
            # If there's an error, use default mappings
            default_mappings = {
                "Toronto": "yyz",
                "Austin": "aus",
                "Bangalore": "bglr"
            }
            return default_mappings.get(site_name)
    
    def get_available_queues(self):
        """Get the list of available LSF queues"""
        return self.lsf_config["available_queues"]
    
    def get_memory_options(self):
        """Get the list of available memory options in GB"""
        try:
            # Always use GB options
            if "memory_options_gb" in self.lsf_config:
                return self.lsf_config["memory_options_gb"]
            
            # Convert MB options to GB if GB options are not available
            if "memory_options_mb" in self.lsf_config:
                mb_options = self.lsf_config["memory_options_mb"]
                return [max(1, mb // 1024) for mb in mb_options]
                
            # Default memory options in GB if nothing is specified
            return [2, 4, 8, 16, 32]
        except KeyError:
            # Default memory options in GB if none are specified
            return [2, 4, 8, 16, 32]
    
    def get_core_options(self):
        """Get the list of available core options"""
        return self.lsf_config["core_options"]
        
    def get_vnc_config(self):
        """Get the full VNC configuration"""
        return self.vnc_config 
