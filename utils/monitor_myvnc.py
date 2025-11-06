#!/usr/bin/env python3
"""
MyVNC Server Monitor
Monitors MyVNC server health and restarts it if unresponsive.
Designed to run from cron with semaphore locking to prevent overlapping executions.
"""

import sys
import os
import argparse
import time
import socket
import fcntl
import signal
import subprocess
import datetime
import requests
import urllib3
from pathlib import Path
from contextlib import contextmanager


class ServerMonitor:
    def __init__(self, server_url, logfile, quiet=False, debug=False, timeout=10, restart_cmd=None, verify_ssl=True):
        """
        Initialize the server monitor
        
        Args:
            server_url: URL to check (e.g., https://myvnc-yyz.local.tenstorrent.com)
            logfile: Path to log file
            quiet: If True, suppress stdout/stderr (only log to file)
            debug: If True, show DEBUG level messages
            timeout: HTTP request timeout in seconds
            restart_cmd: Command to restart the server
            verify_ssl: If True, verify SSL certificates (default: True)
        """
        self.server_url = server_url.rstrip('/')
        self.logfile = Path(logfile)
        self.quiet = quiet
        self.debug = debug
        self.timeout = timeout
        self.restart_cmd = restart_cmd
        self.verify_ssl = verify_ssl
        self.lock_file = None
        
        # Disable SSL warnings if verification is disabled
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Ensure log directory exists
        self.logfile.parent.mkdir(parents=True, exist_ok=True)
        
    def log(self, message, level="INFO"):
        """Log a message to file and optionally to stdout"""
        # Skip DEBUG messages entirely unless debug mode is enabled
        if level == "DEBUG" and not self.debug:
            return
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}\n"
        
        # Write to log file
        with open(self.logfile, 'a') as f:
            f.write(log_line)
        
        # Write to stdout/stderr unless in quiet mode
        if not self.quiet:
            if level in ["ERROR", "CRITICAL"]:
                sys.stderr.write(log_line)
                sys.stderr.flush()
            else:
                sys.stdout.write(log_line)
                sys.stdout.flush()
    
    @contextmanager
    def acquire_lock(self, lock_path):
        """
        Acquire an exclusive file lock to prevent concurrent executions
        
        Args:
            lock_path: Path to the lock file
            
        Raises:
            BlockingIOError: If lock cannot be acquired (another instance is running)
        """
        lock_file_path = Path(lock_path)
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        lock_fd = None
        try:
            # Open/create lock file
            lock_fd = open(lock_file_path, 'w')
            
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write PID to lock file
            lock_fd.write(f"{os.getpid()}\n")
            lock_fd.flush()
            
            self.log(f"Lock acquired (PID: {os.getpid()})", "DEBUG")
            
            yield lock_fd
            
        except BlockingIOError:
            # Another instance is already running
            if lock_fd:
                lock_fd.close()
            raise BlockingIOError("Another instance is already running")
            
        finally:
            # Release lock and close file
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                    self.log(f"Lock released (PID: {os.getpid()})", "DEBUG")
                except Exception as e:
                    self.log(f"Error releasing lock: {e}", "ERROR")
    
    def check_server_health(self):
        """
        Check if the server is responding to HTTP requests
        
        Returns:
            tuple: (is_healthy: bool, message: str)
        """
        try:
            # Try to access the main page
            self.log(f"Checking server health: {self.server_url}", "DEBUG")
            
            response = requests.get(
                self.server_url,
                timeout=self.timeout,
                verify=self.verify_ssl,  # Verify SSL certificates (can be disabled for self-signed)
                allow_redirects=True
            )
            
            # Consider 200-399 as healthy (including redirects to login)
            if 200 <= response.status_code < 400:
                self.log(f"Server responded with status {response.status_code}", "DEBUG")
                return True, f"Server is healthy (status: {response.status_code})"
            else:
                return False, f"Server returned error status: {response.status_code}"
                
        except requests.exceptions.SSLError as e:
            return False, f"SSL certificate error: {e}"
            
        except requests.exceptions.Timeout:
            return False, f"Server request timed out after {self.timeout} seconds"
            
        except requests.exceptions.ConnectionError as e:
            return False, f"Connection error: {e}"
            
        except requests.exceptions.RequestException as e:
            return False, f"Request error: {e}"
            
        except Exception as e:
            return False, f"Unexpected error: {e}"
    
    def find_server_process(self):
        """
        Find the MyVNC server process (excluding the monitor itself)
        
        Returns:
            list: List of PIDs matching the server process, or empty list
        """
        try:
            my_pid = os.getpid()
            
            # Look for manage.py or main.py processes, but exclude monitor_myvnc.py
            result = subprocess.run(
                ['pgrep', '-f', 'manage.py|main.py'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                all_pids = [int(pid) for pid in result.stdout.strip().split('\n')]
                
                # Filter out our own PID and check each process
                filtered_pids = []
                for pid in all_pids:
                    if pid == my_pid:
                        self.log(f"Skipping PID {pid} (monitor itself)", "DEBUG")
                        continue
                    
                    # Check the process command line to exclude monitor_myvnc.py
                    try:
                        with open(f'/proc/{pid}/cmdline', 'r') as f:
                            cmdline = f.read()
                            if 'monitor_myvnc.py' in cmdline:
                                self.log(f"Skipping PID {pid} (monitor script)", "DEBUG")
                                continue
                            filtered_pids.append(pid)
                    except (FileNotFoundError, PermissionError):
                        # Process may have terminated or no permission to read
                        pass
                
                if filtered_pids:
                    self.log(f"Found {len(filtered_pids)} MyVNC server process(es): {filtered_pids}", "DEBUG")
                else:
                    self.log("No MyVNC server process found (after filtering)", "DEBUG")
                return filtered_pids
            else:
                self.log("No MyVNC server process found", "DEBUG")
                return []
                
        except Exception as e:
            self.log(f"Error finding server process: {e}", "ERROR")
            return []
    
    def stop_server(self, pids):
        """
        Stop the server by sending SIGTERM to the process(es)
        
        Args:
            pids: List of process IDs to stop
            
        Returns:
            bool: True if all processes were stopped successfully
        """
        if not pids:
            self.log("No PIDs to stop", "WARNING")
            return True
        
        self.log(f"Stopping server processes: {pids}", "INFO")
        
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                self.log(f"Sent SIGTERM to PID {pid}", "INFO")
            except ProcessLookupError:
                self.log(f"PID {pid} already terminated", "DEBUG")
            except PermissionError:
                self.log(f"Permission denied to kill PID {pid}", "ERROR")
                return False
            except Exception as e:
                self.log(f"Error killing PID {pid}: {e}", "ERROR")
                return False
        
        # Wait for processes to terminate (up to 10 seconds)
        self.log("Waiting for processes to terminate...", "INFO")
        for i in range(10):
            time.sleep(1)
            still_running = []
            for pid in pids:
                try:
                    os.kill(pid, 0)  # Check if process exists
                    still_running.append(pid)
                except ProcessLookupError:
                    pass  # Process terminated
            
            if not still_running:
                self.log("All processes terminated successfully", "INFO")
                return True
            
            if i == 9:
                self.log(f"Processes still running after 10s: {still_running}", "WARNING")
                # Force kill
                for pid in still_running:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        self.log(f"Sent SIGKILL to PID {pid}", "WARNING")
                    except Exception as e:
                        self.log(f"Error force-killing PID {pid}: {e}", "ERROR")
        
        return True
    
    def start_server(self):
        """
        Start the server using the configured restart command
        
        Returns:
            bool: True if server started successfully
        """
        if not self.restart_cmd:
            self.log("No restart command configured", "ERROR")
            return False
        
        self.log(f"Starting server with command: {self.restart_cmd}", "INFO")
        
        try:
            # Start server in background
            # Use nohup to detach from this process
            with open(os.devnull, 'r') as devnull:
                process = subprocess.Popen(
                    self.restart_cmd,
                    shell=True,
                    stdin=devnull,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True  # Detach from parent process
                )
            
            # Give it a moment to start
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                self.log(f"Server started successfully (PID: {process.pid})", "INFO")
                return True
            else:
                stdout, stderr = process.communicate()
                self.log(f"Server failed to start (exit code: {process.returncode})", "ERROR")
                if stdout:
                    self.log(f"STDOUT: {stdout.decode()}", "ERROR")
                if stderr:
                    self.log(f"STDERR: {stderr.decode()}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error starting server: {e}", "ERROR")
            return False
    
    def restart_server(self):
        """
        Restart the server (stop if running, then start)
        
        Returns:
            bool: True if restart was successful
        """
        self.log("=" * 80, "INFO")
        self.log("RESTARTING SERVER", "INFO")
        self.log("=" * 80, "INFO")
        
        # Find and stop existing processes
        pids = self.find_server_process()
        if pids:
            if not self.stop_server(pids):
                self.log("Failed to stop server cleanly", "ERROR")
                return False
        
        # Wait a moment before restarting
        time.sleep(2)
        
        # Start server
        if self.start_server():
            # Wait for server to become responsive
            self.log("Waiting for server to become responsive...", "INFO")
            for i in range(30):  # Try for 30 seconds
                time.sleep(1)
                is_healthy, message = self.check_server_health()
                if is_healthy:
                    self.log(f"Server is now responsive after {i+1} seconds", "INFO")
                    self.log("=" * 80, "INFO")
                    return True
            
            self.log("Server started but did not become responsive within 30 seconds", "ERROR")
            self.log("=" * 80, "INFO")
            return False
        else:
            self.log("Failed to start server", "ERROR")
            self.log("=" * 80, "INFO")
            return False
    
    def run(self):
        """
        Main monitoring loop - check health and restart if needed
        
        Returns:
            int: Exit code (0 = success, 1 = error)
        """
        lock_path = self.logfile.parent / f".{self.logfile.stem}.lock"
        
        try:
            with self.acquire_lock(lock_path):
                self.log(f"Starting health check for {self.server_url}", "INFO")
                
                # Check if server is healthy
                is_healthy, message = self.check_server_health()
                
                if is_healthy:
                    self.log(f"✓ {message}", "INFO")
                    return 0
                else:
                    self.log(f"✗ Server is unresponsive: {message}", "ERROR")
                    
                    # Attempt restart
                    if self.restart_server():
                        self.log("Server restart successful", "INFO")
                        return 0
                    else:
                        self.log("Server restart failed", "CRITICAL")
                        return 1
                        
        except BlockingIOError:
            # Another instance is running - this is fine for cron
            if not self.quiet:
                print("Another monitoring instance is already running, skipping.")
            return 0
            
        except Exception as e:
            self.log(f"Unexpected error in monitoring loop: {e}", "CRITICAL")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="Monitor MyVNC server health and restart if unresponsive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - check server and log to file
  %(prog)s --url https://myvnc-yyz.local.tenstorrent.com \\
           --logfile /var/log/myvnc-monitor.log \\
           --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config"

  # Quiet mode for cron (no stdout/stderr except to log)
  %(prog)s --url https://myvnc-yyz.local.tenstorrent.com \\
           --logfile /var/log/myvnc-monitor.log \\
           --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" \\
           --quiet

  # Custom timeout
  %(prog)s --url https://myvnc-yyz.local.tenstorrent.com \\
           --logfile /var/log/myvnc-monitor.log \\
           --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" \\
           --timeout 15

Cron example (check every minute):
  * * * * * /usr/bin/python3 /path/to/monitor_myvnc.py --url https://myvnc-yyz.local.tenstorrent.com --logfile /var/log/myvnc-monitor.log --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" --quiet
        """
    )
    
    parser.add_argument(
        '--url',
        required=True,
        help='URL of the MyVNC server to monitor (e.g., https://myvnc-yyz.local.tenstorrent.com)'
    )
    
    parser.add_argument(
        '--logfile',
        required=True,
        help='Path to log file (e.g., /var/log/myvnc-monitor.log)'
    )
    
    parser.add_argument(
        '--restart-cmd',
        required=True,
        help='Command to restart the server (e.g., "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config")'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress stdout/stderr (only write to log file)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=10,
        help='HTTP request timeout in seconds (default: 10)'
    )
    
    parser.add_argument(
        '--no-verify-ssl',
        action='store_true',
        help='Disable SSL certificate verification (for self-signed certificates)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Show DEBUG level messages in output'
    )
    
    args = parser.parse_args()
    
    # Create monitor instance
    monitor = ServerMonitor(
        server_url=args.url,
        logfile=args.logfile,
        quiet=args.quiet,
        debug=args.debug,
        timeout=args.timeout,
        restart_cmd=args.restart_cmd,
        verify_ssl=not args.no_verify_ssl  # Invert the flag
    )
    
    # Run monitoring check
    exit_code = monitor.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

