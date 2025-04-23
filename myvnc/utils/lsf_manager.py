import subprocess
import shlex
import re
import sys
from typing import Dict, List, Optional, Tuple

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
                results.append({
                    'command': ' '.join(cmd),
                    'output': str(e),
                    'success': False
                })
        
        return results
    
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
        """
        Submit a VNC job to LSF
        
        Args:
            vnc_config: VNC configuration
            lsf_config: LSF configuration
            
        Returns:
            Job ID
            
        Raises:
            RuntimeError: If the job submission fails
        """
        # Construct bsub command
        cmd = [
            'bsub',
            '-q', lsf_config['queue'],
            '-n', str(lsf_config['num_cores']),
            '-M', str(lsf_config['memory_mb']),
            '-W', lsf_config['time_limit'],
            '-J', vnc_config['name']
        ]
        
        # Add site-specific parameters if site is specified
        if 'site' in vnc_config and vnc_config['site']:
            site_domain = self.config_manager.get_site_domain(vnc_config['site'])
            if site_domain:
                # Add site domain to job submission
                cmd.extend(['-m', f'{site_domain}-*'])
        
        # Get the vncserver path from config or use default as fallback
        vncserver_path = vnc_config.get('vncserver_path', '/usr/bin/vncserver')
        
        # Add the vncserver command with its arguments
        # Note: Only using supported options (geometry, depth, name)
        vnc_cmd = f"{vncserver_path} -geometry {vnc_config['resolution']} -depth {vnc_config['color_depth']} " + \
                 f"-name {vnc_config['name']}"
        
        # Note: Removed -wm and -site options as they're not supported by vncserver
        cmd.append(vnc_cmd)
        
        # Run the command
        output = self._run_command(cmd)
        
        # Extract job ID using regex
        match = re.search(r'Job <(\d+)>', output)
        if match:
            return match.group(1)
        else:
            raise RuntimeError("Failed to extract job ID from bsub output")
    
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