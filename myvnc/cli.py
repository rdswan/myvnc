import click
import json
import sys
from pathlib import Path
from tabulate import tabulate
from .utils.config_manager import ConfigManager
from .utils.lsf_manager import LSFManager

@click.group()
def cli():
    """MyVNC - A CLI application to manage VNC sessions through LSF"""
    pass

@cli.command()
def list():
    """List all active VNC sessions"""
    try:
        lsf_manager = LSFManager()
        jobs = lsf_manager.get_active_vnc_jobs()
        
        if not jobs:
            click.echo("No active VNC sessions found.")
            return
        
        # Prepare data for tabulate
        headers = ["Job ID", "Name", "User", "Status", "Queue"]
        table_data = [[job['job_id'], job['name'], job['user'], job['status'], job['queue']] for job in jobs]
        
        # Print table
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)

@cli.command()
@click.option('--name', prompt='VNC session name', help='Name for the VNC session')
@click.option('--resolution', type=click.Choice(['1920x1080', '2560x1440', '3840x2160', '1280x720']), 
              default='1920x1080', help='Resolution for the VNC session')
@click.option('--wm', type=click.Choice(['gnome', 'kde', 'xfce', 'mate']), 
              default='gnome', help='Window manager for the VNC session')
@click.option('--queue', type=click.Choice(['vnc_queue', 'interactive', 'gpu_queue']), 
              default='vnc_queue', help='LSF queue to submit the job to')
@click.option('--cores', type=int, default=2, help='Number of cores to allocate')
@click.option('--memory', type=int, default=4096, help='Memory to allocate in MB')
@click.option('--vncserver-path', help='Path to vncserver binary')
def create(name, resolution, wm, queue, cores, memory, vncserver_path):
    """Create a new VNC session"""
    try:
        config_manager = ConfigManager()
        lsf_manager = LSFManager()
        
        # Get default vncserver path from config
        default_vncserver_path = config_manager.get_vnc_defaults().get('vncserver_path', '/usr/bin/vncserver')
        
        # Prepare configurations
        vnc_config = {
            'name': name,
            'resolution': resolution,
            'window_manager': wm,
            'color_depth': 24,
            'vncserver_path': vncserver_path or default_vncserver_path
        }
        
        lsf_config = {
            'queue': queue,
            'num_cores': cores,
            'memory_mb': memory
        }
        
        # Submit job
        job_id = lsf_manager.submit_vnc_job(vnc_config, lsf_config)
        click.echo(f"VNC session created successfully! Job ID: {job_id}")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)

@cli.command()
@click.argument('job_id')
def kill(job_id):
    """Kill a VNC session by job ID"""
    try:
        lsf_manager = LSFManager()
        
        if lsf_manager.kill_vnc_job(job_id):
            click.echo(f"VNC session {job_id} killed successfully.")
        else:
            click.echo(f"Failed to kill VNC session {job_id}.", err=True)
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    cli() 