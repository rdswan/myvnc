#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
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
import socket
import logging

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
    
    # Find existing server PID and its log file
    existing_pid = read_pid_file() or find_server_process()
    config = load_server_config()
    
    # If we have a running server, try to use its log file
    if existing_pid and is_server_running(existing_pid):
        log_dir = config.get('logdir', '/tmp')
        server_log_file = os.path.join(log_dir, f'myvnc_{existing_pid}.log')
        
        # If server log file exists, create a handler for it
        if os.path.exists(server_log_file):
            # Create a logger that writes to the server's log file
            logger = logging.getLogger('myvnc')
            logger.setLevel(logging.INFO)
            
            # Clear existing handlers to avoid duplicate logging
            logger.handlers.clear()
            
            # Create formatter for our logs
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            
            # Add console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            # Add file handler for the server's log file
            try:
                file_handler = logging.FileHandler(server_log_file)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                logger.info(f"Manage.py: Writing to server log file: {server_log_file}")
                return logger
            except (PermissionError, IOError) as e:
                # If we can't write to the server log file, log it and continue
                # with a new log file
                print(f"Warning: Cannot write to server log file {server_log_file}: {e}")
                # Continue with setup_logging below
    
    # If no server log file or couldn't write to it, create our own temporary log
    # but don't record it in a way that would make it look like a server log
    try:
        # Create a new logger with a temp file that includes "manage" in the name
        from myvnc.utils.log_manager import setup_logging
        
        # Temporarily modify the process ID to avoid creating a server-named log
        real_pid = os.getpid()
        
        # Override PID with a special value for manage.py
        # This ensures that log files for manage.py-only operations are clearly marked
        os.environ['MYVNC_MANAGE_PID'] = f"manage_{real_pid}"
        
        # Set up logging with this environment variable
        logger = setup_logging(config=config)
        
        # Restore real PID
        del os.environ['MYVNC_MANAGE_PID']
        
        return logger
    except Exception as e:
        # If all else fails, create a basic logger
        logger = logging.getLogger('myvnc')
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        logger.warning(f"Using fallback logger due to error: {e}")
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
    
    # Look for the most direct match first
    log_file = log_path / f'myvnc_{pid}.log'
    
    if log_file.exists():
        return str(log_file)
    
    # If direct match isn't found, try all log files in the directory
    try:
        # Get list of all log files sorted by modification time (newest first)
        log_files = sorted(
            log_path.glob('myvnc_*.log'),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        # First look for a file with the PID in the name
        for file in log_files:
            if f'myvnc_{pid}.log' in file.name:
                return str(file)
        
        # If we have a running server process and didn't find a direct match,
        # just return the newest log file as it's likely the right one
        if is_server_running(pid) and log_files:
            return str(log_files[0])
            
    except Exception as e:
        logger = get_logger()
        if logger:
            logger.error(f"Error searching for log files: {e}")
        else:
            # Fall back to print only if logger is not available
            print(f"Error searching for log files: {e}")
    
    return None

def get_fully_qualified_hostname(host):
    """Get the fully qualified domain name for a host"""
    if host == 'localhost' or host == '127.0.0.1':
        try:
            # Try to get the FQDN using the hostname command
            process = subprocess.run(['hostname', '-f'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False)
            if process.returncode == 0 and process.stdout.strip():
                return process.stdout.strip()
            
            # Fall back to socket.getfqdn()
            fqdn = socket.getfqdn()
            if fqdn != 'localhost' and fqdn != '127.0.0.1':
                return fqdn
        except Exception as e:
            logger = get_logger()
            if logger:
                logger.warning(f"Could not get FQDN: {e}")
    elif host.count('.') == 0:  # If host is a simple hostname without domain
        try:
            # Try to get full domain by running hostname -f command
            process = subprocess.run(['hostname', '-f'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False)
            if process.returncode == 0 and process.stdout.strip():
                return process.stdout.strip()
            
            # Try socket.getfqdn
            fqdn = socket.getfqdn(host)
            if fqdn != host:
                return fqdn
            
            # If hostname command didn't work and socket.getfqdn returned the same,
            # try to detect domain from the current hostname
            current_host = socket.getfqdn()
            if '.' in current_host:
                # Extract domain from current hostname
                domain = '.'.join(current_host.split('.')[1:])
                if domain:
                    return f"{host}.{domain}"
        except Exception as e:
            logger = get_logger()
            if logger:
                logger.warning(f"Could not get FQDN for {host}: {e}")
    
    # Return the original host if no FQDN could be determined
    return host

def start_server():
    """Start the server if it's not already running"""
    logger = setup_logging_for_manage()
    
    # First check for any existing server processes
    running_pid = None
    
    # Check if we have a PID file
    pid_from_file = read_pid_file()
    if pid_from_file and is_server_running(pid_from_file):
        running_pid = pid_from_file
        # Log the warning with proper formatting to make it stand out
        logger.warning(f"")
        logger.warning(f"=== SERVER ALREADY RUNNING ===")
        logger.warning(f"An instance of the server is already running with PID {running_pid}")
    else:
        # If PID file doesn't exist or its PID is not running, 
        # try to find any server process that might be running
        running_pid = find_server_process()
        if running_pid:
            # Log the warning with proper formatting to make it stand out
            logger.warning(f"")
            logger.warning(f"=== SERVER ALREADY RUNNING ===")
            logger.warning(f"An existing server instance was found with PID {running_pid}")
            
            # Update PID file to match the found process
            write_pid_file(running_pid)
    
    if running_pid:
        # Report server URL for existing server
        config = load_server_config()
        host = config.get('host', 'localhost')
        port = config.get('port', '9143')
        
        # Always use fully qualified domain name
        host = get_fully_qualified_hostname(host)
        
        # Check if HTTPS is configured
        ssl_cert = config.get('ssl_cert', '')
        ssl_key = config.get('ssl_key', '')
        ssl_ca_chain = config.get('ssl_ca_chain', '')
        use_https = ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key)
        protocol = "https" if use_https else "http"
        
        url = f"{protocol}://{host}:{port}"
        logger.warning(f"On instance on server URL: {url} is already running!")
        
        # Find the server log file
        server_log_file = find_server_log_file(running_pid)
        if server_log_file:
            logger.warning(f"Existing instance log file: {server_log_file}")
        
        logger.warning(f"No action taken. Use 'manage.py restart' if you need to restart the server.")
        
        # Exit gracefully - don't start a new server
        return running_pid
    
    # If we get here, there's no existing server running, so start a new one
    logger.info(f"No existing server found. Starting MyVNC server")
    
    # Remove any stale PID file if it exists
    if pid_from_file:
        logger.info(f"Removing stale PID file for PID {pid_from_file}")
        if os.path.exists(get_pid_file()):
            os.remove(get_pid_file())
    
    # Get the full path to main.py
    main_script = Path(os.path.dirname(os.path.abspath(__file__))) / "main.py"
    
    # Load config to get host and port
    config = load_server_config()
    
    # Get host and always use FQDN
    host = config.get('host', 'localhost')
    port = config.get('port', '9143')
    
    # Get FQDN to explicitly pass to main.py script
    fqdn_host = get_fully_qualified_hostname(host)
    
    # Explicitly add FQDN to the environment for child process to inherit
    env = os.environ.copy()
    env['MYVNC_FQDN_HOST'] = fqdn_host
    
    # Start the server process and completely detach it
    # Use nohup to ensure the process continues running even after the parent exits
    try:
        # Create the command to run
        cmd = [sys.executable, str(main_script), '--host', fqdn_host]
        
        # Use subprocess.Popen with stdout/stderr redirected to /dev/null 
        # and start in a new session to fully detach from terminal
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env
        )
        
        # Process is now detached, get its PID
        pid = process.pid
        logger.info(f"Server started with PID {pid}")
        write_pid_file(pid)
        
        # Check if HTTPS is configured
        ssl_cert = config.get('ssl_cert', '')
        ssl_key = config.get('ssl_key', '')
        ssl_ca_chain = config.get('ssl_ca_chain', '')
        use_https = ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key)
        protocol = "https" if use_https else "http"
        
        # URL with FQDN
        url = f"{protocol}://{fqdn_host}:{port}"
        
        # Log the URL
        logger.info(f"Server successfully started with PID {pid}")
        logger.info(f"")
        logger.info(f"=== SERVER STARTED SUCCESSFULLY ===")
        logger.info(f"PID: {pid}")
        logger.info(f"Server URL: {url}")
        if use_https:
            logger.info(f"SSL/HTTPS: Enabled")
        
        # Wait a moment for the log file to be created
        time.sleep(0.5)
        server_log_file = find_server_log_file(pid)
        if server_log_file:
            logger.info(f"Log file: {server_log_file}")
        
        return pid
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return None

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
        logger.info(f"Server is not running")
        return
    
    # Check if the process is actually running
    if not is_server_running(pid):
        logger.info(f"Server is not running (PID {pid} not found)")
        os.remove(get_pid_file())
        return
    
    # Send a SIGTERM signal to gracefully stop the server
    logger.info(f"")
    logger.info(f"=== STOPPING SERVER ===")
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
            
        logger.info(f"")
        logger.info(f"=== SERVER STOPPED SUCCESSFULLY ===")
        
    except ProcessLookupError:
        logger.warning(f"Process {pid} not found, removing PID file")
        if os.path.exists(get_pid_file()):
            os.remove(get_pid_file())

