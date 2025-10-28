#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0

"""
Configuration file linter for MyVNC
Validates JSON syntax and configuration consistency
"""

import json
import sys
import os
from pathlib import Path


class ConfigLinter:
    """Lints configuration files for MyVNC"""
    
    def __init__(self, config_dir):
        self.config_dir = Path(config_dir)
        self.errors = []
        self.warnings = []
        self.info = []
        
    def run(self):
        """Run all linting checks"""
        print(f"🔍 Linting configuration files in: {self.config_dir}\n")
        
        # Check if directory exists
        if not self.config_dir.exists():
            print(f"❌ ERROR: Config directory does not exist: {self.config_dir}")
            return False
        
        # Find all JSON files
        json_files = list(self.config_dir.glob("*.json"))
        
        if not json_files:
            print(f"❌ ERROR: No JSON files found in {self.config_dir}")
            return False
        
        print(f"Found {len(json_files)} config file(s):\n")
        
        # Lint each file
        for json_file in sorted(json_files):
            print(f"  Checking: {json_file.name}")
            self._lint_file(json_file)
        
        # Print results
        print("\n" + "="*70)
        self._print_results()
        
        return len(self.errors) == 0
    
    def _lint_file(self, filepath):
        """Lint a single configuration file"""
        try:
            with open(filepath, 'r') as f:
                config = json.load(f)
            
            self.info.append(f"✓ {filepath.name}: Valid JSON syntax")
            
            # Run specific checks based on filename
            if filepath.name == "server_config.json":
                self._check_server_config(config, filepath.name)
            elif filepath.name == "lsf_config.json":
                self._check_lsf_config(config, filepath.name)
            elif filepath.name == "vnc_config.json":
                self._check_vnc_config(config, filepath.name)
            elif filepath.name == "ldap_config.json":
                self._check_ldap_config(config, filepath.name)
            elif filepath.name == "entra_config.json":
                self._check_entra_config(config, filepath.name)
                
        except json.JSONDecodeError as e:
            self.errors.append(f"❌ {filepath.name}: JSON Syntax Error at line {e.lineno}, col {e.colno}: {e.msg}")
        except Exception as e:
            self.errors.append(f"❌ {filepath.name}: {str(e)}")
    
    def _check_server_config(self, config, filename):
        """Validate server_config.json"""
        required = ["host", "port", "datadir", "logdir", "managers"]
        
        for field in required:
            if field not in config:
                self.warnings.append(f"  ⚠ {filename}: Missing recommended field '{field}'")
        
        # Check managers is a list
        if "managers" in config:
            if not isinstance(config["managers"], list):
                self.errors.append(f"  ❌ {filename}: 'managers' must be a list, got {type(config['managers']).__name__}")
            elif len(config["managers"]) == 0:
                self.warnings.append(f"  ⚠ {filename}: 'managers' list is empty")
        
        # Check manager_overrides if present
        if "manager_overrides" in config:
            mo = config["manager_overrides"]
            if not isinstance(mo, dict):
                self.errors.append(f"  ❌ {filename}: 'manager_overrides' must be a dict")
            else:
                expected_keys = ["allow_cores_override", "allow_memory_override", 
                               "allow_window_manager_override", "allow_queue_override", 
                               "allow_os_override"]
                for key in expected_keys:
                    if key not in mo:
                        self.warnings.append(f"  ⚠ {filename}: Missing 'manager_overrides.{key}'")
                    elif not isinstance(mo[key], bool):
                        self.errors.append(f"  ❌ {filename}: 'manager_overrides.{key}' must be boolean")
        
        # Check port is integer
        if "port" in config:
            if not isinstance(config["port"], int):
                self.errors.append(f"  ❌ {filename}: 'port' must be integer, got {type(config['port']).__name__}")
    
    def _check_lsf_config(self, config, filename):
        """Validate lsf_config.json"""
        required = ["available_queues", "core_options", "memory_options_gb", "os_options"]
        
        for field in required:
            if field not in config:
                self.errors.append(f"  ❌ {filename}: Missing required field '{field}'")
        
        # Check available_queues
        if "available_queues" in config:
            if not isinstance(config["available_queues"], list):
                self.errors.append(f"  ❌ {filename}: 'available_queues' must be a list")
            elif len(config["available_queues"]) == 0:
                self.errors.append(f"  ❌ {filename}: 'available_queues' cannot be empty")
        
        # Check enabled_queues if present (consistency check)
        if "enabled_queues" in config and "available_queues" in config:
            enabled = set(config["enabled_queues"])
            available = set(config["available_queues"])
            invalid = enabled - available
            if invalid:
                self.errors.append(f"  ❌ {filename}: 'enabled_queues' contains values not in 'available_queues': {invalid}")
        
        # Check core_options
        if "core_options" in config:
            if not isinstance(config["core_options"], list):
                self.errors.append(f"  ❌ {filename}: 'core_options' must be a list")
            elif not all(isinstance(x, int) for x in config["core_options"]):
                self.errors.append(f"  ❌ {filename}: 'core_options' must contain only integers")
        
        # Check enabled_core_options if present (consistency check)
        if "enabled_core_options" in config and "core_options" in config:
            enabled = set(config["enabled_core_options"])
            available = set(config["core_options"])
            invalid = enabled - available
            if invalid:
                self.errors.append(f"  ❌ {filename}: 'enabled_core_options' contains values not in 'core_options': {invalid}")
        
        # Check memory_options_gb
        if "memory_options_gb" in config:
            if not isinstance(config["memory_options_gb"], list):
                self.errors.append(f"  ❌ {filename}: 'memory_options_gb' must be a list")
            elif not all(isinstance(x, int) for x in config["memory_options_gb"]):
                self.errors.append(f"  ❌ {filename}: 'memory_options_gb' must contain only integers")
        
        # Check enabled_memory_options_gb if present (consistency check)
        if "enabled_memory_options_gb" in config and "memory_options_gb" in config:
            enabled = set(config["enabled_memory_options_gb"])
            available = set(config["memory_options_gb"])
            invalid = enabled - available
            if invalid:
                self.errors.append(f"  ❌ {filename}: 'enabled_memory_options_gb' contains values not in 'memory_options_gb': {invalid}")
        
        # Check os_options
        if "os_options" in config:
            if not isinstance(config["os_options"], list):
                self.errors.append(f"  ❌ {filename}: 'os_options' must be a list")
            else:
                os_names = []
                for idx, os_opt in enumerate(config["os_options"]):
                    if not isinstance(os_opt, dict):
                        self.errors.append(f"  ❌ {filename}: 'os_options[{idx}]' must be a dict")
                    else:
                        if "name" not in os_opt:
                            self.errors.append(f"  ❌ {filename}: 'os_options[{idx}]' missing 'name' field")
                        else:
                            os_names.append(os_opt["name"])
                        if "select" not in os_opt:
                            self.errors.append(f"  ❌ {filename}: 'os_options[{idx}]' missing 'select' field")
        
        # Check enabled_os_options if present (consistency check)
        if "enabled_os_options" in config and "os_options" in config:
            enabled = set(config["enabled_os_options"])
            available = {os_opt["name"] for os_opt in config["os_options"] if isinstance(os_opt, dict) and "name" in os_opt}
            invalid = enabled - available
            if invalid:
                self.errors.append(f"  ❌ {filename}: 'enabled_os_options' contains names not in 'os_options': {invalid}")
        
        # Check default_settings
        if "default_settings" in config:
            defaults = config["default_settings"]
            if not isinstance(defaults, dict):
                self.errors.append(f"  ❌ {filename}: 'default_settings' must be a dict")
            else:
                # Validate default queue is available
                if "queue" in defaults and "available_queues" in config:
                    if defaults["queue"] not in config["available_queues"]:
                        self.warnings.append(f"  ⚠ {filename}: default 'queue' '{defaults['queue']}' not in available_queues")
    
    def _check_vnc_config(self, config, filename):
        """Validate vnc_config.json"""
        required = ["available_window_managers", "available_resolutions"]
        
        for field in required:
            if field not in config:
                self.errors.append(f"  ❌ {filename}: Missing required field '{field}'")
        
        # Check available_window_managers
        if "available_window_managers" in config:
            if not isinstance(config["available_window_managers"], list):
                self.errors.append(f"  ❌ {filename}: 'available_window_managers' must be a list")
            elif len(config["available_window_managers"]) == 0:
                self.errors.append(f"  ❌ {filename}: 'available_window_managers' cannot be empty")
        
        # Check enabled_window_managers if present (consistency check)
        if "enabled_window_managers" in config and "available_window_managers" in config:
            enabled = set(config["enabled_window_managers"])
            available = set(config["available_window_managers"])
            invalid = enabled - available
            if invalid:
                self.errors.append(f"  ❌ {filename}: 'enabled_window_managers' contains values not in 'available_window_managers': {invalid}")
        
        # Check available_resolutions
        if "available_resolutions" in config:
            if not isinstance(config["available_resolutions"], list):
                self.errors.append(f"  ❌ {filename}: 'available_resolutions' must be a list")
            elif len(config["available_resolutions"]) == 0:
                self.errors.append(f"  ❌ {filename}: 'available_resolutions' cannot be empty")
        
        # Check enabled_resolutions if present (consistency check)
        if "enabled_resolutions" in config and "available_resolutions" in config:
            enabled = set(config["enabled_resolutions"])
            available = set(config["available_resolutions"])
            invalid = enabled - available
            if invalid:
                self.errors.append(f"  ❌ {filename}: 'enabled_resolutions' contains values not in 'available_resolutions': {invalid}")
        
        # Check window_manager_configs if present
        if "window_manager_configs" in config:
            if not isinstance(config["window_manager_configs"], dict):
                self.errors.append(f"  ❌ {filename}: 'window_manager_configs' must be a dict")
        
        # Check default_settings
        if "default_settings" in config:
            defaults = config["default_settings"]
            if not isinstance(defaults, dict):
                self.errors.append(f"  ❌ {filename}: 'default_settings' must be a dict")
    
    def _check_ldap_config(self, config, filename):
        """Validate ldap_config.json if present"""
        required = ["server", "base_dn"]
        
        for field in required:
            if field not in config:
                self.warnings.append(f"  ⚠ {filename}: Missing field '{field}'")
    
    def _check_entra_config(self, config, filename):
        """Validate entra_config.json if present"""
        required = ["client_id", "tenant_id"]
        
        for field in required:
            if field not in config:
                self.warnings.append(f"  ⚠ {filename}: Missing field '{field}'")
    
    def _print_results(self):
        """Print linting results"""
        if self.errors:
            print("\n❌ ERRORS Found:")
            print("-" * 70)
            for error in self.errors:
                print(error)
        
        if self.warnings:
            print("\n⚠ WARNINGS:")
            print("-" * 70)
            for warning in self.warnings:
                print(warning)
        
        if self.info:
            print("\n✓ INFO:")
            print("-" * 70)
            for info in self.info:
                print(info)
        
        print("\n" + "="*70)
        
        if not self.errors and not self.warnings:
            print("✅ All configuration files are valid!")
            return True
        
        if self.errors:
            print(f"❌ Found {len(self.errors)} error(s)")
            return False
        else:
            print(f"✓ All critical checks passed ({len(self.warnings)} warning(s))")
            return True


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        config_dir = Path(__file__).parent / "config"
    else:
        config_dir = sys.argv[1]
    
    linter = ConfigLinter(config_dir)
    success = linter.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
