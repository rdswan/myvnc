import json
from pathlib import Path

class ConfigManager:
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.vnc_config = self._load_config("vnc_config.json")
        self.lsf_config = self._load_config("lsf_config.json")
    
    def _load_config(self, filename):
        config_path = self.config_dir / filename
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"Configuration file {filename} not found")
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON in configuration file {filename}")
    
    def get_vnc_defaults(self):
        return self.vnc_config["default_settings"]
    
    def get_lsf_defaults(self):
        return self.lsf_config["default_settings"]
    
    def get_available_window_managers(self):
        return self.vnc_config["available_window_managers"]
    
    def get_available_resolutions(self):
        return self.vnc_config["available_resolutions"]
    
    def get_available_queues(self):
        return self.lsf_config["available_queues"]
    
    def get_memory_options(self):
        return self.lsf_config["memory_options_mb"]
    
    def get_core_options(self):
        return self.lsf_config["core_options"] 