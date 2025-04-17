from typing import Dict, List
import subprocess
import json

class LSFManager:
    def __init__(self):
        self._check_lsf_available()
    
    def _check_lsf_available(self):
        try:
            subprocess.run(['bjobs', '-V'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("LSF is not available on this system")
    
    def submit_vnc_job(self, vnc_config: Dict, lsf_config: Dict) -> str:
        """
        Submit a VNC job to LSF and return the job ID
        """
        cmd = [
            'bsub',
            '-q', lsf_config['queue'],
            '-n', str(lsf_config['num_cores']),
            '-M', str(lsf_config['memory_mb']),
            '-W', lsf_config['time_limit'],
            '-J', vnc_config['name'],
            'vncserver',
            f"-geometry {vnc_config['resolution']}",
            f"-depth {vnc_config['color_depth']}",
            f"-name {vnc_config['name']}",
            f"-wm {vnc_config['window_manager']}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Extract job ID from bsub output
        job_id = result.stdout.strip().split()[1].strip('<>')
        return job_id
    
    def kill_vnc_job(self, job_id: str) -> bool:
        """
        Kill a VNC job by its job ID
        """
        try:
            subprocess.run(['bkill', job_id], capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def get_active_vnc_jobs(self) -> List[Dict]:
        """
        Get all active VNC jobs for the current user
        """
        cmd = ['bjobs', '-o', 'jobid:10 name:20 user:10 stat:10 queue:10']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        jobs = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            if line.strip():
                jobid, name, user, stat, queue = line.split()
                if 'vnc' in name.lower():
                    jobs.append({
                        'job_id': jobid,
                        'name': name,
                        'user': user,
                        'status': stat,
                        'queue': queue
                    })
        return jobs 