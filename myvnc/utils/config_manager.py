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

        # Load SLURM config if it exists (non-fatal if missing)
        self.slurm_config = self._load_config(
            "slurm_config.json", os.environ.get("MYVNC_SLURM_CONFIG_FILE"), optional=True
        )
        if self.slurm_config is None:
            self.logger.info("ConfigManager: slurm_config.json not found, SLURM support unavailable")
    
    def _load_config(self, filename, env_path=None, optional=False):
        """
        Load a configuration file
        
        Args:
            filename: Name of the configuration file
            env_path: Path from environment variable if available
            optional: If True, a missing file is not an error. Instead of logging
                      an error and raising, this logs an informational message and
                      returns None.
            
        Returns:
            Dict containing the configuration, or None if optional and not found
        
        Raises:
            RuntimeError: If a required file is not found or contains invalid JSON
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
                    if optional:
                        self.logger.info(f"ConfigManager: Optional configuration file {filename} not found at {config_path} (also tried {alt_path})")
                        return None
                    self.logger.error(f"ConfigManager: Configuration file {filename} not found at {config_path} (also tried {alt_path})")
                    raise RuntimeError(f"Configuration file {filename} not found at {config_path} (also tried {alt_path})")
                except json.JSONDecodeError:
                    self.logger.error(f"ConfigManager: Invalid JSON in configuration file {alt_filename}")
                    raise RuntimeError(f"Invalid JSON in configuration file {alt_filename}")
            if optional:
                self.logger.info(f"ConfigManager: Optional configuration file {filename} not found at {config_path}")
                return None
            self.logger.error(f"ConfigManager: Configuration file {filename} not found at {config_path}")
            raise RuntimeError(f"Configuration file {filename} not found at {config_path}")
        except json.JSONDecodeError:
            self.logger.error(f"ConfigManager: Invalid JSON in configuration file {filename}")
            raise RuntimeError(f"Invalid JSON in configuration file {filename}")
    
    def get_vnc_defaults(self):
        """Get the default VNC settings"""
        return self.vnc_config["default_settings"]

    def _get_queue_override(self, queue=None, config=None):
        """Return the per-queue override dict for a given queue.

        Per-queue settings live under the optional top-level ``queue_settings``
        key of a scheduler config, mapping a queue/partition name to a dict of
        settings that override the global defaults. Returns an empty dict when
        no queue is given, ``queue_settings`` is missing/malformed, or the queue
        has no entry. This preserves full backward compatibility with configs
        that do not define ``queue_settings``.

        Args:
            queue: Name of the queue/partition to look up (or None).
            config: Scheduler config dict to read from. Defaults to lsf_config.

        Returns:
            Dict of per-queue overrides (possibly empty).
        """
        if config is None:
            config = self.lsf_config
        if not isinstance(config, dict) or not queue:
            return {}
        queue_settings = config.get("queue_settings")
        if not isinstance(queue_settings, dict):
            return {}
        override = queue_settings.get(queue)
        return override if isinstance(override, dict) else {}

    def get_lsf_defaults(self, queue=None):
        """Get the default LSF settings, optionally overridden per-queue.

        Args:
            queue: Optional queue name. When provided and the queue defines
                   overrides in ``queue_settings``, those override the globals.
        """
        defaults = self.lsf_config["default_settings"].copy()
        
        # Convert memory_mb to memory_gb if needed for backward compatibility
        if "memory_mb" in defaults and "memory_gb" not in defaults:
            defaults["memory_gb"] = max(1, defaults.get("memory_mb", 16384) // 1024)
            
        # Ensure memory_gb is always present
        if "memory_gb" not in defaults:
            defaults["memory_gb"] = 16
        
        # Add top-level configuration settings
        if "memlimit_multiplier" in self.lsf_config:
            defaults["memlimit_multiplier"] = self.lsf_config["memlimit_multiplier"]

        # Apply per-queue default overrides (backward compatible: no-op if unset)
        override = self._get_queue_override(queue)
        for key in ("num_cores", "memory_gb", "os", "memlimit_multiplier"):
            if key in override:
                defaults[key] = override[key]

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
    
    def get_memory_options(self, queue=None):
        """Get the list of available memory options in GB.

        Args:
            queue: Optional queue name. When the queue defines
                   ``memory_options_gb`` in ``queue_settings``, that list is
                   used instead of the global one.
        """
        # Per-queue override takes precedence
        override = self._get_queue_override(queue)
        if "memory_options_gb" in override:
            return override["memory_options_gb"]
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
    
    def get_core_options(self, queue=None):
        """Get the list of available core options.

        Args:
            queue: Optional queue name. When the queue defines ``core_options``
                   in ``queue_settings``, that list is used instead of global.
        """
        override = self._get_queue_override(queue)
        if "core_options" in override:
            return override["core_options"]
        return self.lsf_config["core_options"]
    
    def get_os_options(self):
        """Get the list of available OS options"""
        return self.lsf_config.get("os_options", [])
    
    def get_os_config_by_name(self, os_name):
        """
        Get the OS configuration (select and container) by OS name
        
        Args:
            os_name: Name of the OS
            
        Returns:
            Dictionary with 'select' and optionally 'container' keys, or None if not found
        """
        os_options = self.get_os_options()
        for os_option in os_options:
            if os_option.get("name") == os_name:
                return os_option
        return None
    
    def get_bindpaths_by_name(self, bindpaths_name):
        """
        Get the bindpaths configuration by name
        
        Args:
            bindpaths_name: Name of the bindpaths set (e.g., 'standard', 'minimal')
            
        Returns:
            List of paths to bind, or None if not found
        """
        bindpaths_configs = self.lsf_config.get("bindpaths", [])
        for bindpaths_config in bindpaths_configs:
            if bindpaths_config.get("name") == bindpaths_name:
                return bindpaths_config.get("paths", [])
        return None
        
    def get_vnc_config(self):
        """Get the full VNC configuration"""
        return self.vnc_config
    
    def get_enabled_window_managers(self):
        """Get the list of enabled window managers (globally available by default)"""
        # Check if enabled_window_managers exists, otherwise return all available
        return self.vnc_config.get("enabled_window_managers", self.vnc_config.get("available_window_managers", []))
    
    def get_enabled_memory_options(self, queue=None):
        """Get the list of enabled memory options in GB (globally available by default).

        Resolution order for a given queue:
          1. queue's ``enabled_memory_options_gb`` (explicit enabled subset)
          2. queue's ``memory_options_gb`` (all queue options are enabled)
          3. global ``enabled_memory_options_gb``
          4. global ``memory_options_gb``
        """
        override = self._get_queue_override(queue)
        if "enabled_memory_options_gb" in override:
            return override["enabled_memory_options_gb"]
        if "memory_options_gb" in override:
            return override["memory_options_gb"]
        return self.lsf_config.get("enabled_memory_options_gb", self.lsf_config.get("memory_options_gb", []))
    
    def get_enabled_core_options(self, queue=None):
        """Get the list of enabled core options (globally available by default).

        Resolution mirrors :meth:`get_enabled_memory_options` but for cores.
        """
        override = self._get_queue_override(queue)
        if "enabled_core_options" in override:
            return override["enabled_core_options"]
        if "core_options" in override:
            return override["core_options"]
        return self.lsf_config.get("enabled_core_options", self.lsf_config.get("core_options", []))
    
    def get_enabled_os_options(self, queue=None):
        """Get the list of enabled OS options (globally available by default).

        A queue may restrict the enabled OS options via ``enabled_os_options``
        (a list of OS names). The full OS definitions themselves remain global.
        """
        override = self._get_queue_override(queue)
        if "enabled_os_options" in override:
            enabled_os_names = override["enabled_os_options"]
        else:
            enabled_os_names = self.lsf_config.get("enabled_os_options", [])
        
        # If no enabled list, return all available OS options
        if not enabled_os_names:
            return self.get_os_options()
        
        # Filter OS options to only include enabled ones
        all_os_options = self.get_os_options()
        return [os_opt for os_opt in all_os_options if os_opt.get("name") in enabled_os_names]

    def get_memlimit_multiplier(self, queue=None):
        """Get the memory-limit multiplier, optionally overridden per-queue.

        Args:
            queue: Optional queue name. When the queue defines
                   ``memlimit_multiplier`` in ``queue_settings`` that value is
                   used, otherwise the global value (default 1.0) is returned.
        """
        override = self._get_queue_override(queue)
        if "memlimit_multiplier" in override:
            return override["memlimit_multiplier"]
        return self.lsf_config.get("memlimit_multiplier", 1.0)
    
    def get_user_specific_options(self, username, user_override=None):
        """
        Get options available for a specific user, considering manager overrides
        
        Args:
            username: The username to get options for
            user_override: Optional override dict (if None, will be fetched from DB)
            
        Returns:
            Dictionary with user-specific options for cores, memory, window_managers, queues, os_options
        """
        # If override exists for user, use those options; otherwise use enabled options
        if user_override:
            return {
                'cores': user_override.get('cores') if user_override.get('cores') is not None else self.get_enabled_core_options(),
                'memory': user_override.get('memory') if user_override.get('memory') is not None else self.get_enabled_memory_options(),
                'window_managers': user_override.get('window_managers') if user_override.get('window_managers') is not None else self.get_enabled_window_managers(),
                'queues': user_override.get('queues') if user_override.get('queues') is not None else self.get_available_queues(),
                'os_options': self._filter_os_options_by_names(user_override.get('os_options')) if user_override.get('os_options') is not None else self.get_enabled_os_options()
            }
        else:
            # Return enabled options (global defaults)
            return {
                'cores': self.get_enabled_core_options(),
                'memory': self.get_enabled_memory_options(),
                'window_managers': self.get_enabled_window_managers(),
                'queues': self.get_available_queues(),
                'os_options': self.get_enabled_os_options()
            }
    
    def get_scheduler_type(self):
        """Get the configured scheduler type from server_config.json.
        
        Returns 'lsf' or 'slurm'. Defaults to 'lsf' if not specified.
        """
        from myvnc.utils.config_loader import load_server_config
        server_config = load_server_config()
        return server_config.get('scheduler', 'lsf').lower()

    def get_scheduler_config(self):
        """Get the configuration for the active scheduler.
        
        Returns the lsf_config or slurm_config based on the scheduler setting.
        """
        scheduler = self.get_scheduler_type()
        if scheduler == 'slurm':
            if self.slurm_config is None:
                raise RuntimeError("Scheduler is set to 'slurm' but slurm_config.json was not found")
            return self.slurm_config
        return self.lsf_config

    def get_scheduler_defaults(self, queue=None):
        """Get the default settings for the active scheduler.
        
        Returns a normalized dict with keys: queue/partition, num_cores/cpus_per_task,
        memory_gb, job_name, and scheduler-specific extras.

        Args:
            queue: Optional queue/partition name. When provided, per-queue
                   overrides from ``queue_settings`` are merged over the globals.
        """
        scheduler = self.get_scheduler_type()
        if scheduler == 'slurm':
            return self.get_slurm_defaults(queue=queue)
        return self.get_lsf_defaults(queue=queue)

    def get_slurm_defaults(self, queue=None):
        """Get the default SLURM settings, optionally overridden per-partition.

        Unlike :meth:`get_scheduler_defaults`, this always resolves against the
        SLURM config regardless of the active scheduler, so it is safe to call
        when building the per-partition settings map.
        """
        if self.slurm_config is None:
            raise RuntimeError("slurm_config.json was not found")
        defaults = self.slurm_config["default_settings"].copy()
        # Normalize keys for compatibility with existing code
        if "partition" in defaults and "queue" not in defaults:
            defaults["queue"] = defaults["partition"]
        if "cpus_per_task" in defaults and "num_cores" not in defaults:
            defaults["num_cores"] = defaults["cpus_per_task"]
        if "memory_gb" not in defaults:
            defaults["memory_gb"] = 16

        # Apply per-partition default overrides
        override = self._get_queue_override(queue, config=self.slurm_config)
        for key in ("cpus_per_task", "num_cores", "memory_gb", "os"):
            if key in override:
                defaults[key] = override[key]
        # Keep num_cores/cpus_per_task in sync when only one is overridden
        if "cpus_per_task" in override and "num_cores" not in override:
            defaults["num_cores"] = override["cpus_per_task"]
        if "num_cores" in override and "cpus_per_task" not in override:
            defaults["cpus_per_task"] = override["num_cores"]
        return defaults

    def get_available_partitions(self):
        """Get the list of available SLURM partitions"""
        if self.slurm_config:
            return self.slurm_config.get("available_partitions", [])
        return []

    def get_slurm_cpus_per_task_options(self, queue=None):
        """Get the list of available CPU options for SLURM (optionally per-partition)"""
        if not self.slurm_config:
            return []
        override = self._get_queue_override(queue, config=self.slurm_config)
        if "cpus_per_task_options" in override:
            return override["cpus_per_task_options"]
        return self.slurm_config.get("cpus_per_task_options", [])

    def get_slurm_enabled_cpus_per_task_options(self, queue=None):
        """Get the list of enabled CPU options for SLURM (optionally per-partition).

        SLURM configs historically expose only the available options; the
        enabled set falls back to the available set when unspecified.
        """
        if not self.slurm_config:
            return []
        override = self._get_queue_override(queue, config=self.slurm_config)
        if "enabled_cpus_per_task_options" in override:
            return override["enabled_cpus_per_task_options"]
        if "cpus_per_task_options" in override:
            return override["cpus_per_task_options"]
        return self.slurm_config.get(
            "enabled_cpus_per_task_options",
            self.slurm_config.get("cpus_per_task_options", []),
        )

    def get_slurm_memory_options(self, queue=None):
        """Get the list of available memory options for SLURM in GB (optionally per-partition)"""
        if not self.slurm_config:
            return []
        override = self._get_queue_override(queue, config=self.slurm_config)
        if "memory_options_gb" in override:
            return override["memory_options_gb"]
        return self.slurm_config.get("memory_options_gb", [])

    def get_slurm_enabled_memory_options(self, queue=None):
        """Get the list of enabled memory options for SLURM in GB (optionally per-partition)"""
        if not self.slurm_config:
            return []
        override = self._get_queue_override(queue, config=self.slurm_config)
        if "enabled_memory_options_gb" in override:
            return override["enabled_memory_options_gb"]
        if "memory_options_gb" in override:
            return override["memory_options_gb"]
        return self.slurm_config.get(
            "enabled_memory_options_gb",
            self.slurm_config.get("memory_options_gb", []),
        )

    def get_slurm_os_options(self, queue=None):
        """Get the list of available OS options for SLURM"""
        if self.slurm_config:
            return self.slurm_config.get("os_options", [])
        return []

    def get_slurm_enabled_os_options(self, queue=None):
        """Get the list of enabled OS options for SLURM (optionally per-partition).

        A partition may restrict enabled OS options via ``enabled_os_options``
        (a list of OS names). Full OS definitions remain global.
        """
        if not self.slurm_config:
            return []
        override = self._get_queue_override(queue, config=self.slurm_config)
        if "enabled_os_options" in override:
            enabled_os_names = override["enabled_os_options"]
        else:
            enabled_os_names = self.slurm_config.get("enabled_os_options", [])
        all_os_options = self.get_slurm_os_options()
        if not enabled_os_names:
            return all_os_options
        return [os_opt for os_opt in all_os_options if os_opt.get("name") in enabled_os_names]

    def get_slurm_os_config_by_name(self, os_name):
        """Get the SLURM OS configuration by OS name.
        
        Args:
            os_name: Name of the OS
            
        Returns:
            Dictionary with 'constraint' and optionally 'container' keys, or None
        """
        os_options = self.get_slurm_os_options()
        for os_option in os_options:
            if os_option.get("name") == os_name:
                return os_option
        return None

    @staticmethod
    def _intersect_override(queue_values, override_values):
        """Intersect a queue's enabled values with a manager override list.

        The manager override acts as a per-user restriction: the effective
        options are those enabled for the queue AND allowed by the override.
        If the intersection is empty (e.g. the override and queue settings are
        disjoint), the override list is returned so the user is never left with
        an empty selection.
        """
        if override_values is None:
            return queue_values
        intersection = [v for v in queue_values if v in override_values]
        return intersection if intersection else override_values

    def _intersect_os_override(self, enabled_os_options, override_os_names):
        """Intersect queue-enabled OS option dicts with override OS names."""
        if override_os_names is None:
            return enabled_os_options
        intersection = [os_opt for os_opt in enabled_os_options
                        if os_opt.get("name") in override_os_names]
        if intersection:
            return intersection
        # Fall back to the override selection expressed as full OS dicts
        return self._filter_os_options_by_names(override_os_names)

    def build_queue_settings_map(self, scheduler=None, user_override=None):
        """Build a per-queue settings map for the active scheduler.

        The returned map is keyed by queue/partition name; each entry contains
        the resolved available/enabled cores, memory, and OS options plus the
        per-queue defaults. This lets the frontend switch option sets when the
        user changes queue without re-querying the server. Manager overrides
        (when supplied) are intersected with each queue's enabled options.

        Args:
            scheduler: 'lsf' or 'slurm'. Defaults to the active scheduler.
            user_override: Optional manager-override dict for the current user.

        Returns:
            Dict mapping queue name -> resolved settings dict.
        """
        if scheduler is None:
            scheduler = self.get_scheduler_type()

        result = {}
        is_slurm = scheduler == 'slurm'

        if is_slurm:
            if not self.slurm_config:
                return result
            queues = self.get_available_partitions()
            all_os_options = self.get_slurm_os_options()
        else:
            queues = self.get_available_queues()
            all_os_options = self.get_os_options()

        for queue in queues:
            if is_slurm:
                core_options = self.get_slurm_cpus_per_task_options(queue)
                enabled_cores = self.get_slurm_enabled_cpus_per_task_options(queue)
                memory_options = self.get_slurm_memory_options(queue)
                enabled_memory = self.get_slurm_enabled_memory_options(queue)
                enabled_os = self.get_slurm_enabled_os_options(queue)
                defaults = self.get_slurm_defaults(queue=queue)
            else:
                core_options = self.get_core_options(queue)
                enabled_cores = self.get_enabled_core_options(queue)
                memory_options = self.get_memory_options(queue)
                enabled_memory = self.get_enabled_memory_options(queue)
                enabled_os = self.get_enabled_os_options(queue)
                defaults = self.get_lsf_defaults(queue=queue)

            # Apply manager-override restrictions per dimension
            if user_override:
                enabled_cores = self._intersect_override(enabled_cores, user_override.get('cores'))
                enabled_memory = self._intersect_override(enabled_memory, user_override.get('memory'))
                enabled_os = self._intersect_os_override(enabled_os, user_override.get('os_options'))

            result[queue] = {
                'core_options': core_options,
                'enabled_cores': enabled_cores,
                'memory_options': memory_options,
                'memory_options_gb': memory_options,
                'enabled_memory': enabled_memory,
                'os_options': all_os_options,
                'enabled_os_options': enabled_os,
                'defaults': {
                    'num_cores': defaults.get('num_cores'),
                    'memory_gb': defaults.get('memory_gb'),
                    'os': defaults.get('os'),
                    'memlimit_multiplier': defaults.get('memlimit_multiplier', 1.0),
                },
            }

        return result

    def _filter_os_options_by_names(self, os_names):
        """
        Filter OS options to only include those with specified names
        
        Args:
            os_names: List of OS option names to include
            
        Returns:
            List of OS option dictionaries
        """
        if not os_names:
            return []
        
        all_os_options = self.get_os_options()
        return [os_opt for os_opt in all_os_options if os_opt.get("name") in os_names] 
