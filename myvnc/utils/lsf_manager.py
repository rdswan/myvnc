# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""
LSF Manager for submitting and monitoring LSF jobs
"""

import subprocess
import shlex
import re
import sys
import time
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path
import signal
import random

from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.log_manager import get_logger

class LSFManager:
    """Manages interactions with the LSF job scheduler via command line"""
    
    # Singleton instance
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Ensure only one instance of LSFManager is created"""
        if cls._instance is None:
            cls._instance = super(LSFManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        Initialize the LSF manager and check if LSF is available
        
        Raises:
            RuntimeError: If LSF is not available
        """
        # Only initialize once
        if LSFManager._initialized:
            return
            
        # For storing command execution history for debugging
        self.command_history = []
        
        # Initialize config manager for site domain lookups
        self.config_manager = ConfigManager()
        
        # Initialize environment and logger
        self.environment = os.environ.copy()
        self.logger = get_logger()
        
        try:
            self._check_lsf_available()
        except Exception as e:
            print(f"Warning: LSF initialization error: {str(e)}", file=sys.stderr)
            # Don't raise here, let individual methods handle errors
            
        # Mark as initialized
        LSFManager._initialized = True
    
    def get_command_history(self, limit=10):
        """Return the last N commands executed with their outputs"""
        return self.command_history[-limit:] if limit else self.command_history
    
    def run_test_commands(self):
        """Run a series of test LSF commands to populate the command history"""
        test_commands = [
            ['bjobs', '-h'],
            ['bsub', '-h'],
            ['bkill', '-h'],
            ['ls', '-la']
        ]
        
        results = []
        for cmd in test_commands:
            try:
                output = self._run_command(cmd, authenticated_user=None)
                results.append({
                    'command': ' '.join(cmd),
                    'output': output,
                    'success': True
                })
            except Exception as e:
                # Create an entry for failed commands
                error_msg = str(e)
                # Add directly to command history for failed commands since _run_command won't do it
                self.command_history.append({
                    'command': ' '.join(cmd),
                    'stdout': '',
                    'stderr': error_msg,
                    'success': False
                })
                results.append({
                    'command': ' '.join(cmd),
                    'output': error_msg,
                    'success': False
                })
        
        # If there are no commands in history yet, add some placeholder entries
        if not self.command_history:
            self.command_history.append({
                'command': 'echo "Testing command history"',
                'stdout': 'Testing command history',
                'stderr': '',
                'success': True
            })
            
            self.command_history.append({
                'command': 'whoami',
                'stdout': os.environ.get('USER', 'unknown'),
                'stderr': '',
                'success': True
            })
        
        return results
    
    def test_vnc_submission(self):
        """Run a test VNC job submission command (dry run)"""
        try:
            # Create test VNC config
            vnc_config = {
                'name': f'test_vnc_{int(time.time())}',
                'resolution': '1280x720',
                'color_depth': 24,
                'site': 'Austin',
                'vncserver_path': '/usr/bin/vncserver'
            }
            
            # Create test LSF config
            lsf_config = {
                'queue': 'interactive',
                'num_cores': 1,
                'memory_gb': 2,
                'time_limit': '00:30'
            }
            
            # Format the R resource requirement string
            resource_req = f"span[hosts=1] rusage[mem={lsf_config['memory_gb']}G]"
            
            # Build the command but don't execute it (dry run)
            cmd = [
                'bsub',
                '-q', lsf_config['queue'],
                '-n', str(lsf_config['num_cores']),
                '-R', resource_req,
                '-W', lsf_config['time_limit'],
                '-J', vnc_config['name']
            ]
            
            # Add site-specific parameters
            site_domain = self.config_manager.get_site_domain(vnc_config['site'])
            if site_domain:
                cmd.extend(['-m', f'{site_domain}-*'])
                
            # Add the VNC command
            vnc_cmd = f"{vnc_config['vncserver_path']} -geometry {vnc_config['resolution']} -depth {vnc_config['color_depth']} -name {vnc_config['name']}"
            cmd.append(vnc_cmd)
            
            # Try to run 'bsub -h' to test if bsub works
            try:
                bsub_help = self._run_command(['bsub', '-h'], authenticated_user=None)
                self.command_history.append({
                    'command': '[TEST VNC SUBMISSION] Would run command: ' + ' '.join(cmd),
                    'stdout': f'Test bsub help output:\n{bsub_help}',
                    'stderr': '',
                    'success': True
                })
            except Exception as e:
                self.command_history.append({
                    'command': '[TEST VNC SUBMISSION] Would run command: ' + ' '.join(cmd),
                    'stdout': '',
                    'stderr': f'Error testing bsub: {str(e)}',
                    'success': False
                })
                
        except Exception as e:
            self.command_history.append({
                'command': '[TEST VNC SUBMISSION]',
                'stdout': '',
                'stderr': f'Error preparing test submission: {str(e)}',
                'success': False
            })
    
    def _check_lsf_available(self):
        """
        Check if LSF is available on the system and determine full paths for LSF commands
        
        Raises:
            RuntimeError: If LSF is not available
        """
        self.logger.info("Checking LSF command availability")
        
        # Initialize command paths dictionary
        self.lsf_cmd_paths = {}
        
        # List of LSF commands to check
        lsf_commands = ['bjobs', 'bsub', 'bkill']
        
        # Check each LSF command
        for cmd in lsf_commands:
            try:
                # Compatible with Python 3.6 - removed text=True
                self.logger.debug(f"Running 'which {cmd}' to find command path")
                result = subprocess.run(['which', cmd], check=True, 
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                cmd_path = result.stdout.decode('utf-8').strip()
                self.logger.info(f"Found {cmd} at: {cmd_path}")
                
                # Store the path in the dictionary
                self.lsf_cmd_paths[cmd] = cmd_path
                
                # For bjobs, also store in the class attribute for backward compatibility
                if cmd == 'bjobs':
                    self.bjobs_path = cmd_path
            except subprocess.CalledProcessError as e:
                stderr = e.stderr.decode('utf-8')
                self.logger.error(f"{cmd} not available: {stderr}")
                
                # If bjobs is not available, LSF is not available
                if cmd == 'bjobs':
                    raise RuntimeError(f"LSF is not available on this system: {stderr}")
                    
        # Verify that all commands were found
        if not all(cmd in self.lsf_cmd_paths for cmd in lsf_commands):
            missing = [cmd for cmd in lsf_commands if cmd not in self.lsf_cmd_paths]
            self.logger.warning(f"Some LSF commands not found: {', '.join(missing)}")
        else:
            self.logger.info(f"All LSF commands found successfully: {', '.join(lsf_commands)}")
    
    def _run_command(self, cmd: List[str], authenticated_user: str = None) -> str:
        """
        Run a command and return its output
        
        Args:
            cmd: Command to run as a list of arguments
            authenticated_user: Optional authenticated username to run command as
            
        Returns:
            Command output as a string
            
        Raises:
            RuntimeError: If the command fails
        """
        # Create a modified command list
        modified_cmd = cmd.copy()
        
        # Check if the command is an LSF command and replace it with the full path
        lsf_command = cmd[0] if cmd else ""
        if lsf_command in self.lsf_cmd_paths:
            # Replace the command with its full path
            modified_cmd[0] = self.lsf_cmd_paths[lsf_command]
            
            # Prepend sudo command to run as the authenticated user, but only if we have one
            if authenticated_user:
                modified_cmd = ['sudo', '-u', authenticated_user, '-E'] + modified_cmd
        
        # For logging and debugging
        cmd_str = ' '.join(str(arg) for arg in cmd)
        modified_cmd_str = ' '.join(str(arg) for arg in modified_cmd)
        
        # Add DEBUG log for the system call
        self.logger.debug(f"DEBUG: Original command: {cmd_str}")
        self.logger.debug(f"DEBUG: Modified command: {modified_cmd_str}")
        if authenticated_user:
            self.logger.debug(f"DEBUG: Running as authenticated user: {authenticated_user}")
        
        # Log the command being executed - using original command for INFO logs
        self.logger.info(f"Executing command: {cmd_str}")
        
        try:
            # Compatible with Python 3.6 - removed text=True
            result = subprocess.run(modified_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout = result.stdout.decode('utf-8')
            stderr = result.stderr.decode('utf-8')
            
            # Log the command output
            if stdout:
                self.logger.info(f"Command output: {stdout}")
            if stderr:
                self.logger.info(f"Command stderr: {stderr}")
            
            # Add to command history for debugging - use the original command for consistency
            self.command_history.append({
                'command': cmd_str,
                'stdout': stdout,
                'stderr': stderr,
                'success': True,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            return stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8')
            stdout = e.stdout.decode('utf-8') if e.stdout else ''
            
            # Log the error - using the original command format for logs
            self.logger.error(f"Command failed: {cmd_str}")
            self.logger.error(f"Command stdout: {stdout}")
            self.logger.error(f"Command stderr: {stderr}")
            
            # Add failed command to history for debugging
            self.command_history.append({
                'command': cmd_str,
                'stdout': stdout,
                'stderr': stderr,
                'success': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            raise RuntimeError(f"Command failed: {stderr}")
    
    def submit_vnc_job(self, vnc_config: Dict, lsf_config: Dict, authenticated_user: str = None) -> str:
        """Submit a VNC job using bsub
        
        Args:
            vnc_config: VNC configuration
            lsf_config: LSF configuration
            authenticated_user: Optional authenticated username to run command as
            
        Returns:
            Job ID if successful
            
        Raises:
            Exception if submission fails
        """
        try:
            # Get current user for fallback if no authenticated user
            user = authenticated_user if authenticated_user else os.environ.get('USER', '')
            
            # Get the full path to bsub
            bsub_path = self.lsf_cmd_paths.get('bsub', 'bsub')
            
            # Extract parameters from config
            job_name = 'myvnc_vncserver'  # Fixed name for all VNC jobs
            num_cores = int(lsf_config.get('num_cores', 2))
            memory_gb = float(lsf_config.get('memory_gb', 2.0))
            
            # Get display name and resolution from vnc_config
            display_name = vnc_config.get('name', 'MyVNC Session')
            resolution = vnc_config.get('resolution', '1024x768')
            color_depth = int(vnc_config.get('color_depth', 24))
            
            # Get LSF group (queue) to use
            queue = lsf_config.get('queue', 'interactive')
            
            # Format resource request string
            resource_req = f"rusage[mem={memory_gb}]"
            
            # Add OS selection if specified
            os_select = lsf_config.get('os_select', '')
            
            # Add processor architecture selection if specified
            arch_select = lsf_config.get('arch_select', '')
            if arch_select and arch_select != "any":
                self.logger.info(f"Adding architecture selection '{arch_select}' to resource requirements")
                if resource_req:
                    resource_req = f"select[{arch_select}] {resource_req}"
                else:
                    resource_req = f"select[{arch_select}]"
            else:
                self.logger.info(f"Not adding architecture selection - arch_select is '{arch_select}'")
                
            # Modify resource string based on OS selection
            if os_select and os_select != "any":
                self.logger.info(f"Adding OS selection '{os_select}' to resource requirements")
                resource_req = f"select[{os_select}] {resource_req}"
            else:
                self.logger.info(f"Not adding OS selection - os_select is '{os_select}'")
                
            self.logger.info(f"Final resource requirements string: '{resource_req}'")
            
            # Build LSF command with -n for cores and -R for resource requirements
            bsub_cmd = [
                'bsub',
                '-q', lsf_config.get('queue', 'interactive'),
                '-n', str(num_cores),
                '-R', resource_req,
                '-J', job_name
            ]
            
            # Add time limit if specified
            time_limit = lsf_config.get('time_limit', '')
            if time_limit and time_limit.strip():
                bsub_cmd.extend(['-W', time_limit])
            
            # Add host filter only if specified
            host_filter = lsf_config.get('host_filter', '')
            if host_filter and host_filter.strip():
                bsub_cmd.extend(['-m', host_filter])
            
            # Add the VNC server command
            vncserver_path = vnc_config.get('vncserver_path', '/usr/bin/vncserver')
            
            # Randomly pick a display number between 500 and 999
            display_num = random.randint(500, 999)
            self.logger.info(f"Assigning random display number: {display_num}")
            
            vncserver_cmd = [
                vncserver_path,
                f":{display_num}",
                '-geometry', resolution,
                '-depth', str(color_depth),
            ]
            
            # Add display name parameter to vncserver command only if specified
            # Only add -name if display_name has content
            if display_name and display_name.strip():
                vncserver_cmd.extend(['-name', display_name])
            
            # Add xstartup parameter if configured
            # Check if custom xstartup is enabled and path is provided
            use_custom_xstartup = vnc_config.get('use_custom_xstartup', False)
            xstartup_path = vnc_config.get('xstartup_path', '')
            
            if use_custom_xstartup and xstartup_path and xstartup_path.strip():
                self.logger.info(f"Using custom xstartup script: {xstartup_path}")
                vncserver_cmd.extend(['-xstartup', xstartup_path])
                
                # Set window manager as an environment variable for the xstartup script
                window_manager = vnc_config.get('window_manager', 'gnome')
                # Get the current environment
                env = os.environ.copy()
                # Add the WINDOW_MANAGER environment variable
                env['WINDOW_MANAGER'] = window_manager
                # Make sure environment is propagated through bsub
                bsub_cmd.extend(['-env', f'WINDOW_MANAGER={window_manager}'])
            
            # Add fallbacktofreeport switch to ensure the server falls back to a free port if the specified one is in use
            vncserver_cmd.append('-fallbacktofreeport')
                
            # Add vncserver command to bsub command
            bsub_cmd.extend(vncserver_cmd)
            
            # Convert command list to string for logging
            cmd_str = ' '.join(str(arg) for arg in bsub_cmd)
            
            # Add to command history before execution
            cmd_entry = {
                'command': cmd_str,
                'stdout': '',
                'stderr': '',
                'success': False,  # Will update after execution
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.command_history.append(cmd_entry)
            
            # Execute the command
            try:
                # Use _run_command to ensure consistent logging
                self.logger.info(f"Submitting VNC job with bsub")
                # Use _run_command instead of subprocess.run directly
                stdout = self._run_command(bsub_cmd, authenticated_user)
                
                # Extract job ID from output
                job_id_match = re.search(r'Job <(\d+)>', stdout)
                job_id = job_id_match.group(1) if job_id_match else 'unknown'
                
                self.logger.info(f"Job submitted successfully, ID: {job_id}")
                
                return job_id
                
            except Exception as e:
                error_msg = f"Command failed: {str(e)}"
                self.logger.error(f"Job submission failed: {error_msg}")
                
                # Update command history with failure
                cmd_entry['stderr'] += f"\nException: {str(e)}"
                
                raise Exception(error_msg)
                
        except Exception as e:
            # Make sure any errors are added to command history
            if 'cmd_entry' in locals():
                cmd_entry['stderr'] += f"\nException: {str(e)}"
            else:
                self.command_history.append({
                    'command': 'Error preparing VNC job submission',
                    'stdout': '',
                    'stderr': str(e),
                    'success': False,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            raise
    
    def kill_vnc_job(self, job_id: str, authenticated_user: str = None) -> bool:
        """
        Kill a VNC job
        
        Args:
            job_id: Job ID to kill
            authenticated_user: Optional authenticated username to run command as
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Killing VNC job: {job_id}")
        
        try:
            result = self._run_command(['bkill', job_id], authenticated_user)
            self.logger.info(f"Kill result: Job {job_id} killed successfully: {result}")
            return True
        except RuntimeError as e:
            self.logger.error(f"Kill failed: Failed to kill job {job_id}: {str(e)}")
            return False
    
    def get_active_vnc_jobs(self, authenticated_user: str = None) -> List[Dict]:
        """
        Get active VNC jobs for the current user with job name matching the config
        
        Args:
            authenticated_user: Optional authenticated username to run command as
            
        Returns:
            List of jobs as dictionaries
        """
        jobs = []
        
        try:
            # Get current user for fallback if no authenticated user
            user = authenticated_user if authenticated_user else os.environ.get('USER', '')
            
            # Get the full path to bjobs
            bjobs_path = self.lsf_cmd_paths.get('bjobs', 'bjobs')
            
            # Create the base command as a list of arguments - this will be properly quoted
            cmd = [
                'bjobs',
                '-o', "jobid stat user queue first_host run_time slots max_req_proc combined_resreq command delimiter=';'",
                '-noheader',
                '-u', user,
                '-J', 'myvnc_vncserver'
            ]
            
            # For logging purposes, store the original command string
            base_cmd = ' '.join(cmd)
            
            # Add to command history with original command for consistency
            cmd_entry = {
                'command': base_cmd,
                'stdout': '',
                'stderr': '',
                'success': False,  # Will update after execution
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.command_history.append(cmd_entry)
            
            # Log the command for debugging
            self.logger.info(f"Executing command: {base_cmd}")
            
            try:
                # Use _run_command which will handle sudo and full paths
                output_str = self._run_command(cmd, authenticated_user)
                cmd_entry['stdout'] = output_str
                cmd_entry['success'] = True
                
                # Log success
                if output_str:
                    for line in output_str.splitlines():
                        self.logger.info(f"  {line}")
                        
            except RuntimeError as e:
                # Handle command failure
                error_str = str(e)
                cmd_entry['stderr'] = error_str
                
                # Check for delimiter error and fall back if needed
                if "delimiter" in error_str and "Illegal job ID" in error_str:
                    # Older LSF versions don't support the delimiter parameter
                    # Fall back to standard bjobs command
                    self.logger.warning(f"LSF version doesn't support delimiter: {error_str}")
                    return self._get_active_vnc_jobs_standard(authenticated_user)
                else:
                    # For other errors, just fail
                    self.logger.error(f"Error executing command: {error_str}")
                    return []
                
            # Parse the output
            output_lines = output_str.strip().split('\n')
            for line in output_lines:
                try:
                    # Skip empty lines
                    if not line.strip():
                        continue
                    
                    # Split by delimiter
                    parts = line.split(';')
                    
                    # Older LSF versions might not honor the delimiter
                    # Validate the output has at least a few fields
                    if len(parts) < 5:
                        self.logger.warning(f"Output format seems incorrect, falling back to standard format")
                        return self._get_active_vnc_jobs_standard(authenticated_user)
                    
                    # Extract fields
                    job_id = parts[0]
                    status = parts[1]
                    job_user = parts[2] 
                    queue = parts[3]
                    first_host = parts[4]
                    run_time = parts[5] if len(parts) > 5 else "0:0"
                    slots = parts[6] if len(parts) > 6 else None
                    max_req_proc = parts[7] if len(parts) > 7 else None
                    combined_resreq = parts[8] if len(parts) > 8 else ""
                    command = parts[9] if len(parts) > 9 else ""
                    
                    self.logger.debug(f"Job {job_id}: status={status}, user={job_user}, host={first_host}")
                    
                    # Format run time
                    run_time_parts = run_time.split(':')
                    run_time_seconds = 0
                    try:
                        hours = int(run_time_parts[0])
                        minutes = int(run_time_parts[1])
                        run_time_seconds = hours * 3600 + minutes * 60
                        
                        # Format for display
                        if hours > 24:
                            days = hours // 24
                            hours = hours % 24
                            runtime_display = f"{days}d {hours}h {minutes}m"
                        else:
                            runtime_display = f"{hours}h {minutes}m"
                    except:
                        runtime_display = run_time
                    
                    # Extract resource information from the combined_resreq
                    # Initialize defaults
                    num_cores = 1
                    memory_gb = 2
                    resources_unknown = False
                    
                    # For pending jobs, we won't have precise resource info
                    if status == "PEND":
                        resources_unknown = True
                        num_cores = None
                        memory_gb = None
                    else:
                        # First try to extract from slots or max_req_proc field
                        if slots and slots not in ('-', ''):
                            try:
                                num_cores = int(slots)
                            except:
                                self.logger.warning(f"Could not convert slots '{slots}' to integer")
                        elif max_req_proc and max_req_proc not in ('-', ''):
                            try:
                                num_cores = int(max_req_proc)
                            except:
                                self.logger.warning(f"Could not convert max_req_proc '{max_req_proc}' to integer")
                                
                        # Extract memory requirements if available
                        if combined_resreq:
                            # Use a regex to find memory spec
                            mem_match = re.search(r'rusage\[mem=(\d+(?:\.\d+)?)(\w*)\]', combined_resreq)
                            if mem_match:
                                try:
                                    mem_value = float(mem_match.group(1))
                                    mem_unit = mem_match.group(2).upper()
                                    
                                    # Convert to GB based on unit
                                    if mem_unit == 'K' or mem_unit == 'KB':
                                        memory_gb = mem_value / (1024 * 1024)
                                    elif mem_unit == 'M' or mem_unit == 'MB':
                                        memory_gb = mem_value / 1024
                                    elif mem_unit == 'T' or mem_unit == 'TB':
                                        memory_gb = mem_value * 1024
                                    else:  # Default unit is GB
                                        memory_gb = mem_value
                                except:
                                    self.logger.warning(f"Error converting memory value: {mem_match.group(0)}")
                    
                    # Get VNC connection details
                    display = None
                    port = None
                    exec_host = first_host
                    host = first_host
                    
                    # Clean up hostname for display
                    if host:
                        if '*' in host:
                            host = host.split('*')[0]
                        if ':' in host:  # Handle multiple hosts (like rv-c-35:rv-c-57)
                            host = host.split(':')[0]
                        if '.' in host:  # Remove domain name
                            host = host.split('.')[0]
                            
                    self.logger.debug(f"Cleaned host name: '{host}'")
                    
                    # Default display name
                    display_name = "VNC Session"
                    
                    # Extract display name from command
                    name_match = re.search(r'-name\s+([^\s"]+|"([^"]+)")', command)
                    if name_match:
                        if name_match.group(2):  # If captured in quotes
                            display_name = name_match.group(2)
                        else:
                            display_name = name_match.group(1)
                        self.logger.debug(f"Found display name: {display_name}")
                    
                    # Try to extract the display number from the command
                    display_match = re.search(r':(\d+)', command)
                    if display_match:
                        display_num = int(display_match.group(1))
                        self.logger.info(f"Found display number from command: {display_num}")
                        
                        # VNC uses port 5900+display number
                        vnc_port = 5900 + display_num
                        display = display_num
                        port = vnc_port
                    
                    # Only SSH to the remote host to determine the display if we couldn't get it from the command
                    if (host and host != "N/A" and status == "RUN" and display is None):
                        try:
                            self.logger.info(f"Attempting to query VNC information on host: {host} for user: {user}")
                            # Use SSH to run a command on the remote host to find the Xvnc process
                            ssh_cmd = ['ssh', 
                                      '-o', 'StrictHostKeyChecking=no', 
                                      '-o', 'UserKnownHostsFile=/dev/null',
                                      host, 
                                      f"ps -u {user} -o pid,command | grep Xvnc"]
                            self.logger.debug(f"Running SSH command: {' '.join(ssh_cmd)}")
                            
                            # Run ssh command with sudo if authenticated user is provided
                            vnc_process_output = self._run_command(ssh_cmd, authenticated_user)
                            self.logger.debug(f"SSH command output: {vnc_process_output}")
                            
                            # Look for the display number in the Xvnc process command line
                            # Format will be something like: Xvnc :1 
                            display_match = re.search(r'Xvnc\s+:(\d+)', vnc_process_output)
                            
                            if display_match:
                                display_num = int(display_match.group(1))
                                self.logger.info(f"Found display number from Xvnc pattern: {display_num}")
                                
                                # VNC uses port 5900+display number
                                vnc_port = 5900 + display_num
                                display = display_num
                                port = vnc_port
                            else:
                                # Fallback to scanning through all command line arguments
                                args_match = re.search(r'Xvnc.*?:(\d+)', vnc_process_output)
                                if args_match:
                                    display_num = int(args_match.group(1))
                                    self.logger.info(f"Found display number from args pattern: {display_num}")
                                    
                                    # VNC uses port 5900+display number
                                    vnc_port = 5900 + display_num
                                    display = display_num
                                    port = vnc_port
                        except Exception as e:
                            self.logger.error(f"Error querying remote host for VNC process: {str(e)}")
                    
                    # Create job entry with all required fields
                    job = {
                        'job_id': job_id,
                        'name': display_name,
                        'status': status,
                        'queue': queue,
                        'from_host': first_host,
                        'exec_host': exec_host,
                        'host': host,  # Use the cleaned host name for display
                        'user': job_user,
                        'runtime': runtime_display,  # Explicitly include runtime
                        'runtime_display': runtime_display,  # Add runtime_display for consistency with client
                        'run_time_seconds': run_time_seconds if 'run_time_seconds' in locals() else 0,
                        'resource_req': combined_resreq  # Add the raw resource requirements string
                    }
                    
                    # Add resource information based on what we found
                    if resources_unknown:
                        job['num_cores'] = None
                        job['cores'] = None
                        job['mem_gb'] = None
                        job['memory_gb'] = None
                        job['resources_unknown'] = True
                    else:
                        job['num_cores'] = num_cores
                        job['cores'] = num_cores      # Keep for backward compatibility
                        job['mem_gb'] = memory_gb
                        job['memory_gb'] = memory_gb  # Add for consistency with frontend
                    
                    # Log the final core count and memory values
                    self.logger.debug(f"Job {job_id} final values - cores: {num_cores}, memory_gb: {memory_gb}")
                    
                    # Add connection details if available
                    if display is not None:
                        job['display'] = display
                    if port is not None:
                        job['port'] = port
                    
                    jobs.append(job)
                    self.logger.debug(f"Added job to list: {job}")
                    
                except Exception as e:
                    self.logger.error(f"Error processing job: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error retrieving VNC jobs: {str(e)}")
        
        return jobs
    
    def _get_active_vnc_jobs_standard(self, authenticated_user: str = None) -> List[Dict]:
        """
        Fallback method using standard bjobs command (no delimiter)
        
        Args:
            authenticated_user: Optional authenticated username to run command as
            
        Returns:
            List of jobs as dictionaries
        """
        jobs = []
        
        try:
            # Get user to query (authenticated user or current user)
            user = authenticated_user if authenticated_user else os.environ.get('USER', '')
            
            # Use simple bjobs command to get job list - _run_command will handle using sudo and the full path
            # Use -o format instead of -w to get resource requirements in one call
            cmd = ['bjobs', '-u', user, '-J', 'myvnc_vncserver', '-o', "jobid stat user queue from_host exec_host job_name submit_time slots max_req_proc combined_resreq"]
            self.logger.info(f"Executing command: {' '.join(cmd)}")
            
            output = self._run_command(cmd, authenticated_user)
            
            lines = output.strip().split('\n')
            self.logger.debug(f"bjobs command output: {len(lines)} lines")
            
            if len(lines) <= 1:  # Only header or no output
                self.logger.info("No jobs found in output. Lines: {}".format(len(lines)))
                return jobs
            
            # Process job lines (skip header)
            for i in range(1, len(lines)):
                line = lines[i]
                
                try:
                    # Split into fields
                    fields = line.split()
                    
                    if len(fields) < 7:
                        self.logger.warning(f"Incomplete fields in line, expected at least 7, got {len(fields)}")
                        continue
                    
                    # Get job ID and basic info
                    job_id = fields[0].strip()
                    
                    # Extract submit time
                    submit_time = "N/A"  # Default value
                    submit_time_raw = "N/A"
                    
                    # In standard bjobs -o output, submit time might be in column 7
                    if len(fields) > 7:
                        # Handle the submit time field
                        submit_time_raw = ' '.join(fields[7:9])  # Get date and time parts
                        
                        try:
                            # Try to convert to standard datetime format for consistency
                            dt_parts = submit_time_raw.split()
                            if len(dt_parts) >= 2:
                                # Format might be "Apr 25 12:34"
                                month_name = dt_parts[0]
                                day = dt_parts[1]
                                time_part = dt_parts[2] if len(dt_parts) > 2 else "00:00:00"
                                
                                # Convert month name to month number
                                month_dict = {
                                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                                }
                                month = month_dict.get(month_name, '01')
                                
                                # Current year - LSF might not include it
                                year = datetime.now().year
                                
                                # Construct a standard date time string
                                submit_time = f"{year}-{month}-{day.zfill(2)} {time_part}"
                        except Exception as e:
                            # Keep the default value and print the error
                            self.logger.error(f"Error parsing submit time '{submit_time_raw}': {str(e)}")
                    
                    # Default values for resources
                    num_cores = 2  # Default
                    memory_gb = 16  # Default in GB
                    combined_resreq = ""
                    resources_unknown = False
                    slots = None
                    max_req_proc = None
                    
                    # Extract slots if present (should be in column 9 after submit time)
                    if len(fields) > 9:
                        slots = fields[9].strip()
                    
                    # Extract max_req_proc if present (should be in column 10 after slots)
                    if len(fields) > 10:
                        max_req_proc = fields[10].strip()
                    
                    # Log exact values for debugging
                    self.logger.debug(f"Job {fields[0].strip()} raw field values - slots: '{slots}', max_req_proc: '{max_req_proc}'")
                    
                    # Determine number of cores - first try max_req_proc, then slots
                    # Default value first
                    num_cores = 2  # Default
                    
                    # Try max_req_proc if it's a valid value (not empty or dash)
                    if max_req_proc and max_req_proc != '-':
                        try:
                            num_cores = int(max_req_proc)
                            self.logger.debug(f"Using max_req_proc value for cores: {num_cores}")
                        except (ValueError, TypeError):
                            self.logger.warning(f"Could not parse max_req_proc value '{max_req_proc}' as integer")
                    # If max_req_proc not available or not valid, try slots
                    elif slots and slots != '-':
                        try:
                            num_cores = int(slots)
                            self.logger.debug(f"Using slots value for cores: {num_cores}")
                        except (ValueError, TypeError):
                            self.logger.warning(f"Could not parse slots value '{slots}' as integer")
                    
                    # Extract combined resource requirements if present
                    # In newer bjobs -o output, it would be after max_req_proc field
                    if len(fields) > 11:
                        combined_resreq = ' '.join(fields[11:])
                        
                        # Check if combined_resreq is just a dash, indicating unknown resources
                        if combined_resreq == "-":
                            self.logger.info(f"Job {job_id} has unknown resource requirements")
                            num_cores = None
                            memory_gb = None
                            resources_unknown = True
                            job = {
                                'job_id': fields[0].strip(),
                                'user': fields[2].strip(),
                                'status': fields[1].strip(),
                                'queue': fields[3].strip(),
                                'from_host': fields[4].strip(),
                                'exec_host': fields[5].strip(),
                                'host': fields[5].strip(),
                                'runtime': 'N/A',
                                'runtime_display': 'N/A',
                                'submit_time': submit_time,
                                'submit_time_raw': submit_time_raw,
                                'resource_req': combined_resreq,
                                'num_cores': None,
                                'cores': None,
                                'mem_gb': None,
                                'memory_gb': None,
                                'resources_unknown': True
                            }
                            jobs.append(job)
                            continue
                            
                        self.logger.debug(f"Found combined resreq: {combined_resreq}")
                        
                        # Extract cores from affinity[core(N)] pattern
                        core_match = re.search(r'affinity\[core\((\d+)\)(?:\*(\d+))?\]', combined_resreq)
                        if core_match:
                            cores_per_node = int(core_match.group(1))
                            nodes = int(core_match.group(2)) if core_match.group(2) else 1
                            num_cores = cores_per_node * nodes
                            self.logger.debug(f"Parsed cores from combined_resreq: {num_cores}")
                        
                        # Extract memory from rusage[mem=N] pattern
                        mem_match = re.search(r'rusage\[mem=(\d+(\.\d+)?)([KMG]?)\]', combined_resreq)
                        if mem_match:
                            mem_value = float(mem_match.group(1))
                            mem_unit = mem_match.group(3)
                            
                            self.logger.info(f"Found memory in connection details: mem={mem_value}{mem_unit}")
                            
                            # Special case for your LSF configuration: values without units are already in GB
                            memory_gb = mem_value
                            self.logger.info(f"Treating memory value {mem_value} as GB")
                        else:
                            self.logger.debug(f"No memory information found in combined_resreq: {combined_resreq}")
                    
                    # Create basic job info
                    job = {
                        'job_id': fields[0].strip(),
                        'user': fields[2].strip(),
                        'status': fields[1].strip(),
                        'queue': fields[3].strip(),
                        'from_host': fields[4].strip(),
                        'exec_host': fields[5].strip(),
                        'host': fields[5].strip(),
                        'runtime': 'N/A',  # Default runtime
                        'runtime_display': 'N/A',  # Add runtime_display for consistency with client
                        'submit_time': submit_time,
                        'submit_time_raw': submit_time_raw,
                        'resource_req': combined_resreq  # Add the raw resource requirements string
                    }
                    
                    # Add resource information based on what we found
                    if resources_unknown:
                        job['num_cores'] = None
                        job['cores'] = None
                        job['mem_gb'] = None
                        job['memory_gb'] = None
                        job['resources_unknown'] = True
                    else:
                        job['num_cores'] = num_cores
                        job['cores'] = num_cores      # Keep for backward compatibility
                        job['mem_gb'] = memory_gb
                        job['memory_gb'] = memory_gb  # Add for consistency with frontend
                    
                    # Log the final core count and memory values
                    self.logger.debug(f"Job {job_id} final values - cores: {num_cores}, memory_gb: {memory_gb}")
                    
                    # Add to jobs list
                    jobs.append(job)
                except Exception as e:
                    self.logger.error(f"Error processing job in fallback method: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error in fallback job retrieval: {str(e)}")
        
        return jobs
            
    def get_vnc_connection_details(self, job_id: str, authenticated_user: str = None) -> Optional[Dict]:
        """
        Get connection details for a VNC job
        
        Args:
            job_id: Job ID
            authenticated_user: Optional authenticated username to run command as
            
        Returns:
            Dictionary with connection details or None if not found
        """
        try:
            # Get all necessary information with a single comprehensive command
            self.logger.info(f"Getting connection details for job {job_id}")
            comprehensive_output = self._run_command([
                'bjobs', 
                '-o', "stat:6 user:8 exec_host:25 slots:5 max_req_proc:5 combined_resreq:50 command:100 job_name delimiter=';'", 
                '-noheader', 
                job_id
            ], authenticated_user)
            
            # Initialize values
            host = None
            user = None
            display_num = None
            status = "UNKNOWN"
            slots = None
            max_req_proc = None
            combined_resreq = ""
            command = ""
            job_name = ""
            
            # Try to parse the output with delimiter
            try:
                # Should return a single line with the job info
                basic_line = comprehensive_output.strip()
                self.logger.debug(f"Job info with delimiter: {basic_line}")
                
                if ';' in basic_line:
                    # Split by the delimiter
                    fields = basic_line.split(';')
                    if len(fields) >= 8:
                        status = fields[0].strip()
                        user = fields[1].strip()
                        exec_host = fields[2].strip()
                        slots = fields[3].strip()
                        max_req_proc = fields[4].strip()
                        combined_resreq = fields[5].strip()
                        command = fields[6].strip() if len(fields) > 6 else ""
                        job_name = fields[7].strip() if len(fields) > 7 else ""
                        
                        if exec_host and exec_host != '-':
                            if ":" in exec_host:
                                # For multi-host jobs, take the first host
                                host = exec_host.split(':')[0]
                            else:
                                host = exec_host
                            self.logger.debug(f"Found host from job info with delimiter: {host}")
                            
                        # Extract resource information from the combined_resreq
                        if combined_resreq:
                            self.logger.debug(f"Resource requirements: {combined_resreq}")
                            
                            # Try to get cores directly
                            num_cores = None
                            
                            # First try max_req_proc if it's a valid value (not a dash or empty)
                            if max_req_proc and max_req_proc != '-':
                                try:
                                    num_cores = int(max_req_proc)
                                    self.logger.debug(f"Using max_req_proc value for cores: {num_cores}")
                                except (ValueError, TypeError):
                                    self.logger.warning(f"Could not parse max_req_proc value '{max_req_proc}' as integer")
                            # If max_req_proc is not valid, try slots
                            elif slots and slots != '-':
                                try:
                                    num_cores = int(slots)
                                    self.logger.debug(f"Using slots value for cores: {num_cores}")
                                except (ValueError, TypeError):
                                    self.logger.warning(f"Could not parse slots value '{slots}' as integer")
                            
                            # Fall back to regex parsing only if we couldn't get a value from fields
                            if num_cores is None:
                                # Look for span[hosts=1] pattern which indicates using the new format
                                if 'span[hosts=1]' in combined_resreq:
                                    # For the new format, the cores are specified with -n parameter
                                    # but we can't directly see that in combined_resreq
                                    # Just leave at default
                                    self.logger.debug(f"Found span[hosts=1] pattern indicating new resource format")
                                else:
                                    # Try the old affinity[core(N)] pattern as fallback
                                    core_match = re.search(r'affinity\[core\((\d+)\)(?:\*(\d+))?\]', combined_resreq)
                                    if core_match:
                                        cores_per_node = int(core_match.group(1))
                                        nodes = int(core_match.group(2)) if core_match.group(2) else 1
                                        num_cores = cores_per_node * nodes
                                        self.logger.debug(f"Parsed cores from affinity pattern: {num_cores}")
                            
                            # Extract memory from rusage[mem=N] pattern
                            mem_match = re.search(r'rusage\[mem=(\d+(\.\d+)?)([KMG]?)\]', combined_resreq)
                            if mem_match:
                                mem_value = float(mem_match.group(1))
                                mem_unit = mem_match.group(3)
                                
                                self.logger.info(f"Found memory in connection details: mem={mem_value}{mem_unit}")
                                
                                # Special case for your LSF configuration: values without units are already in GB
                                memory_gb = mem_value
                                self.logger.info(f"Treating memory value {mem_value} as GB")
                            else:
                                self.logger.debug(f"No memory information found in combined_resreq: {combined_resreq}")
                        else:
                            self.logger.debug(f"No memory information found in combined_resreq: {combined_resreq}")
                    else:
                        self.logger.warning(f"Incomplete fields in job info, expected at least 8, got {len(fields)}")
                else:
                    self.logger.warning(f"No delimiter found in output: {basic_line}")
            except Exception as e:
                self.logger.error(f"Error parsing job info with delimiter: {str(e)}")
            
            # If we can't determine the host, we can't determine connection details
            if not host:
                self.logger.warning(f"Could not determine execution host for job {job_id}")
                return None
                
            # Clean up the hostname
            if host:
                # Remove domain if present
                if '.' in host:
                    host = host.split('.')[0]
                # Remove subdomain if present
                if '*' in host:
                    host = host.split('*')[0]
                # Handle multiple hosts by taking the first one
                if ':' in host:
                    host = host.split(':')[0]
            
            # Extract the display value from command output if possible
            if command:
                # Extract display number from vnc command string
                try:
                    # Look for :N in the command string (VNC display number)
                    display_match = re.search(r':(\d+)', command)
                    if display_match:
                        display_num = display_match.group(1)
                        self.logger.debug(f"Found display number from command: {display_num}")
                except Exception as e:
                    self.logger.warning(f"Error extracting display number from command: {str(e)}")
            
            # If display number is still not found, try to find it in output_info
            if not display_num and comprehensive_output:
                try:
                    # Look for VNC display pattern in output_info
                    display_match = re.search(r'New \'[^:]+:(\d+)', comprehensive_output)
                    if display_match:
                        display_num = display_match.group(1)
                        self.logger.debug(f"Found display number from output info: {display_num}")
                    else:
                        display_match = re.search(r'Starting applications specified in\s+.*\s+for VNC display\s+(\d+)', comprehensive_output)
                        if display_match:
                            display_num = display_match.group(1)
                            self.logger.debug(f"Found display number from VNC output info: {display_num}")
                except Exception as e:
                    self.logger.warning(f"Error extracting display number from output info: {str(e)}")
            
            # If display number is still not found and job is running, try SSH to the host
            if not display_num and status == "RUN" and host:
                try:
                    self.logger.info(f"Display number not found in command, attempting to query via SSH on host: {host} for user: {user}")
                    # Use SSH to run a command on the remote host to find the Xvnc process
                    ssh_cmd = ['ssh', 
                              '-o', 'StrictHostKeyChecking=no', 
                              '-o', 'UserKnownHostsFile=/dev/null',
                              host, 
                              f"ps -u {user} -o pid,command | grep Xvnc"]
                    self.logger.debug(f"Running SSH command: {' '.join(ssh_cmd)}")
                    
                    # Run ssh command with sudo if authenticated user is provided
                    vnc_process_output = self._run_command(ssh_cmd, authenticated_user)
                    self.logger.debug(f"SSH command output: {vnc_process_output}")
                    
                    # Look for the display number in the Xvnc process command line
                    # Format will be something like: Xvnc :1 
                    display_match = re.search(r'Xvnc\s+:(\d+)', vnc_process_output)
                    
                    if display_match:
                        display_num = display_match.group(1)
                        self.logger.info(f"Found display number from Xvnc pattern via SSH: {display_num}")
                    else:
                        # Fallback to scanning through all command line arguments
                        args_match = re.search(r'Xvnc.*?:(\d+)', vnc_process_output)
                        if args_match:
                            display_num = args_match.group(1)
                            self.logger.info(f"Found display number from args pattern via SSH: {display_num}")
                except Exception as e:
                    self.logger.error(f"Error querying remote host for VNC process: {str(e)}")
            
            # Last resort - use default display number
            if not display_num:
                self.logger.debug(f"No display number found, using default (1)")
                display_num = "1"  # Default value
            
            # Calculate VNC port from display number
            try:
                if display_num:
                    port = 5900 + int(display_num)
                    self.logger.debug(f"Calculated VNC port: {port}")
                else:
                    port = None
                    self.logger.warning("Could not calculate VNC port (no display number)")
            except Exception as e:
                self.logger.warning(f"Error calculating VNC port: {str(e)}")
                port = None
            
            # Return connection details
            return {
                'job_id': job_id,
                'host': host,
                'display': display_num,
                'port': port,
                'user': user,
                'status': status
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get VNC connection details: {str(e)}")
            return None 
