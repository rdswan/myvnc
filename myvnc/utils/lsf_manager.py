import subprocess
import shlex
import re
import sys
import time
import os
from typing import Dict, List, Optional, Tuple
import datetime

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
                'memory_mb': 2048,
                'time_limit': '00:30'
            }
            
            # Build the command but don't execute it (dry run)
            cmd = [
                'bsub',
                '-q', lsf_config['queue'],
                '-n', str(lsf_config['num_cores']),
                '-M', str(lsf_config['memory_mb']),
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
            
            # Convert memory from MB to GB (with minimum of 1GB)
            memory_mb = lsf_config.get('memory_mb', 4096)
            # If memory_mb is already small enough to be in GB, use it directly
            if memory_mb < 1000:  # If the memory value is already small, it's likely already in GB
                memory_gb = memory_mb
            else:
                memory_gb = max(1, memory_mb // 1024)
            
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
                'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                    'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        Get active VNC jobs
        
        Returns:
            List of jobs as dictionaries
        """
        try:
            # Get all jobs for current user
            output = self._run_command(['bjobs', '-w'])
            
            # Parse the output
            jobs = []
            lines = output.strip().split('\n')
            
            # Skip if only header line is present (no jobs)
            if len(lines) <= 1:
                return jobs
            
            # Process each job line
            for line in lines[1:]:  # Skip header line
                fields = line.split()
                if len(fields) >= 6:  # Ensure we have enough fields
                    job_id = fields[0]
                    name = fields[3]
                    # Only include VNC jobs
                    if 'vnc' in name.lower():
                        status = fields[2]
                        queue = fields[1]
                        user = fields[1]
                        jobs.append({
                            'job_id': job_id,
                            'name': name,
                            'status': status,
                            'queue': queue,
                            'user': user
                        })
            
            return jobs
        except Exception as e:
            # Catch and log any exception
            print(f"Error retrieving VNC jobs: {str(e)}", file=sys.stderr)
            # Return empty list on any error
            return []
            
    def get_vnc_connection_details(self, job_id: str) -> Optional[Dict]:
        """
        Get connection details for a VNC job
        
        Args:
            job_id: Job ID
            
        Returns:
            Dictionary with connection details or None if not found
        """
        try:
            # Get job details
            output = self._run_command(['bjobs', '-l', job_id])
            
            # Try to extract host information
            host_match = re.search(r'Started on <([^>]+)>', output)
            if not host_match:
                return None
                
            host = host_match.group(1)
            
            # The display number is typically assigned by the VNC server
            # Here we make a simplification: just use the last part of the job ID
            # In a real implementation, this would need to be more sophisticated
            display = job_id[-2:] if len(job_id) > 2 else job_id
            
            return {
                'host': host,
                'display': display,
                'port': 5900 + int(display),  # VNC typically uses port 5900+display
                'connection_string': f"{host}:{display}"
            }
        except (RuntimeError, ValueError):
            return None 