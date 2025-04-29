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

from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.log_manager import get_logger

class LSFManager:
    """Manages interactions with the LSF job scheduler via command line"""
    
    def __init__(self):
        """
        Initialize the LSF manager and check if LSF is available
        
        Raises:
            RuntimeError: If LSF is not available
        """
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
    
    def get_command_history(self, limit=10):
        """Return the last N commands executed with their outputs"""
        return self.command_history[-limit:] if limit else self.command_history
    
    def run_test_commands(self):
        """Run a series of test LSF commands to populate the command history"""
        test_commands = [
            ['which', 'bjobs'],
            ['bjobs', '-h'],
            ['which', 'bsub'],
            ['which', 'bkill'],
            ['ls', '-la']
        ]
        
        results = []
        for cmd in test_commands:
            try:
                output = self._run_command(cmd)
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
                'memory_gb': 2048,
                'time_limit': '00:30'
            }
            
            # Build the command but don't execute it (dry run)
            cmd = [
                'bsub',
                '-q', lsf_config['queue'],
                '-n', str(lsf_config['num_cores']),
                '-M', str(lsf_config['memory_gb']),
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
                bsub_help = self._run_command(['bsub', '-h'])
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
        Check if LSF is available on the system
        
        Raises:
            RuntimeError: If LSF is not available
        """
        try:
            # Compatible with Python 3.6 - removed text=True
            result = subprocess.run(['which', 'bjobs'], check=True, 
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout = result.stdout.decode('utf-8').strip()
            print(f"LSF available at: {stdout}", file=sys.stderr)
            self.bjobs_path = stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8')
            print(f"LSF not available: {stderr}", file=sys.stderr)
            raise RuntimeError(f"LSF is not available on this system: {stderr}")
    
    def _run_command(self, cmd: List[str]) -> str:
        """
        Run a command and return its output
        
        Args:
            cmd: Command to run as a list of arguments
            
        Returns:
            Command output as a string
            
        Raises:
            RuntimeError: If the command fails
        """
        cmd_str = ' '.join(cmd)
        # Log the command being executed to stdout and logger with the specified format
        self.logger.info(f"Executing command: {cmd_str}")
        
        try:
            # Compatible with Python 3.6 - removed text=True
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout = result.stdout.decode('utf-8')
            stderr = result.stderr.decode('utf-8')
            
            # Log the command output
            if stdout:
                self.logger.info(f"Command output: {stdout}")
            if stderr:
                self.logger.info(f"Command stderr: {stderr}")
            
            # Add to command history for debugging
            self.command_history.append({
                'command': cmd_str,
                'stdout': stdout,
                'stderr': stderr,
                'success': True
            })
            
            return stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8')
            stdout = e.stdout.decode('utf-8') if e.stdout else ''
            
            # Log the error
            self.logger.error(f"Command failed: {cmd_str}")
            self.logger.error(f"Command stdout: {stdout}")
            self.logger.error(f"Command stderr: {stderr}")
            
            # Add failed command to history for debugging
            self.command_history.append({
                'command': cmd_str,
                'stdout': stdout,
                'stderr': stderr,
                'success': False
            })
            
            raise RuntimeError(f"Command failed: {stderr}")
    
    def submit_vnc_job(self, vnc_config: Dict, lsf_config: Dict) -> str:
        """Submit a VNC job using bsub"""
        
        try:
            # Get the display name from vnc_config if provided
            display_name = vnc_config.get('name', '')
            resolution = vnc_config.get('resolution', '1920x1080')
            color_depth = vnc_config.get('color_depth', 24)
            
            # Use the job_name from LSF config (or default value if not set)
            job_name = lsf_config.get('job_name', 'myvnc_vncserver')
            
            # Use memory directly in GB (no conversion)
            memory_gb = lsf_config.get('memory_gb', 16)
            
            # Build LSF command with -R for memory instead of -M
            bsub_cmd = [
            'bsub',
                '-q', lsf_config.get('queue', 'interactive'),
                '-n', str(lsf_config.get('num_cores', 2)),
                '-R', f"rusage[mem={memory_gb}G]",
                '-J', job_name
            ]
            
            # Add host filter only if specified
            host_filter = lsf_config.get('host_filter', '')
            if host_filter and host_filter.strip():
                bsub_cmd.extend(['-m', host_filter])
            
            # Add the VNC server command
            vncserver_path = vnc_config.get('vncserver_path', '/usr/bin/vncserver')
            vncserver_cmd = [
                vncserver_path,
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
                
            # Add vncserver command to bsub command
            bsub_cmd.extend(vncserver_cmd)
            
            # Convert command list to string for logging
            cmd_str = ' '.join(str(arg) for arg in bsub_cmd)
            self.logger.info(f"SUBMIT COMMAND: {cmd_str}")
            
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
                stdout = self._run_command(bsub_cmd)
                
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
    
    def kill_vnc_job(self, job_id: str) -> bool:
        """
        Kill a VNC job
        
        Args:
            job_id: Job ID to kill
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Killing VNC job: {job_id}")
        
        try:
            result = self._run_command(['bkill', job_id])
            self.logger.info(f"Kill result: Job {job_id} killed successfully: {result}")
            return True
        except RuntimeError as e:
            self.logger.error(f"Kill failed: Failed to kill job {job_id}: {str(e)}")
            return False
    
    def get_active_vnc_jobs(self) -> List[Dict]:
        """
        Get active VNC jobs for the current user with job name matching the config
        
        Returns:
            List of jobs as dictionaries
        """
        jobs = []
        
        try:
            # Get current user
            user = os.environ.get('USER', '')
            
            # Use bjobs with the exact format specified by the user
            cmd = f'bjobs -o "jobid stat user queue first_host run_time command delimiter=\';\'" -noheader -u {user} -J myvnc_vncserver'
            self.logger.info(f"BJOBS COMMAND: {cmd}")
            
            # Add to command history
            cmd_entry = {
                'command': cmd,
                'stdout': '',
                'stderr': '',
                'success': False,  # Will update after execution
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.command_history.append(cmd_entry)
            
            # Run the command and capture output directly
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = proc.communicate()
            
            # Decode and log the output
            output_str = output.decode('utf-8').strip() if output else ""
            error_str = error.decode('utf-8').strip() if error else ""
            
            # Update command history
            cmd_entry['stdout'] = output_str
            cmd_entry['stderr'] = error_str
            cmd_entry['success'] = proc.returncode == 0
            
            # Log the results
            if output_str:
                self.logger.info(f"BJOBS OUTPUT: {len(output_str.splitlines())} line(s)")
                for line in output_str.splitlines():
                    self.logger.info(f"  {line}")
            
            if error_str:
                self.logger.warning(f"bjobs stderr output:")
                for line in error_str.splitlines():
                    self.logger.warning(f"  {line}")
                    
                if "delimiter" in error_str and "Illegal job ID" in error_str:
                    # Older LSF versions don't support the delimiter parameter
                    # Fall back to standard bjobs command
                    self.logger.warning(f"LSF version doesn't support delimiter: {error_str}")
                    return self._get_active_vnc_jobs_standard()
                else:
                    self.logger.error(f"Error in bjobs command: {error_str}")
                    return jobs
            
            lines = output_str.splitlines() if output_str else []
            self.logger.debug(f"bjobs command output: {len(lines)} line(s)")
            
            if not lines or (len(lines) == 1 and not lines[0].strip()):
                self.logger.info(f"No jobs found in output.")
                return jobs
            
            # Process each job line
            for line in lines:
                self.logger.debug(f"Processing job line: {line}")
                
                # Split the line by the delimiter
                fields = line.split(';')
                if len(fields) < 6:  # Need at least jobid, status, user, queue, first_host, run_time
                    self.logger.warning(f"Incomplete fields in line, expected at least 6, got {len(fields)}")
                    continue
                    
                # Extract job information from fields
                try:
                    job_id = fields[0].strip()
                    status = fields[1].strip()
                    user = fields[2].strip()
                    queue = fields[3].strip()
                    first_host = fields[4].strip()
                    run_time_raw = fields[5].strip()
                    command = ';'.join(fields[6:]).strip() if len(fields) > 6 else ""
                    
                    # Format runtime from the run_time_raw field
                    runtime_display = "N/A"
                    run_time_seconds = 0
                    try:
                        # Extract runtime value from various formats:
                        # "2580 second(s)" or "43 minute(s) 30 second(s)" or "2:30"
                        
                        # Try to match HH:MM or H:MM format first
                        time_match = re.search(r'(\d+):(\d+)', run_time_raw)
                        if time_match:
                            hours = int(time_match.group(1))
                            minutes = int(time_match.group(2))
                            run_time_seconds = hours * 3600 + minutes * 60
                            self.logger.debug(f"Parsed HH:MM format: {hours}h {minutes}m = {run_time_seconds}s")
                        else:
                            # Try to match "X minute(s) Y second(s)" format
                            minutes_match = re.search(r'(\d+)\s+minute\(s\)', run_time_raw)
                            seconds_match = re.search(r'(\d+)\s+second\(s\)', run_time_raw)
                            
                            minutes = int(minutes_match.group(1)) if minutes_match else 0
                            seconds = int(seconds_match.group(1)) if seconds_match else 0
                            
                            if minutes > 0 or seconds > 0:
                                run_time_seconds = minutes * 60 + seconds
                                self.logger.debug(f"Parsed minutes/seconds format: {minutes}m {seconds}s = {run_time_seconds}s")
                            else:
                                # Just look for any number as a last resort (assuming seconds)
                                seconds_match = re.search(r'(\d+)', run_time_raw)
                                if seconds_match:
                                    run_time_seconds = int(seconds_match.group(1))
                                    self.logger.debug(f"Parsed seconds format: {run_time_seconds}s")
                        
                        # Now format the runtime display string based on the calculated seconds
                        if run_time_seconds > 0:
                            days = run_time_seconds // 86400  # 86400 seconds in a day
                            hours = (run_time_seconds % 86400) // 3600  # 3600 seconds in an hour
                            minutes = (run_time_seconds % 3600) // 60  # 60 seconds in a minute
                            seconds = run_time_seconds % 60
                            
                            # Format runtime string
                            if days > 0:
                                runtime_display = f"{days}d {hours}h {minutes}m"
                            elif hours > 0:
                                runtime_display = f"{hours}h {minutes}m"
                            elif minutes > 0:
                                runtime_display = f"{minutes}m {seconds}s"
                            else:
                                runtime_display = f"{seconds}s"
                                
                            self.logger.debug(f"Parsed runtime: {runtime_display} from {run_time_seconds} seconds (raw: {run_time_raw})")
                        else:
                            if status == "PEND" or status == "PSUSP":
                                # For pending jobs, display 0m instead of N/A
                                runtime_display = "0m"
                            else:
                                self.logger.debug(f"No valid runtime found in '{run_time_raw}', using default")
                    except (ValueError, TypeError, IndexError) as e:
                        self.logger.warning(f"Error parsing runtime '{run_time_raw}': {e}")
                        # Default for pending jobs should be 0m
                        if status == "PEND" or status == "PSUSP":
                            runtime_display = "0m"
                    
                    # Get detailed job information
                    try:
                        # Get detailed job info for host, cores, memory
                        detailed_cmd = ['bjobs', '-l', job_id]
                        detailed_output = self._run_command(detailed_cmd)
                        
                        # Extract host information
                        host_match = re.search(r'Started on <([^>]+)>', detailed_output)
                        if host_match:
                            exec_host = host_match.group(1)
                            self.logger.debug(f"Found exec_host: {exec_host}")
                        else:
                            exec_host = first_host
                            self.logger.debug(f"Using first_host as exec_host: {exec_host}")
                        
                        # Clean up hostname for display
                        host = exec_host
                        if '*' in host:
                            host = host.split('*')[0]
                        if ':' in host:  # Handle multiple hosts (like rv-c-35:rv-c-57)
                            host = host.split(':')[0]
                        if '.' in host:  # Remove domain name
                            host = host.split('.')[0]
                            
                        self.logger.debug(f"Cleaned host name: '{host}'")
                        
                        # Default values
                        display_name = "VNC Session"
                        num_cores = 2  # Default
                        memory_gb = 16  # Default in GB
                        
                        # Extract display name from command
                        name_match = re.search(r'-name\s+([^\s"]+|"([^"]+)")', command)
                        if not name_match:
                            name_match = re.search(r'-name\s+([^\s"]+|"([^"]+)")', detailed_output)
                            
                        if name_match:
                            if name_match.group(2):  # If captured in quotes
                                display_name = name_match.group(2)
                            else:
                                display_name = name_match.group(1)
                            self.logger.debug(f"Found display name: {display_name}")
                            
                        # Extract cores and memory
                        tasks_match = re.search(r'(\d+)\s+Task\(s\)', detailed_output)
                        if tasks_match:
                            num_cores = int(tasks_match.group(1))
                            self.logger.debug(f"Found cores: {num_cores}")
                            
                        mem_match = re.search(r'rusage\[mem=(\d+(\.\d+)?)([KMG]?)\]', detailed_output)
                        if mem_match:
                            mem_value = float(mem_match.group(1))
                            mem_unit = mem_match.group(3)
                            
                            # Convert to GB
                            if not mem_unit:
                                self.logger.debug("No unit specified in rusage context, assuming GB")
                                mem_unit = 'G'
                            
                            if mem_unit == 'K':
                                memory_gb = mem_value / (1024 * 1024)
                            elif mem_unit == 'M':
                                memory_gb = mem_value / 1024
                            elif mem_unit == 'G':
                                memory_gb = mem_value
                            
                            memory_gb = round(memory_gb, 2)
                            self.logger.debug(f"Found memory: {memory_gb}GB")
                            
                    except Exception as e:
                        self.logger.error(f"Error getting detailed job info: {str(e)}")
                        host = first_host
                        exec_host = first_host
                    
                    # Get VNC connection details
                    display = None
                    port = None
                    
                    if host and host != "N/A":
                        try:
                            self.logger.info(f"Attempting to query VNC information on host: {host} for user: {user}")
                            # Use SSH to find the VNC display number on the remote host
                            ssh_cmd = f"ssh {host} ps -u {user} -o pid,command | grep Xvnc"
                            ssh_result = subprocess.run(ssh_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            ssh_output = ssh_result.stdout.decode('utf-8')
                            self.logger.debug(f"SSH command output: {ssh_output}")
                            
                            # Extract display number from the Xvnc process
                            display_match = re.search(r'Xvnc :\s*(\d+)', ssh_output)
                            if display_match:
                                display = int(display_match.group(1))
                                port = 5900 + display
                                self.logger.info(f"Found display number: {display}, port: {port}")
                        except Exception as e:
                            self.logger.error(f"Error getting connection details: {str(e)}")
                    
                    # Extract submission time from the last two columns if there are at least 7 fields
                    submit_time = "2025-04-25 00:00:00"  # Default value
                    submit_time_raw = "Unknown"
                    
                    if len(fields) >= 7:
                        try:
                            # Try to extract the submit time from fields
                            # The format may be "Mon DD HH:MM" or "Mon DD YYYY" or just "HH:MM"
                            submit_time_raw = ' '.join(fields[-2:])  # Last two fields
                            
                            # Parse different possible formats
                            # The format may be "Mon DD HH:MM" or "Mon DD YYYY" or just "HH:MM"
                            
                            # Format: "Mon DD HH:MM"
                            mon_dd_hhmm_match = re.match(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2})', submit_time_raw)
                            if mon_dd_hhmm_match:
                                month_str, day, hour, minute = mon_dd_hhmm_match.groups()
                                # Convert month string to number
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_str, 1)
                                
                                # Use current year, but check if date is in future
                                current_date = datetime.now()
                                year = current_date.year
                                
                                # Create the date with the current year
                                submit_date = datetime(year, month, int(day), int(hour), int(minute))
                                
                                # If the date is in the future, it's likely from the previous year
                                if submit_date > current_date:
                                    submit_date = datetime(year - 1, month, int(day), int(hour), int(minute))
                                
                                # Format the date as string
                                submit_time = submit_date.strftime("%Y-%m-%d %H:%M:%S")
                                
                            # Format: "Mon DD YYYY"
                            elif re.match(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})', submit_time_raw):
                                mon_dd_yyyy_match = re.match(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})', submit_time_raw)
                                month_str, day, year = mon_dd_yyyy_match.groups()
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_str, 1)
                                
                                # Create the date
                                submit_date = datetime(int(year), month, int(day), 0, 0)
                                
                                # Format the date as string
                                submit_time = submit_date.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Format: "HH:MM" (just time, assume today's date)
                            elif re.match(r'(\d{1,2}):(\d{2})', submit_time_raw):
                                hhmm_match = re.match(r'(\d{1,2}):(\d{2})', submit_time_raw)
                                hour, minute = hhmm_match.groups()
                                
                                # Use current date
                                current_date = datetime.now()
                                
                                # Create datetime with today's date and the given time
                                submit_date = datetime(
                                    current_date.year, 
                                    current_date.month, 
                                    current_date.day,
                                    int(hour), 
                                    int(minute)
                                )
                                
                                # If the time is in the future (which is unlikely for a submission time),
                                # assume it was from yesterday
                                if submit_date > current_date:
                                    submit_date = submit_date - datetime.timedelta(days=1)
                                
                                # Format the date as string
                                submit_time = submit_date.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Unknown format: use default
                            else:
                                # Keep the default value and print a warning
                                self.logger.warning(f"Unknown submit time format: '{submit_time_raw}'")
                                
                        except Exception as e:
                            # Keep the default value and print the error
                            self.logger.error(f"Error parsing submit time '{submit_time_raw}': {str(e)}")
                    
                    # Create job entry with all required fields
                    job = {
                            'job_id': job_id,
                        'name': display_name,
                            'status': status,
                            'queue': queue,
                        'from_host': first_host,
                        'exec_host': exec_host,
                        'host': host,  # Use the cleaned host name for display
                        'user': user,
                        'cores': num_cores,
                        'mem_gb': memory_gb,
                        'submit_time': submit_time,
                        'submit_time_raw': submit_time_raw,
                        'runtime': runtime_display,  # Explicitly include runtime
                        'run_time_seconds': run_time_seconds if 'run_time_seconds' in locals() else 0
                    }
                    
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
    
    def _get_active_vnc_jobs_standard(self) -> List[Dict]:
        """
        Fallback method using standard bjobs command (no delimiter)
        """
        jobs = []
        
        try:
            # Get current user
            user = os.environ.get('USER', '')
            
            # Use simple bjobs command to get job list
            cmd = ['bjobs', '-u', user, '-J', 'myvnc_vncserver', '-w']
            self.logger.info(f"Executing command: {' '.join(cmd)}")
            
            output = self._run_command(cmd)
            
            lines = output.strip().split('\n')
            self.logger.debug(f"bjobs command output: {len(lines)} lines")
            
            if len(lines) <= 1:  # Only header or no output
                self.logger.info("No jobs found in output. Lines: {}".format(len(lines)))
                return jobs
                
            # Skip header line and process each job line
            for line in lines[1:]:
                self.logger.debug(f"Processing job line: {line}")
                
                # Skip empty lines
                if not line.strip():
                    continue
                
                # Process job
                try:
                    # Split the line by whitespace
                    fields = line.split()
                    if len(fields) < 7:
                        continue
                        
                    # Extract submission time from the last two columns if there are at least 7 fields
                    submit_time = "2025-04-25 00:00:00"  # Default value
                    submit_time_raw = "Unknown"
                    
                    if len(fields) >= 7:
                        try:
                            # Try to extract the submit time from fields
                            # The format may be "Mon DD HH:MM" or "Mon DD YYYY" or just "HH:MM"
                            submit_time_raw = ' '.join(fields[-2:])  # Last two fields
                            
                            # Parse different possible formats
                            # Note: re and datetime are already imported at the top level
                            
                            # Format: "Mon DD HH:MM"
                            mon_dd_hhmm_match = re.match(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2})', submit_time_raw)
                            if mon_dd_hhmm_match:
                                month_str, day, hour, minute = mon_dd_hhmm_match.groups()
                                # Convert month string to number
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_str, 1)
                                
                                # Use current year, but check if date is in future
                                current_date = datetime.now()
                                year = current_date.year
                                
                                # Create the date with the current year
                                submit_date = datetime(year, month, int(day), int(hour), int(minute))
                                
                                # If the date is in the future, it's likely from the previous year
                                if submit_date > current_date:
                                    submit_date = datetime(year - 1, month, int(day), int(hour), int(minute))
                                
                                # Format the date as string
                                submit_time = submit_date.strftime("%Y-%m-%d %H:%M:%S")
                                
                            # Format: "Mon DD YYYY"
                            elif re.match(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})', submit_time_raw):
                                mon_dd_yyyy_match = re.match(r'([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})', submit_time_raw)
                                month_str, day, year = mon_dd_yyyy_match.groups()
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_str, 1)
                                
                                # Create the date
                                submit_date = datetime(int(year), month, int(day), 0, 0)
                                
                                # Format the date as string
                                submit_time = submit_date.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Format: "HH:MM" (just time, assume today's date)
                            elif re.match(r'(\d{1,2}):(\d{2})', submit_time_raw):
                                hhmm_match = re.match(r'(\d{1,2}):(\d{2})', submit_time_raw)
                                hour, minute = hhmm_match.groups()
                                
                                # Use current date
                                current_date = datetime.now()
                                
                                # Create datetime with today's date and the given time
                                submit_date = datetime(
                                    current_date.year, 
                                    current_date.month, 
                                    current_date.day,
                                    int(hour), 
                                    int(minute)
                                )
                                
                                # If the time is in the future (which is unlikely for a submission time),
                                # assume it was from yesterday
                                if submit_date > current_date:
                                    submit_date = submit_date - datetime.timedelta(days=1)
                                
                                # Format the date as string
                                submit_time = submit_date.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Unknown format: use default
                            else:
                                # Keep the default value and print a warning
                                self.logger.warning(f"Unknown submit time format: '{submit_time_raw}'")
                                
                        except Exception as e:
                            # Keep the default value and print the error
                            self.logger.error(f"Error parsing submit time '{submit_time_raw}': {str(e)}")
                    
                    # Create basic job info
                    job = {
                        'job_id': fields[0].strip(),
                        'user': fields[1].strip(),
                        'status': fields[2].strip(),
                        'queue': fields[3].strip(),
                        'from_host': fields[4].strip(),
                        'exec_host': fields[5].strip(),
                        'host': fields[5].strip(),
                        'runtime': 'N/A',  # Default runtime
                        'submit_time': submit_time,
                        'submit_time_raw': submit_time_raw
                    }
                    
                    # Add to jobs list
                    jobs.append(job)
                except Exception as e:
                    self.logger.error(f"Error processing job in fallback method: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error in fallback job retrieval: {str(e)}")
        
        return jobs
            
    def get_vnc_connection_details(self, job_id: str) -> Optional[Dict]:
        """
        Get connection details for a VNC job
        
        Args:
            job_id: Job ID
            
        Returns:
            Dictionary with connection details or None if not found
        """
        try:
            # First get basic job info to extract the host
            basic_output = self._run_command(['bjobs', '-w', job_id])
            basic_lines = basic_output.strip().split('\n')
            
            # Initialize host
            host = None
            output = ""  # Initialize output to avoid reference error
            
            # Extract host from the basic output first (most reliable)
            if len(basic_lines) > 1:  # Header + job line
                job_line = basic_lines[1]
                self.logger.debug(f"Basic job info: {job_line}")
                fields = job_line.split()
                
                if len(fields) >= 6 and 'RUN' in job_line:
                    # Format: JOBID USER STATUS QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME
                    exec_host = fields[5]  # EXEC_HOST is the 6th field (index 5)
                    if exec_host and exec_host != '-':
                        if ":" in exec_host:
                            # For multi-host jobs, take the first host
                            host = exec_host.split(':')[0]
                        else:
                            host = exec_host
                        self.logger.debug(f"Found host from basic job info: {host}")
            
            # If we didn't get the host from basic output, get detailed info
            if not host:
                # Get detailed job info
                output = self._run_command(['bjobs', '-l', job_id])
                
                # Try to extract host information from detailed output
                host_match = re.search(r'Started on <([^>]+)>', output)
                if host_match:
                    host = host_match.group(1)
                    self.logger.debug(f"Found host from 'Started on' pattern: {host}")
                
                # Look for EXEC_HOST pattern as fallback
                if not host:
                    exec_host_match = re.search(r'EXEC_HOST\s*:\s*(\S+)', output, re.IGNORECASE)
                    if exec_host_match:
                        host_info = exec_host_match.group(1)
                        if ":" in host_info:
                            host = host_info.split(':')[0]
                        else:
                            host = host_info
                        self.logger.debug(f"Found host from EXEC_HOST pattern: {host}")
            
            # If we still don't have a host, print error and exit
            if not host:
                self.logger.error(f"Could not determine execution host for job {job_id}")
                return None
            
            # Get the user running the job
            user_match = re.search(r'User <([^>]+)>', output)
            user = user_match.group(1) if user_match else os.environ.get('USER', '')
            
            # Query the remote host for VNC process information
            try:
                # Clean up the hostname - remove any non-alphanumeric characters except for hyphens
                host = host.strip()
                # More aggressive cleaning - keep only alphanumeric chars, hyphens, and dots
                host = re.sub(r'[^a-zA-Z0-9\-\.]', '', host)
                self.logger.debug(f"Cleaned host name: '{host}'")
                
                if not host or not re.match(r'^[a-zA-Z0-9\-\.]+$', host):
                    self.logger.error(f"Host name is invalid after cleaning: '{host}'")
                    raise ValueError(f"Invalid hostname: {host}")
                
                self.logger.info(f"Attempting to query VNC information on host: {host} for user: {user}")
                
                # Use SSH to run a command on the remote host to find the Xvnc process
                ssh_cmd = ['ssh', host, f"ps -u {user} -o pid,command | grep Xvnc"]
                self.logger.debug(f"Running SSH command: {' '.join(ssh_cmd)}")
                
                vnc_process_output = self._run_command(ssh_cmd)
                self.logger.debug(f"SSH command output: {vnc_process_output}")
                
                # Look for the display number in the Xvnc process command line
                # Format will be something like: Xvnc :1 
                display_match = re.search(r'Xvnc\s+:(\d+)', vnc_process_output)
                
                if display_match:
                    display_num = int(display_match.group(1))
                    self.logger.info(f"Found display number from Xvnc pattern: {display_num}")
                else:
                    # Fallback to scanning through all command line arguments
                    args_match = re.search(r'Xvnc.*?:(\d+)', vnc_process_output)
                    if args_match:
                        display_num = int(args_match.group(1))
                        self.logger.info(f"Found display number from args pattern: {display_num}")
                    else:
                        # If we can't find the display number, use a fallback
                        display_num = (int(job_id) % 5) + 1  # Results in 1-5
                        self.logger.info(f"Using fallback display number: {display_num}")
            except Exception as e:
                # If we can't query the remote host, use the fallback method
                self.logger.error(f"Error querying remote host for VNC process: {str(e)}")
                display_num = (int(job_id) % 5) + 1  # Results in 1-5
                self.logger.info(f"Using fallback display number after error: {display_num}")
            
            # VNC uses port 5900+display number
            vnc_port = 5900 + display_num
            
            return {
                'host': host,
                'display': display_num,
                'port': vnc_port,
                'connection_string': f"{host}:{display_num}"
            }
        except (RuntimeError, ValueError) as e:
            self.logger.error(f"Error getting connection details for job {job_id}: {str(e)}")
            return None 