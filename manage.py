#!/proj_risc/user_dev/bswan/tools_src/myvnc/.venv_py3/bin/python3
"""
Management script for the MyVNC server

This script provides commands to start, stop, restart and check the status of the MyVNC server.

Usage:
    python3 manage.py start   - Start the server
    python3 manage.py stop    - Stop the server
    python3 manage.py restart - Restart the server
    python3 manage.py status  - Show server status
"""

import os
import sys
import time
import argparse
import signal
import subprocess
import datetime
import json
import psutil
import glob
from pathlib import Path

# Add the current directory to the path so we can import from the myvnc package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from myvnc.web.server import load_server_config
from myvnc.utils.log_manager import get_logger, setup_logging, get_current_log_file

# Set up a logger
logger = None

def setup_logging_for_manage():
    """Set up logging for the management script"""
    global logger
    
    # First try to get an existing logger
    if logger is not None:
        return logger
        
    # Only create a new logger if one doesn't exist
    config = load_server_config()
    
    # Try using get_logger first, which will reuse an existing logger if possible
    logger = get_logger()
    
    # If that didn't work, fall back to setup_logging
    if logger is None:
        logger = setup_logging(config=config)
        
    return logger

def get_pid_file():
    """Get the path to the PID file"""
    # Load server configuration to get logdir
    config = load_server_config()
    logdir = config.get('logdir', '/tmp')
    
    # Use the logdir from the config file
    return Path(logdir) / "myvnc_server.pid"

def write_pid_file(pid):
    """Write the PID to the PID file"""
    with open(get_pid_file(), 'w') as f:
        f.write(str(pid))
        
def read_pid_file():
    """Read the PID from the PID file if it exists"""
    pid_file = get_pid_file()
    if pid_file.exists():
        with open(pid_file, 'r') as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return None
    return None

def is_server_running(pid=None):
    """Check if the server is running"""
    if pid is None:
        pid = read_pid_file()
        
    if pid is None:
        return False
        
    try:
        process = psutil.Process(pid)
        cmdline = ' '.join(process.cmdline())
        # Check if it's our Python server process
        return "python" in cmdline and "main.py" in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False

def find_server_process():
    """Find the server process if it's running but we don't have a PID file"""
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if "python" in cmdline and "main.py" in cmdline:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None

