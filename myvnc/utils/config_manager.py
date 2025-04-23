import json
import os
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
        if config_dir is None:
            self.config_dir = Path(__file__).parent.parent.parent / "config"
        else:
            self.config_dir = Path(config_dir)
        
        # Load configurations
        self.vnc_config = self._load_config("vnc_config.json")
        self.lsf_config = self._load_config("lsf_config.json")
    
    def _load_config(self, filename):
        """
        Load a configuration file
        
        Args:
            filename: Name of the configuration file
            
        Returns:
            Dict containing the configuration
        
        Raises:
            RuntimeError: If the file is not found or contains invalid JSON
        """
        config_path = self.config_dir / filename
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"Configuration file {filename} not found at {config_path}")
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON in configuration file {filename}")
    
    def get_vnc_defaults(self):
        """Get the default VNC settings"""
        return self.vnc_config["default_settings"]
    
    def get_lsf_defaults(self):
        """Get the default LSF settings"""
        return self.lsf_config["default_settings"]
    
    def get_available_window_managers(self):
        """Get the list of available window managers"""
        return self.vnc_config["available_window_managers"]
    
    def get_available_resolutions(self):
        """Get the list of available resolutions"""
        return self.vnc_config["available_resolutions"]
    
    def get_available_sites(self):
        """Get the list of available sites"""
        sites = self.lsf_config.get("available_sites", [])
        # Return just the site names
        return [site["name"] for site in sites]
    
    def get_site_domain(self, site_name):
        """
        Get the domain for a specific site
        
        Args:
            site_name: Name of the site
            
        Returns:
            Domain name or None if not found
        """
        sites = self.lsf_config.get("available_sites", [])
        for site in sites:
            if site["name"] == site_name:
                return site["domain"]
        return None
    
    def get_available_queues(self):
        """Get the list of available LSF queues"""
        return self.lsf_config["available_queues"]
    
    def get_memory_options(self):
        """Get the list of available memory options"""
        return self.lsf_config["memory_options_mb"]
    
    def get_core_options(self):
        """Get the list of available core options"""
        return self.lsf_config["core_options"] 