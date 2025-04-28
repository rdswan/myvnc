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
    config = load_server_config()
    logger = setup_logging(config=config)
    return logger

def get_pid_file():
    """Get the path to the PID file"""
    return Path(os.path.dirname(os.path.abspath(__file__))) / "myvnc_server.pid"

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

def start_server():
    """Start the server if it's not already running"""
    logger = setup_logging_for_manage()
    
    # Check if the server is already running
    pid = read_pid_file()
    if pid and is_server_running(pid):
        print(f"Server is already running with PID {pid}")
        logger.info(f"Server is already running with PID {pid}")
        return
    
    # If we have a PID file but the server is not running, clean it up
    if pid:
        print(f"Removing stale PID file for PID {pid}")
        logger.info(f"Removing stale PID file for PID {pid}")
        os.remove(get_pid_file())
    
    # Check if we can find the server process even without a PID file
    pid = find_server_process()
    if pid:
        print(f"Server is already running with PID {pid} (discovered)")
        logger.info(f"Server is already running with PID {pid} (discovered)")
        write_pid_file(pid)
        return
    
    # Start the server
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Starting MyVNC server")
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
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Server started with PID {process.pid}")
        logger.info(f"Server started with PID {process.pid}")
        write_pid_file(process.pid)
    else:
        # Process exited, read the output to see why
        output = process.stdout.read().decode('utf-8')
        print(f"Server failed to start:\n{output}")
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
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Server is not running")
        logger.info("Server is not running")
        return
    
    # Check if the process is actually running
    if not is_server_running(pid):
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Server is not running (PID {pid} not found)")
        logger.info(f"Server is not running (PID {pid} not found)")
        os.remove(get_pid_file())
        return
    
    # Send a SIGTERM signal to gracefully stop the server
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Stopping server with PID {pid}")
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
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - WARNING - Server did not exit gracefully, forcing termination")
            logger.warning(f"Server did not exit gracefully, forcing termination")
            os.kill(pid, signal.SIGKILL)
        
        # Remove the PID file
        if os.path.exists(get_pid_file()):
            os.remove(get_pid_file())
            
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Server stopped")
        logger.info("Server stopped")
        
    except ProcessLookupError:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - WARNING - Process {pid} not found, removing PID file")
        logger.warning(f"Process {pid} not found, removing PID file")
        if os.path.exists(get_pid_file()):
            os.remove(get_pid_file())

def restart_server():
    """Restart the server"""
    logger = setup_logging_for_manage()
    
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Restarting server")
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
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Server status: Not running")
        logger.info("Server status: Not running")
        return
    
    # Server is running, get more information
    uptime = get_uptime(pid)
    
    host = config.get('host', 'localhost')
    port = config.get('port', '9143')
    logdir = config.get('logdir', 'logs')
    
    status_info = {
        'status': 'Running',
        'pid': pid,
        'host': host,
        'port': port,
        'url': f'http://{host}:{port}',
        'logdir': logdir,
        'uptime': uptime
    }
    
    # Current log file
    log_file = get_current_log_file()
    if log_file:
        status_info['current_log'] = str(log_file)
    
    # Print status information
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - myvnc - INFO - Server status:")
    print(f"  Status: Running")
    print(f"  PID: {pid}")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  URL: http://{host}:{port}")
    print(f"  Log directory: {logdir}")
    print(f"  Current log: {log_file if log_file else 'Unknown'}")
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