def get_process_start_time(pid):
    """Get the start time of a process"""
    try:
        process = psutil.Process(pid)
        return datetime.datetime.fromtimestamp(process.create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

def get_uptime(pid):
    """Get the uptime of the server process"""
    start_time = get_process_start_time(pid)
    if start_time:
        uptime = datetime.datetime.now() - start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    return "Unknown"

def get_log_filename_for_pid(pid):
    """Get the log filename using PID format"""
    config = load_server_config()
    logdir = config.get('logdir', '/tmp')
    return str(Path(logdir) / f"myvnc_{pid}.log")

def find_server_log_file(pid):
    """Find the log file associated with the given PID"""
    if not pid:
        return None
    
    # Get server config for log directory
    config = load_server_config()
    
    log_dir = config.get('logdir', '/tmp')
    log_path = Path(log_dir)
    
    # Look for log file with PID in name
    log_file = log_path / f'myvnc_{pid}.log'
    
    if log_file.exists():
        return str(log_file)
    
    # Fallback: Check all log files in directory if specific file not found
    try:
        for file in log_path.glob('myvnc_*.log'):
            if f'myvnc_{pid}.log' in file.name:
                return str(file)
    except Exception as e:
        print(f"Error searching for log files: {e}")
    
    return None

def start_server():
    """Start the server if it's not already running"""
    logger = setup_logging_for_manage()
    
    # Check if the server is already running
    pid = read_pid_file()
    if pid and is_server_running(pid):
        logger.info(f"Server is already running with PID {pid}")
        return
    
    # If we have a PID file but the server is not running, clean it up
    if pid:
        logger.info(f"Removing stale PID file for PID {pid}")
        os.remove(get_pid_file())
    
    # Check if we can find the server process even without a PID file
    pid = find_server_process()
    if pid:
        logger.info(f"Server is already running with PID {pid} (discovered)")
        write_pid_file(pid)
        return
    
    # Start the server
    logger.info("Starting MyVNC server")
    
    # Get the full path to main.py
    main_script = Path(os.path.dirname(os.path.abspath(__file__))) / "main.py"
    
    # Start the server process
    process = subprocess.Popen([sys.executable, str(main_script)], 
                             stdout=subprocess.PIPE, 
                             stderr=subprocess.STDOUT,
                             start_new_session=True)  # Detach from terminal
    
    # Give it a moment to start
    time.sleep(1)
    
    # Check if the process is still running (didn't immediately exit)
    if process.poll() is None:
        # Process is still running, write the PID file
        logger.info(f"Server started with PID {process.pid}")
        write_pid_file(process.pid)
        
        # We need to pass the PID to the main.py script somehow
        # This is usually done by creating an environment variable or a configuration file
        # For now, we'll just make sure we can find the log file when needed
    else:
        # Process exited, read the output to see why
        output = process.stdout.read().decode('utf-8')
        logger.error(f"Server failed to start:\n{output}")
        sys.exit(1)

def stop_server():
    """Stop the server if it's running"""
    logger = setup_logging_for_manage()
    
    # Check if we have a PID file
    pid = read_pid_file()
    
    # If not, try to find the server process
    if pid is None:
        pid = find_server_process()
        if pid:
            write_pid_file(pid)
    
    # If we still don't have a PID, the server is not running
    if pid is None:
        logger.info("Server is not running")
        return
    
    # Check if the process is actually running
    if not is_server_running(pid):
        logger.info(f"Server is not running (PID {pid} not found)")
        os.remove(get_pid_file())
        return
    
    # Send a SIGTERM signal to gracefully stop the server
    logger.info(f"Stopping server with PID {pid}")
    
    try:
        os.kill(pid, signal.SIGTERM)
        
        # Wait for the process to exit
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if not is_server_running(pid):
                break
            time.sleep(0.1)
        
        # If the process is still running after waiting, force kill it
        if is_server_running(pid):
            logger.warning(f"Server did not exit gracefully, forcing termination")
            os.kill(pid, signal.SIGKILL)
        
        # Remove the PID file
        if os.path.exists(get_pid_file()):
            os.remove(get_pid_file())
            
        logger.info("Server stopped")
        
    except ProcessLookupError:
        logger.warning(f"Process {pid} not found, removing PID file")
        if os.path.exists(get_pid_file()):
            os.remove(get_pid_file())

def restart_server():
    """Restart the server"""
    logger = setup_logging_for_manage()
    
    logger.info("Restarting server")
    
    stop_server()
    # Give it a moment to shut down completely
    time.sleep(1)
    start_server()

def server_status():
    """Show the status of the server"""
    logger = setup_logging_for_manage()
    
    # Load server configuration to display
    config = load_server_config()
    
    # Check if the server is running
    pid = read_pid_file()
    
    # If we don't have a PID file, try to find the server process
    if pid is None:
        pid = find_server_process()
        if pid:
            write_pid_file(pid)
    
    if pid is None or not is_server_running(pid):
        logger.info("Server status: Not running")
        
        # Print status for user to see
        print("Server status: Not running")
        return
    
    # Server is running, get more information
    uptime = get_uptime(pid)
    
    host = config.get('host', 'localhost')
    port = config.get('port', '9143')
    logdir = config.get('logdir', '/tmp')
    
    status_info = {
        'status': 'Running',
        'pid': pid,
        'host': host,
        'port': port,
        'url': f'http://{host}:{port}',
        'logdir': logdir,
        'uptime': uptime
    }
    
    # Find the log file for this PID
    server_log_file = find_server_log_file(pid)
    if server_log_file:
        status_info['current_log'] = server_log_file
    
    # Print status information
    print("Server status:")
    print(f"  Status: Running")
    print(f"  PID: {pid}")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  URL: http://{host}:{port}")
    print(f"  Log directory: {logdir}")
    print(f"  Current log: {server_log_file if server_log_file else 'Unknown'}")
    print(f"  Uptime: {uptime}")
    
    logger.info(f"Server status: Running (PID: {pid}, Uptime: {uptime})")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="MyVNC Server Management Script")
    parser.add_argument('command', choices=['start', 'stop', 'restart', 'status'],
                      help='Command to execute')
    
    args = parser.parse_args()
    
    if args.command == 'start':
        start_server()
    elif args.command == 'stop':
        stop_server()
    elif args.command == 'restart':
        restart_server()
    elif args.command == 'status':
        server_status()

if __name__ == "__main__":
    main() 