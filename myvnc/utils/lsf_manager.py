import subprocess
import shlex
import re
from typing import Dict, List, Optional

class LSFManager:
    """Manages interactions with the LSF job scheduler via command line"""
    
    def __init__(self):
        """
        Initialize the LSF manager and check if LSF is available
        
        Raises:
            RuntimeError: If LSF is not available
        """
        self._check_lsf_available()
    
    def _check_lsf_available(self):
        """
        Check if LSF is available on the system
        
        Raises:
            RuntimeError: If LSF is not available
        """
        try:
            subprocess.run(['which', 'bjobs'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            raise RuntimeError("LSF is not available on this system")
    
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
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                   text=True, encoding='utf-8')
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Command failed: {e.stderr}")
    
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
        
        # Add the vncserver command with its arguments
        vnc_cmd = f"vncserver -geometry {vnc_config['resolution']} -depth {vnc_config['color_depth']} " + \
                 f"-name {vnc_config['name']} -wm {vnc_config['window_manager']}"
        
        # Add site-specific settings if available
        if 'site' in vnc_config and vnc_config['site'] != 'default':
            vnc_cmd += f" -site {vnc_config['site']}"
        
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
        except RuntimeError:
            # Return empty list on error
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