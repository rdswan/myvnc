import subprocess
import shlex
import re
import sys
import time
import os
from typing import Dict, List, Optional, Tuple
import datetime
import json
from pathlib import Path

from myvnc.utils.config_manager import ConfigManager

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
        try:
            # Compatible with Python 3.6 - removed text=True
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout = result.stdout.decode('utf-8')
            stderr = result.stderr.decode('utf-8')
            
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
            
            # Add failed command to history for debugging
            self.command_history.append({
                'command': cmd_str,
                'stdout': e.stdout.decode('utf-8') if e.stdout else '',
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
                
            # Add vncserver command to bsub command
            bsub_cmd.extend(vncserver_cmd)
            
            # Convert command list to string for logging
            cmd_str = ' '.join(str(arg) for arg in bsub_cmd)
            print(f"About to execute LSF command: {cmd_str}")
            
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
                result = subprocess.run(
                    bsub_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    # Remove text=True for Python 3.6 compatibility
                    # text=True,
                    check=True
                )
                # Convert bytes to string for Python 3.6
                stdout = result.stdout.decode('utf-8')
                stderr = result.stderr.decode('utf-8')
                
                # Extract job ID from output
                job_id_match = re.search(r'Job <(\d+)>', stdout)
                job_id = job_id_match.group(1) if job_id_match else 'unknown'
                
                # Update command history with success
                cmd_entry['stdout'] = stdout
                cmd_entry['stderr'] = stderr
                cmd_entry['success'] = True
                
                return job_id
                
            except subprocess.CalledProcessError as e:
                # Convert bytes to string for Python 3.6
                stdout = e.stdout.decode('utf-8') if e.stdout else ''
                stderr = e.stderr.decode('utf-8') if e.stderr else ''
                
                error_msg = f"Command failed: {stderr}"
                
                # Update command history with failure
                cmd_entry['stdout'] = stdout
                cmd_entry['stderr'] = error_msg
                
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
        try:
            self._run_command(['bkill', job_id])
            return True
        except RuntimeError:
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
            
            # Use bjobs with output formatting and delimiter for easier parsing
            # Format includes the delimiter in quotes as part of the -o option
            cmd = f'bjobs -o "jobid stat user queue first_host run_time submit_time command delimiter=\';\'" -noheader -u {user} -J myvnc_vncserver'
            print(f"Running LSF jobs command: {cmd}", file=sys.stderr)
            
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = proc.communicate()
            
            if error:
                print(f"Error in bjobs command: {error.decode('utf-8')}", file=sys.stderr)
                return jobs
            
            lines = output.decode('utf-8').strip().split('\n')
            print(f"bjobs command output:", file=sys.stderr)
            print(f"{len(lines)} line(s) in output.", file=sys.stderr)
            if not lines or (len(lines) == 1 and not lines[0].strip()):
                print(f"No jobs found in output.", file=sys.stderr)
                return jobs
                
            # Process each job line
            for line in lines:
                print(f"Processing job line: {line}", file=sys.stderr)
                
                # Split the line by the delimiter
                fields = line.split(';')
                if len(fields) < 7:  # Need at least 7 fields
                    print(f"Incomplete fields in line, expected at least 7, got {len(fields)}", file=sys.stderr)
                    continue
                    
                # Extract job information from fields
                try:
                    job_id = fields[0].strip()
                    status = fields[1].strip()
                    user = fields[2].strip()
                    queue = fields[3].strip()
                    host = fields[4].strip()  # Extract first_host
                    run_time_str = fields[5].strip()
                    submit_time_str = fields[6].strip()
                    command = ';'.join(fields[7:]).strip()  # Command might contain semicolons itself
                    
                    print(f"Extracted fields: job_id={job_id}, status={status}, user={user}, queue={queue}, host={host}", file=sys.stderr)
                    print(f"Runtime field: '{run_time_str}'", file=sys.stderr)
                    
                    # Parse runtime in seconds
                    run_time_seconds = 0
                    try:
                        # Extract just the numeric part from the run_time string
                        run_time_match = re.search(r'(\d+)', run_time_str)
                        if run_time_match:
                            run_time_seconds = int(run_time_match.group(1))
                            print(f"Parsed runtime: {run_time_seconds} seconds", file=sys.stderr)
                        else:
                            print(f"No numeric runtime found in '{run_time_str}'", file=sys.stderr)
                    except (ValueError, TypeError, IndexError) as e:
                        print(f"Error parsing runtime '{run_time_str}': {e}", file=sys.stderr)
                    
                    # Get detailed job information for display name, cores and memory information
                    display_name = "VNC Session"  # Default fallback name
                    num_cores = None
                    memory_gb = None
                    
                    try:
                        job_detail_cmd = f'bjobs -l {job_id}'
                        job_detail_result = subprocess.run(job_detail_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        job_detail_output = job_detail_result.stdout.decode('utf-8')
                        print(f"Job {job_id} detailed output snippet: \n{job_detail_output[:300]}...", file=sys.stderr)
                        
                        # Try to extract the host from detailed output
                        host_match = re.search(r'Started on <([^>]+)>', job_detail_output)
                        if host_match:
                            host = host_match.group(1)
                            print(f"Found host from started on pattern: {host}", file=sys.stderr)
                        else:
                            # Second attempt to get the host
                            host_match = re.search(r'EXEC_HOST\s*:\s*(\S+)', job_detail_output, re.IGNORECASE)
                            if host_match:
                                host = host_match.group(1).split(':')[0]  # Take first host if multiple
                                print(f"Found host from EXEC_HOST pattern: {host}", file=sys.stderr)
                        
                        # Extract display name from command
                        name_match = re.search(r'-name\s+([^\s"]+|"([^"]+)")', command)
                        if name_match:
                            if name_match.group(2):  # If captured in quotes
                                display_name = name_match.group(2)
                            else:
                                display_name = name_match.group(1)
                            print(f"Found display name from command: {display_name}", file=sys.stderr)
                        else:
                            # Try to extract from the detailed job output
                            command_match = re.search(r'Command <([^>]+)>', job_detail_output)
                            if command_match:
                                command_detail = command_match.group(1)
                                name_flag_match = re.search(r'-name\s+([^\s"]+|"([^"]+)")', command_detail)
                                if name_flag_match:
                                    if name_flag_match.group(2):  # If captured in quotes
                                        display_name = name_flag_match.group(2)
                                    else:
                                        display_name = name_flag_match.group(1)
                                    print(f"Found display name from detailed command: {display_name}", file=sys.stderr)
                                else:
                                    # If no -name parameter, try to use the last directory component in the CWD
                                    cwd_match = re.search(r'CWD <([^>]+)>', job_detail_output)
                                    if cwd_match:
                                        cwd = cwd_match.group(1)
                                        # Extract the last directory component
                                        display_name = os.path.basename(cwd)
                                        print(f"Using CWD as display name: {display_name}", file=sys.stderr)
                        
                        # Find resource-related lines for cores and memory
                        resource_lines = []
                        for line in job_detail_output.split('\n'):
                            if 'Task(s)' in line or 'rusage[mem=' in line:
                                resource_lines.append(line)
                        
                        if resource_lines:
                            print(f"Resource related lines for job {job_id}:", file=sys.stderr)
                            for rl in resource_lines:
                                print(f"  - {rl}", file=sys.stderr)
                        
                        # Try to extract cores from Tasks pattern, e.g., "2 Task(s)"
                        tasks_match = re.search(r'(\d+)\s+Task\(s\)', job_detail_output)
                        if tasks_match:
                            num_cores = int(tasks_match.group(1))
                            print(f"Found cores from tasks pattern: {num_cores}", file=sys.stderr)
                        
                        # Try to extract memory from rusage pattern
                        mem_match = re.search(r'rusage\[mem=(\d+(\.\d+)?)([KMG]?)\]', job_detail_output)
                        if mem_match:
                            mem_value = float(mem_match.group(1))
                            mem_unit = mem_match.group(3)
                            
                            # If no unit is provided in the rusage context, assume GB
                            if not mem_unit:
                                print(f"No unit specified in rusage context, assuming GB", file=sys.stderr)
                                mem_unit = 'G'
                            
                            # Convert to GB
                            if mem_unit == 'K':
                                memory_gb = mem_value / (1024 * 1024)
                            elif mem_unit == 'M':
                                memory_gb = mem_value / 1024
                            elif mem_unit == 'G':
                                memory_gb = mem_value
                            
                            # Round to 2 decimal places
                            memory_gb = round(memory_gb, 2)
                            print(f"Found memory from rusage regex pattern: {memory_gb}GB (value={mem_value}, unit={mem_unit})", file=sys.stderr)
                        
                    except Exception as e:
                        print(f"Error getting detailed job info: {e}", file=sys.stderr)
                    
                    # Get connection details for display and port
                    display = None
                    port = None
                    
                    if host and host != "N/A":
                        # Try to get connection details
                        try:
                            conn_details = self.get_vnc_connection_details(job_id)
                            if conn_details:
                                display = conn_details.get('display')
                                port = conn_details.get('port')
                        except Exception as e:
                            print(f"Error getting connection details: {e}", file=sys.stderr)
                    
                    # Format runtime in days and hours
                    if run_time_seconds > 0:
                        days = run_time_seconds // 86400  # 86400 seconds in a day
                        hours = (run_time_seconds % 86400) // 3600  # 3600 seconds in an hour
                        minutes = (run_time_seconds % 3600) // 60  # 60 seconds in a minute
                        
                        # Format runtime string
                        if days > 0:
                            runtime_display = f"{days}d {hours}h"
                        elif hours > 0:
                            runtime_display = f"{hours}h {minutes}m"
                        else:
                            runtime_display = f"{minutes}m"
                    else:
                        runtime_display = "N/A"
                    
                    # Create job entry
                    job_entry = {
                        'job_id': job_id,
                        'name': display_name,
                        'status': status,
                        'queue': queue,
                        'host': host,
                        'user': user,
                        'display': display,
                        'port': port,
                        'runtime_seconds': run_time_seconds,
                        'runtime_display': runtime_display,
                        'num_cores': num_cores,
                        'memory_gb': memory_gb,
                        'command': command
                    }
                    
                    jobs.append(job_entry)
                except Exception as e:
                    print(f"Error processing job {job_id if 'job_id' in locals() else 'unknown'}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error retrieving VNC jobs: {e}", file=sys.stderr)
        
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
                print(f"Basic job info: {job_line}", file=sys.stderr)
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
                        print(f"Found host from basic job info: {host}", file=sys.stderr)
            
            # If we didn't get the host from basic output, get detailed info
            if not host:
                # Get detailed job info
                output = self._run_command(['bjobs', '-l', job_id])
                
                # Try to extract host information from detailed output
                host_match = re.search(r'Started on <([^>]+)>', output)
                if host_match:
                    host = host_match.group(1)
                    print(f"Found host from 'Started on' pattern: {host}", file=sys.stderr)
                
                # Look for EXEC_HOST pattern as fallback
                if not host:
                    exec_host_match = re.search(r'EXEC_HOST\s*:\s*(\S+)', output, re.IGNORECASE)
                    if exec_host_match:
                        host_info = exec_host_match.group(1)
                        if ":" in host_info:
                            host = host_info.split(':')[0]
                        else:
                            host = host_info
                        print(f"Found host from EXEC_HOST pattern: {host}", file=sys.stderr)
            
            # If we still don't have a host, print error and exit
            if not host:
                print(f"Could not determine execution host for job {job_id}", file=sys.stderr)
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
                print(f"Cleaned host name: '{host}'", file=sys.stderr)
                
                if not host or not re.match(r'^[a-zA-Z0-9\-\.]+$', host):
                    print(f"Host name is invalid after cleaning: '{host}'", file=sys.stderr)
                    raise ValueError(f"Invalid hostname: {host}")
                
                print(f"Attempting to query VNC information on host: {host} for user: {user}", file=sys.stderr)
                
                # Use SSH to run a command on the remote host to find the Xvnc process
                ssh_cmd = ['ssh', host, f"ps -u {user} -o pid,command | grep Xvnc"]
                print(f"Running SSH command: {' '.join(ssh_cmd)}", file=sys.stderr)
                
                vnc_process_output = self._run_command(ssh_cmd)
                print(f"SSH command output: {vnc_process_output}", file=sys.stderr)
                
                # Look for the display number in the Xvnc process command line
                # Format will be something like: Xvnc :1 
                display_match = re.search(r'Xvnc\s+:(\d+)', vnc_process_output)
                
                if display_match:
                    display_num = int(display_match.group(1))
                    print(f"Found display number from Xvnc pattern: {display_num}", file=sys.stderr)
                else:
                    # Fallback to scanning through all command line arguments
                    args_match = re.search(r'Xvnc.*?:(\d+)', vnc_process_output)
                    if args_match:
                        display_num = int(args_match.group(1))
                        print(f"Found display number from args pattern: {display_num}", file=sys.stderr)
                    else:
                        # If we can't find the display number, use a fallback
                        display_num = (int(job_id) % 5) + 1  # Results in 1-5
                        print(f"Using fallback display number: {display_num}", file=sys.stderr)
            except Exception as e:
                # If we can't query the remote host, use the fallback method
                print(f"Error querying remote host for VNC process: {str(e)}", file=sys.stderr)
                display_num = (int(job_id) % 5) + 1  # Results in 1-5
                print(f"Using fallback display number after error: {display_num}", file=sys.stderr)
            
            # VNC uses port 5900+display number
            vnc_port = 5900 + display_num
            
            return {
                'host': host,
                'display': display_num,
                'port': vnc_port,
                'connection_string': f"{host}:{display_num}"
            }
        except (RuntimeError, ValueError) as e:
            print(f"Error getting connection details for job {job_id}: {str(e)}", file=sys.stderr)
            return None 