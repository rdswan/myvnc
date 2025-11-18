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
import json
import psutil
import glob
from pathlib import Path
from contextlib import contextmanager


class ServerMonitor:
    def __init__(self, server_url, logfile, quiet=False, debug=False, timeout=10, restart_cmd=None, verify_ssl=True, log_history_minutes=2):
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
            log_history_minutes: Number of minutes of log history to capture in diagnostics
        """
        self.server_url = server_url.rstrip('/')
        self.logfile = Path(logfile)
        self.quiet = quiet
        self.debug = debug
        self.timeout = timeout
        self.restart_cmd = restart_cmd
        self.verify_ssl = verify_ssl
        self.log_history_minutes = log_history_minutes
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
            tuple: (is_healthy: bool, message: str, diagnostics_collected: bool)
        """
        try:
            # Try to access the main page
            self.log(f"Checking server health: {self.server_url}", "DEBUG")
            start_time = time.time()
            
            response = requests.get(
                self.server_url,
                timeout=self.timeout,
                verify=self.verify_ssl,  # Verify SSL certificates (can be disabled for self-signed)
                allow_redirects=True
            )
            
            response_time = time.time() - start_time
            
            # Consider 200-399 as healthy (including redirects to login)
            if 200 <= response.status_code < 400:
                self.log(f"Server responded with status {response.status_code} in {response_time:.3f}s", "DEBUG")
                
                # Log slow responses as warnings
                if response_time > 5.0:
                    self.log(f"WARNING: Slow response time: {response_time:.3f}s", "WARNING")
                
                return True, f"Server is healthy (status: {response.status_code}, response time: {response_time:.3f}s)", False
            else:
                self.log(f"Server returned error status: {response.status_code}", "WARNING")
                return False, f"Server returned error status: {response.status_code}", False
                
        except requests.exceptions.SSLError as e:
            self.log(f"SSL certificate error: {e}", "WARNING")
            return False, f"SSL certificate error: {e}", False
            
        except requests.exceptions.Timeout:
            self.log(f"Server request timed out after {self.timeout} seconds", "WARNING")
            return False, f"Server request timed out after {self.timeout} seconds", False
            
        except requests.exceptions.ConnectionError as e:
            self.log(f"Connection error: {e}", "WARNING")
            # Try to get more details about why the connection failed
            self.collect_diagnostics()
            return False, f"Connection error: {e}", True
            
        except requests.exceptions.RequestException as e:
            self.log(f"Request error: {e}", "WARNING")
            return False, f"Request error: {e}", False
            
        except Exception as e:
            self.log(f"Unexpected error: {e}", "ERROR")
            return False, f"Unexpected error: {e}", False
    
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
                    
                    # Check the process command line to verify it's actually a MyVNC process
                    try:
                        with open(f'/proc/{pid}/cmdline', 'r') as f:
                            cmdline = f.read().replace('\x00', ' ')  # Replace null bytes with spaces
                            
                            # Skip monitor_myvnc.py
                            if 'monitor_myvnc.py' in cmdline:
                                self.log(f"Skipping PID {pid} (monitor script)", "DEBUG")
                                continue
                            
                            # Only include if it contains 'myvnc' in the path or command
                            # This ensures we only match MyVNC-related processes
                            if 'myvnc' in cmdline.lower() and ('manage.py' in cmdline or 'main.py' in cmdline):
                                self.log(f"Found MyVNC process {pid}: {cmdline[:100]}", "DEBUG")
                                filtered_pids.append(pid)
                            else:
                                self.log(f"Skipping PID {pid} (not a MyVNC process): {cmdline[:100]}", "DEBUG")
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
    
    def collect_diagnostics(self):
        """
        Collect diagnostic information when the server is unresponsive
        """
        self.log("=" * 80, "INFO")
        self.log("COLLECTING DIAGNOSTICS", "INFO")
        self.log("=" * 80, "INFO")
        
        # Find server processes
        pids = self.find_server_process()
        
        if not pids:
            self.log("No server processes found", "INFO")
            self.check_port_status()
            return
        
        # Get detailed process information
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                self.log(f"Process {pid} details:", "INFO")
                self.log(f"  Status: {proc.status()}", "INFO")
                self.log(f"  CPU: {proc.cpu_percent(interval=0.1)}%", "INFO")
                self.log(f"  Memory: {proc.memory_info().rss / 1024 / 1024:.2f} MB", "INFO")
                self.log(f"  Threads: {proc.num_threads()}", "INFO")
                self.log(f"  Open files: {len(proc.open_files())}", "INFO")
                self.log(f"  Connections: {len(proc.net_connections())}", "INFO")
                
                # Check if process is zombie or stopped
                if proc.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_STOPPED]:
                    self.log(f"  WARNING: Process is in {proc.status()} state!", "WARNING")
                
                # Get command line
                try:
                    cmdline = ' '.join(proc.cmdline())
                    self.log(f"  Command: {cmdline}", "INFO")
                except:
                    pass
                
                # Check file descriptors
                try:
                    num_fds = proc.num_fds()
                    self.log(f"  File descriptors: {num_fds}", "INFO")
                    if num_fds > 900:
                        self.log(f"  WARNING: High file descriptor count ({num_fds}/1024)", "WARNING")
                except:
                    pass
                
                # Check open connections
                try:
                    connections = proc.net_connections(kind='inet')
                    listening = [c for c in connections if c.status == 'LISTEN']
                    self.log(f"  Listening connections: {len(listening)}", "INFO")
                    for conn in listening[:5]:  # Show first 5
                        self.log(f"    {conn.laddr.ip}:{conn.laddr.port} ({conn.status})", "INFO")
                except:
                    pass
                    
            except psutil.NoSuchProcess:
                self.log(f"Process {pid} no longer exists", "DEBUG")
            except psutil.AccessDenied:
                self.log(f"Access denied when querying process {pid} (insufficient permissions)", "DEBUG")
            except Exception as e:
                self.log(f"Error getting process info for {pid}: {type(e).__name__}: {e}", "DEBUG")
        
        # Check port status
        self.check_port_status()
        
        # Tail server logs
        self.tail_server_logs()
        
        self.log("=" * 80, "INFO")
    
    def check_port_status(self):
        """Check if the server port is open and listening"""
        try:
            # Parse port from URL
            from urllib.parse import urlparse
            parsed = urlparse(self.server_url)
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            host = parsed.hostname or 'localhost'
            
            self.log(f"Checking port status: {host}:{port}", "INFO")
            
            # Try to connect to the port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                self.log(f"Port {port} is open", "INFO")
            else:
                self.log(f"Port {port} is closed or filtered (error code: {result})", "WARNING")
                
        except Exception as e:
            self.log(f"Error checking port status: {e}", "ERROR")
    
    def tail_server_logs(self, lines=50):
        """Tail the server logs to see recent activity"""
        try:
            # Try to find server log files
            log_patterns = [
                "/localdev/myvnc/logs/myvnc_*.log",
                "/mnt/myvnc/logs/myvnc_*.log",
                "/var/log/myvnc*.log"
            ]
            
            log_files = []
            for pattern in log_patterns:
                log_files.extend(glob.glob(pattern))
            
            if not log_files:
                self.log("No server log files found", "INFO")
                return
            
            # Get the most recent log file
            log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            recent_log = log_files[0]
            
            # Calculate cutoff time for log filtering
            cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=self.log_history_minutes)
            
            self.log(f"Recent server log ({recent_log}) - last {self.log_history_minutes} minute(s):", "INFO")
            self.log(f"Current time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "DEBUG")
            self.log(f"Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}", "DEBUG")
            self.log(f"Capturing logs from {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} onwards", "DEBUG")
            
            # Read and filter lines by timestamp
            recent_lines = []
            with open(recent_log, 'r') as f:
                for line in f:
                    # Try to parse timestamp from log line
                    # Expected formats:
                    #   1. 2025-11-17 12:28:45,123 - myvnc - INFO - ...
                    #   2. [2025-11-17 12:28:45] [INFO] ...
                    try:
                        log_time = None
                        
                        # Try format 1: YYYY-MM-DD HH:MM:SS,milliseconds - ...
                        if ' - ' in line:
                            timestamp_str = line.split(' - ')[0].split(',')[0].strip()
                            try:
                                log_time = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                pass
                        
                        # Try format 2: [YYYY-MM-DD HH:MM:SS] [LEVEL] ...
                        if log_time is None and line.startswith('['):
                            try:
                                timestamp_str = line.split(']')[0].strip('[')
                                log_time = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            except (ValueError, IndexError):
                                pass
                        
                        # If we successfully parsed a timestamp, check if it's recent
                        if log_time is not None:
                            # Debug: Log first few parsed timestamps
                            if len(recent_lines) < 3:
                                self.log(f"Parsed timestamp: {log_time.strftime('%Y-%m-%d %H:%M:%S')} (cutoff: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}, match: {log_time >= cutoff_time})", "DEBUG")
                            
                            if log_time >= cutoff_time:
                                recent_lines.append(line)
                        else:
                            # If we can't parse the timestamp, include the line anyway
                            # (it might be a continuation of a previous line)
                            if recent_lines:  # Only add if we've already started collecting
                                recent_lines.append(line)
                    except Exception:
                        # If anything goes wrong, include the line if we've started collecting
                        if recent_lines:
                            recent_lines.append(line)
            
            if recent_lines:
                self.log(f"Found {len(recent_lines)} log lines from the past {self.log_history_minutes} minute(s)", "INFO")
                # Show all recent lines (or limit to reasonable max)
                max_lines = 200  # Prevent overwhelming output
                display_lines = recent_lines[-max_lines:] if len(recent_lines) > max_lines else recent_lines
                
                if len(recent_lines) > max_lines:
                    self.log(f"(Showing last {max_lines} of {len(recent_lines)} lines)", "INFO")
                
                for line in display_lines:
                    self.log(f"  {line.rstrip()}", "INFO")
            else:
                self.log(f"No log entries found in the past {self.log_history_minutes} minute(s)", "INFO")
                    
        except Exception as e:
            self.log(f"Error tailing server logs: {e}", "ERROR")
    
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
            # Start server using the restart command
            # The manage.py restart command is designed to exit after starting the server
            with open(os.devnull, 'r') as devnull:
                process = subprocess.Popen(
                    self.restart_cmd,
                    shell=True,
                    stdin=devnull,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True  # Detach from parent process
                )
            
            # Wait for the restart command to complete
            stdout, stderr = process.communicate()
            
            # Check the exit code - 0 means success
            if process.returncode == 0:
                self.log(f"Server restart command completed successfully (exit code: 0)", "INFO")
                if stdout:
                    self.log(f"STDOUT: {stdout.decode()}", "INFO")
                return True
            else:
                self.log(f"Server restart command failed (exit code: {process.returncode})", "ERROR")
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
                is_healthy, message, _ = self.check_server_health()
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
    
    def run(self, diagnostics_only=False):
        """
        Main monitoring loop - check health and restart if needed
        
        Args:
            diagnostics_only: If True, only collect diagnostics without restarting
        
        Returns:
            int: Exit code (0 = success, 1 = error)
        """
        lock_path = self.logfile.parent / f".{self.logfile.stem}.lock"
        
        try:
            with self.acquire_lock(lock_path):
                # If diagnostics-only mode, just collect diagnostics
                if diagnostics_only:
                    self.log(f"Collecting diagnostics for {self.server_url}", "INFO")
                    self.collect_diagnostics()
                    return 0
                
                self.log(f"Starting health check for {self.server_url}", "INFO")
                
                # Check if server is healthy
                is_healthy, message, diagnostics_collected = self.check_server_health()
                
                if is_healthy:
                    self.log(f"✓ {message}", "INFO")
                    return 0
                else:
                    self.log(f"✗ Server is unresponsive: {message}", "ERROR")
                    
                    # Collect diagnostics before attempting restart (if not already collected)
                    if not diagnostics_collected:
                        self.log("Collecting diagnostics before restart...", "INFO")
                        self.collect_diagnostics()
                    else:
                        self.log("Diagnostics already collected during health check", "DEBUG")
                    
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
    
    parser.add_argument(
        '--collect-diagnostics',
        action='store_true',
        help='Collect detailed diagnostics without restarting the server'
    )
    
    parser.add_argument(
        '--log-history-minutes',
        type=int,
        default=2,
        help='Number of minutes of log history to capture in diagnostics (default: 2)'
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
        verify_ssl=not args.no_verify_ssl,  # Invert the flag
        log_history_minutes=args.log_history_minutes
    )
    
    # Run monitoring check
    exit_code = monitor.run(diagnostics_only=args.collect_diagnostics)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