def restart_server():
    """Restart the server"""
    logger = setup_logging_for_manage()
    
    logger.info(f"")
    logger.info(f"=== RESTARTING SERVER ===")
    
    # Stop the existing server
    stop_server()
    
    # Give it a moment to shut down completely
    time.sleep(1)
    
    # Start a new server and return its PID
    return start_server()

def server_status():
    """Show the status of the server"""
    # First check if there's a running server
    pid = read_pid_file()
    
    # If we don't have a PID file, try to find the server process
    if pid is None:
        pid = find_server_process()
        if pid:
            write_pid_file(pid)
    
    # Check if the server is actually running
    is_running = pid is not None and is_server_running(pid)
    
    # Now get a logger - try to use the server's log if possible
    logger = setup_logging_for_manage()
    
    # Load server configuration to display
    config = load_server_config()
    
    # Calculate timestamp once, for consistent output
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    
    if not is_running:
        logger.info("Server status: Not running")
        return
    
    # Server is running, get more information
    uptime = get_uptime(pid)
    
    host = config.get('host', 'localhost')
    port = config.get('port', '9143')
    logdir = config.get('logdir', '/tmp')
    
    # Always use FQDN even if config has localhost
    fqdn_host = get_fully_qualified_hostname(host)
    
    # Find the log file for this PID
    server_log_file = find_server_log_file(pid)
    
    # Check if HTTPS is configured
    ssl_cert = config.get('ssl_cert', '')
    ssl_key = config.get('ssl_key', '')
    ssl_ca_chain = config.get('ssl_ca_chain', '')
    use_https = ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key)
    protocol = "https" if use_https else "http"
    
    # Check authentication configuration
    auth_method = config.get('authentication', 'None')
    auth_enabled = auth_method.lower() in ['entra', 'ldap']
    
    # Check if LDAP module is available
    try:
        import ldap3
        ldap_available = True
    except ImportError:
        ldap_available = False
    
    # Check if MSAL (Microsoft Auth) module is available
    try:
        import msal
        msal_available = True
    except ImportError:
        msal_available = False
    
    # Determine actual auth status based on configuration and module availability
    actual_auth_enabled = auth_enabled
    if auth_method.lower() == 'ldap' and not ldap_available:
        actual_auth_enabled = False
    elif auth_method.lower() == 'entra' and not msal_available:
        actual_auth_enabled = False
    
    # Log status information
    logger.info("Server status:")
    logger.info(f"  Status: Running")
    logger.info(f"  PID: {pid}")
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  URL: {protocol}://{fqdn_host}:{port}")
    logger.info(f"  SSL: {'Enabled' if use_https else 'Disabled'}")
    if use_https:
        logger.info(f"  SSL Certificate: {ssl_cert}")
        logger.info(f"  SSL Key: {ssl_key}")
        if ssl_ca_chain and os.path.exists(ssl_ca_chain):
            logger.info(f"  SSL CA Chain: {ssl_ca_chain}")
        elif ssl_ca_chain:
            logger.info(f"  SSL CA Chain: {ssl_ca_chain} (file not found)")
        else:
            logger.info(f"  SSL CA Chain: Not configured")
    logger.info(f"  Authentication: {'Enabled' if actual_auth_enabled else 'Disabled'}")
    if auth_method and auth_method.lower() != 'none':
        logger.info(f"  Auth Method: {auth_method}")
        logger.info(f"  Auth Method Configured: {'Yes' if auth_enabled else 'No'}")
        logger.info(f"  Auth Method Available: {'Yes' if actual_auth_enabled else 'No'}")
        logger.info(f"  Auth Status: {auth_method} ({'Active' if actual_auth_enabled else 'Inactive - Module Missing'})")
        
        # Add details about the auth modules
        if auth_method.lower() == 'ldap':
            logger.info(f"  LDAP Module Available: {'Yes' if ldap_available else 'No'}")
        elif auth_method.lower() == 'entra':
            logger.info(f"  MSAL Module Available: {'Yes' if msal_available else 'No'}")
    
    logger.info(f"  Log directory: {logdir}")
    logger.info(f"  Current log: {server_log_file if server_log_file else 'Unknown'}")
    logger.info(f"  Uptime: {uptime}")

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
