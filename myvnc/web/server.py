#!/usr/bin/env python3
"""
Simple CGI web server for the VNC management application
"""

import http.server
import cgi
import json
import os
import sys
import argparse
import subprocess
from pathlib import Path
import time
import urllib.parse
import platform
import http.cookies
import traceback
from urllib.parse import parse_qs, urlparse, quote
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
import socket

# Add parent directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from myvnc.utils.auth_manager import AuthManager
from myvnc.utils.lsf_manager import LSFManager
from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.vnc_manager import VNCManager

class VNCRequestHandler(http.server.CGIHTTPRequestHandler):
    """Handler for VNC manager CGI requests"""
    
    def __init__(self, *args, **kwargs):
        self.config_manager = ConfigManager()
        self.lsf_manager = LSFManager()
        self.auth_manager = AuthManager()
        self.vnc_manager = VNCManager()
        self.directory = os.path.join(os.path.dirname(__file__), "static")
        
        # Load server configuration
        self.server_config = load_server_config()
        # Get authentication setting
        self.authentication_enabled = self.server_config.get("authentication", "")
        
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        # Parse URL path
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Only check authentication if it's enabled
        if self.authentication_enabled and self.authentication_enabled.lower() == "entra":
            # Check authentication for all paths except login page and assets
            if not path.startswith("/login") and not path.startswith("/auth/") and not self._is_public_asset(path):
                is_authenticated, _ = self.check_auth()
                if not is_authenticated:
                    # Redirect to login page
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
        
        # Special case: redirect /login to / if authentication is disabled
        if path == "/login" and (not self.authentication_enabled or self.authentication_enabled.lower() != "entra"):
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
            
        # Handle specific paths
        if path == "/":
            self.serve_file("index.html")
        elif path == "/login" and self.authentication_enabled and self.authentication_enabled.lower() == "entra":
            self.serve_file("login.html")
        elif path == "/session" or path == "/api/auth/session":
            self.handle_session()
        elif path == "/api/vnc/sessions" or path == "/api/vnc/list":
            self.handle_vnc_sessions()
        elif path == "/api/lsf/config" or path == "/api/config/lsf":
            self.handle_lsf_config()
        elif path == "/api/server/config" or path == "/api/config/server":
            self.handle_server_config()
        elif path == "/api/config/vnc":
            self.handle_vnc_config()
        elif path == "/api/debug":
            self.handle_debug()
        elif path == "/api/debug/commands":
            self.handle_debug_commands()
        elif path == "/api/debug/environment":
            self.handle_debug_environment()
        elif path == "/auth/entra" and self.authentication_enabled and self.authentication_enabled.lower() == "entra":
            self.handle_auth_entra()
        elif path == "/auth/callback" and self.authentication_enabled and self.authentication_enabled.lower() == "entra":
            self.handle_auth_callback()
        else:
            # Try to serve static file
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests"""
        # Parse URL path
        path = urlparse(self.path).path
        
        # Only check authentication if it's enabled
        if self.authentication_enabled and self.authentication_enabled.lower() == "entra":
            # Allow login without authentication
            if path == "/api/auth/login" or path == "/api/login":
                self.handle_login()
                return
            
            # Check authentication for all other paths
            if not path.startswith("/auth/"):
                is_authenticated, _ = self.check_auth()
                if not is_authenticated:
                    self.send_json_response({
                        "success": False,
                        "message": "Authentication required"
                    }, 401)
                    return
            
            # Handle specific authentication paths
            if path == "/api/logout" or path == "/api/auth/logout":
                self.handle_logout()
                return
        
        # Handle generic paths (always accessible)
        if path == "/api/vnc/start" or path == "/api/vnc/create":
            self.handle_vnc_start()
        elif path.startswith("/api/vnc/stop") or path.startswith("/api/vnc/kill"):
            self.handle_vnc_stop()
        elif path == "/api/vnc/copy":
            self.handle_vnc_copy()
        else:
            self.send_response(404)
            self.end_headers()
    
    def serve_file(self, filename):
        """Serve a file from the static directory"""
        try:
            with open(os.path.join(self.directory, filename), 'rb') as f:
                content = f.read()
                
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            print(f"Error serving file {filename}: {str(e)}", file=sys.stderr)
            self.send_error(500)
    
    def check_auth(self):
        """Check if user is authenticated"""
        session_id = self.get_session_cookie()
        if not session_id:
            return False, None
        
        success, message, session = self.auth_manager.validate_session(session_id)
        if not success:
            return False, None
        
        return True, session
    
    def get_session_cookie(self):
        """Get session cookie from request"""
        cookies = {}
        if "Cookie" in self.headers:
            for cookie in self.headers["Cookie"].split(";"):
                try:
                    name, value = cookie.strip().split("=", 1)
                    cookies[name] = value
                except ValueError:
                    pass
        return cookies.get("session_id")
    
    def handle_login(self):
        """Handle login requests"""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(post_data)
            
            # Extract username and password
            username = data.get("username", "")
            password = data.get("password", "")
            
            # Authenticate user
            success, message, session_id = self.auth_manager.authenticate(username, password)
            
            if success:
                # Set session cookie
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age={self.auth_manager.session_expiry}")
                self.end_headers()
                
                # Send success response
                self.wfile.write(json.dumps({
                    "success": True,
                    "message": message
                }).encode())
            else:
                # Send error response
                self.send_json_response({
                    "success": False,
                    "message": message
                }, 401)
                
        except Exception as e:
            # Send error response for any exceptions
            self.send_json_response({
                "success": False,
                "message": f"Login error: {str(e)}"
            }, 500)
    
    def handle_logout(self):
        """Handle logout requests"""
        try:
            # Get session ID from cookie
            session_id = self.get_session_cookie()
            
            if session_id:
                # Logout user
                success, message = self.auth_manager.logout(session_id)
                
                # Send response
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "session_id=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
                self.end_headers()
                
                self.wfile.write(json.dumps({
                    "success": success,
                    "message": message
                }).encode())
            else:
                # No session to logout
                self.send_json_response({
                    "success": True,
                    "message": "No active session"
                })
                
        except Exception as e:
            # Send error response for any exceptions
            self.send_json_response({
                "success": False,
                "message": f"Logout error: {str(e)}"
            }, 500)
    
    def handle_session(self):
        """Handle session validation requests"""
        try:
            # If authentication is disabled, return as authenticated with a generic user
            if not self.authentication_enabled or self.authentication_enabled.lower() != "entra":
                self.send_json_response({
                    "authenticated": True,
                    "username": "anonymous",
                    "display_name": "Anonymous User",
                    "email": "",
                    "groups": []
                })
                return
                
            # Check if user is authenticated
            is_authenticated, session = self.check_auth()
            
            if is_authenticated:
                # Send user data
                self.send_json_response({
                    "authenticated": True,
                    "username": session.get("username", ""),
                    "display_name": session.get("display_name", ""),
                    "email": session.get("email", ""),
                    "groups": session.get("groups", [])
                })
            else:
                # Send unauthenticated response
                self.send_json_response({
                    "authenticated": False
                }, 401)
                
        except Exception as e:
            # Send error response for any exceptions
            self.send_json_response({
                "authenticated": False,
                "message": f"Session error: {str(e)}"
            }, 500)
    
    def handle_auth_entra(self):
        """Handle Microsoft Entra ID authentication initiation"""
        try:
            # Get authentication URL from auth manager
            auth_url = self.auth_manager.get_auth_url()
            
            if auth_url:
                # Redirect to Microsoft authentication page
                self.send_response(302)
                self.send_header("Location", auth_url)
                self.end_headers()
            else:
                # Entra ID authentication not configured
                self.send_response(500)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"Microsoft Entra ID authentication is not configured")
                
        except Exception as e:
            # Send error response for any exceptions
            self.send_response(500)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"Authentication error: {str(e)}".encode())
    
    def handle_auth_callback(self):
        """Handle Microsoft Entra ID authentication callback"""
        try:
            # Parse query parameters
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # Get authorization code
            code = query_params.get("code", [""])[0]
            
            if code:
                # Process authorization code
                success, message, session_id = self.auth_manager.handle_auth_code(code)
                
                if success:
                    # Set session cookie and redirect to home page
                    self.send_response(302)
                    self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age={self.auth_manager.session_expiry}")
                    self.send_header("Location", "/")
                    self.end_headers()
                else:
                    # Authentication failed
                    self.send_response(401)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"Authentication failed: {message}".encode())
            else:
                # No authorization code provided
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"No authorization code provided")
                
        except Exception as e:
            # Send error response for any exceptions
            self.send_response(500)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"Authentication callback error: {str(e)}".encode())
    
    def _is_public_asset(self, path):
        """Check if a path is a public asset that doesn't require authentication"""
        public_paths = [
            "/css/", 
            "/js/", 
            "/img/", 
            "/favicon.ico",
            "/js/auth.js"  # Allow auth.js to be loaded without authentication
        ]
        return any(path.startswith(prefix) for prefix in public_paths)

    def handle_vnc_sessions(self):
        """Handle VNC sessions request"""
        try:
            jobs = self.lsf_manager.get_active_vnc_jobs()
            
            # Add connection details including port to each job
            for job in jobs:
                try:
                    if 'job_id' in job:
                        # Add default resource values if not present
                        if 'num_cores' not in job:
                            job['num_cores'] = 2  # Default value
                        if 'memory_gb' not in job:
                            job['memory_gb'] = 16  # Default value
                        
                        # Get connection details
                        conn_details = self.lsf_manager.get_vnc_connection_details(job['job_id'])
                        if conn_details:
                            if 'port' in conn_details:
                                job['port'] = conn_details['port']
                            if 'display' in conn_details:
                                job['display'] = conn_details['display']
                except Exception as e:
                    print(f"Error getting connection details for job {job.get('job_id', 'unknown')}: {str(e)}", file=sys.stderr)
            
            self.send_json_response(jobs)
        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_lsf_config(self):
        """Handle LSF configuration request"""
        try:
            config = {
                'defaults': self.config_manager.get_lsf_defaults(),
                'queues': self.config_manager.get_available_queues(),
                'memory_options': self.config_manager.get_memory_options(),
                'core_options': self.config_manager.get_core_options(),
                'sites': self.config_manager.get_available_sites()
            }
            self.send_json_response(config)
        except Exception as e:
            self.send_error_response(str(e))
            
    def handle_server_config(self):
        """Handle server configuration request"""
        try:
            # Return the server configuration (excluding sensitive information)
            server_config = load_server_config()
            # Remove any sensitive fields if needed
            self.send_json_response(server_config)
        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_debug_commands(self):
        """Handle /debug/commands endpoint to display command history"""
        try:
            # Get command history from the LSF manager
            command_history = self.lsf_manager.command_history
            
            # Format command history for better display
            formatted_history = []
            for cmd in command_history:
                formatted_cmd = {
                    "command": cmd.get("command", ""),
                    "success": cmd.get("success", False),
                    "timestamp": cmd.get("timestamp", ""),
                    "stdout": cmd.get("stdout", "").strip(),
                    "stderr": cmd.get("stderr", "").strip()
                }
                formatted_history.append(formatted_cmd)
            
            # Send response
            self.send_json_response({
                "success": True,
                "command_history": formatted_history
            })
        except Exception as e:
            print(f"Error handling debug commands: {str(e)}", file=sys.stderr)
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": f"Error: {str(e)}"
            })
            
    def handle_debug_environment(self):
        """Handle /debug/environment endpoint to display environment information"""
        try:
            # Get environment info
            env_info = {
                "Python Version": platform.python_version(),
                "Platform": platform.platform(),
                "User": os.environ.get("USER", "Unknown"),
                "Hostname": platform.node(),
                "LSB_JOBID": os.environ.get("LSB_JOBID", "Not in LSF environment"),
                "LSF_ENVDIR": os.environ.get("LSF_ENVDIR", "Not set")
            }
            
            # Include configs
            config_info = {
                "vnc_config": self.config_manager.vnc_config,
                "lsf_config": self.config_manager.lsf_config
            }
            
            # Send response
            self.send_json_response({
                "success": True,
                "environment": env_info,
                "config": config_info
            })
        except Exception as e:
            print(f"Error handling debug environment: {str(e)}", file=sys.stderr)
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": f"Error: {str(e)}"
            })
    
    def handle_debug(self):
        """Handle /debug/* requests"""
        path_parts = self.path.strip('/').split('/')
        if len(path_parts) < 2:
            self.send_error(404)
            return
        
        debug_command = path_parts[1]
        
        if debug_command == 'commands':
            self.handle_debug_commands()
        elif debug_command == 'environment':
            self.handle_debug_environment()
        else:
            self.send_error(404)

    def send_json_response(self, data, status=200):
        """Send JSON response to client"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_error_response(self, message, status_code=500):
        """Send an error response"""
        # Ensure message is a string, not bytes
        if isinstance(message, bytes):
            message = message.decode('utf-8')
        elif not isinstance(message, str):
            message = str(message)
        
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        # Ensure we're sending a string that can be encoded to bytes
        error_json = json.dumps({'error': message})
        self.wfile.write(error_json.encode('utf-8'))

    def handle_vnc_config(self):
        """Handle VNC configuration request"""
        try:
            # Get VNC configuration
            config = {
                "window_managers": self.config_manager.get_available_window_managers(),
                "resolutions": self.config_manager.get_available_resolutions(),
                "defaults": self.config_manager.get_vnc_defaults(),
                "sites": self.config_manager.get_available_sites()
            }
            self.send_json_response(config)
        except Exception as e:
            self.send_error_response(str(e))

    def handle_vnc_start(self):
        """Handle VNC start request"""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            print(f"Received raw post data: {post_data}")
            
            data = json.loads(post_data)
            print(f"Parsed JSON data: {data}")
            
            # Extract VNC settings
            vnc_settings = {
                "resolution": data.get("resolution", "1920x1080"),
                "window_manager": data.get("window_manager", "gnome"),
                "color_depth": 24,  # Default color depth
                "site": data.get("site", "Austin"),
                "vncserver_path": "/usr/bin/vncserver",
                "name": data.get("name", "myVNC")
            }
            
            # Extract LSF settings
            lsf_settings = {
                "queue": data.get("queue", "interactive"),
                "num_cores": int(data.get("num_cores", 1)),
                "memory_gb": int(data.get("memory_gb", 16)),
                "job_name": "myvnc_vncserver"
            }
            
            print(f"Submitting VNC job with config: {vnc_settings}")
            print(f"Using LSF settings: {lsf_settings}")
            
            # Submit VNC job
            job_id = self.lsf_manager.submit_vnc_job(vnc_settings, lsf_settings)
            
            # Return result - job_id is a string, not a dictionary
            self.send_json_response({
                "success": True,
                "message": "VNC session created successfully",
                "job_id": job_id,
                "status": "pending"
            })
        except Exception as e:
            error_msg = f"Error creating VNC session: {str(e)}"
            print(error_msg, file=sys.stderr)
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": error_msg
            }, 500)
    
    def handle_vnc_stop(self):
        """Handle VNC stop request"""
        try:
            # Parse path for job ID
            job_id = None
            path = self.path.strip("/").split("/")
            if len(path) >= 3:
                job_id = path[-1]  # Last part of the path should be the job ID
            
            if not job_id:
                # If job ID is not in the path, try to read it from the request body
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length).decode("utf-8")
                    data = json.loads(post_data)
                    job_id = data.get("job_id")
            
            if not job_id:
                raise ValueError("No job ID provided")
            
            # Kill VNC job using the correct method name
            result = self.lsf_manager.kill_vnc_job(job_id)
            
            # Return result
            self.send_json_response({
                "success": result,
                "message": "VNC session stopped successfully" if result else "Failed to stop VNC session",
                "job_id": job_id
            })
        except Exception as e:
            error_msg = f"Error stopping VNC session: {str(e)}"
            print(error_msg, file=sys.stderr)
            self.send_json_response({
                "success": False,
                "message": error_msg
            }, 500)
    
    def handle_vnc_copy(self):
        """Handle VNC copy request"""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(post_data)
            
            # Extract session ID to copy
            session_id = data.get("session_id")
            
            if not session_id:
                raise ValueError("No session ID provided")
            
            # Get session details
            active_sessions = self.lsf_manager.get_active_vnc_jobs()
            session_to_copy = None
            
            for session in active_sessions:
                if str(session.get("job_id")) == str(session_id):
                    session_to_copy = session
                    break
            
            if not session_to_copy:
                raise ValueError(f"Session with ID {session_id} not found")
            
            # Extract and prepare settings for new session
            vnc_settings = {
                "resolution": session_to_copy.get("resolution", "1920x1080"),
                "window_manager": session_to_copy.get("window_manager", "gnome"),
                "color_depth": 24,
                "site": session_to_copy.get("site", "Austin"),
                "vncserver_path": "/usr/bin/vncserver",
                "name": f"Copy of {session_to_copy.get('name', 'myVNC')}"
            }
            
            lsf_settings = {
                "queue": session_to_copy.get("queue", "interactive"),
                "num_cores": int(session_to_copy.get("num_cores", 1)),
                "memory_gb": int(session_to_copy.get("memory_gb", 16)),
                "job_name": "myvnc_vncserver"
            }
            
            # Submit new VNC job
            result = self.lsf_manager.submit_vnc_job(vnc_settings, lsf_settings)
            
            # Return result
            self.send_json_response({
                "success": True,
                "message": "VNC session copied successfully",
                "job_id": result.get("job_id", "unknown"),
                "status": result.get("status", "pending")
            })
        except Exception as e:
            error_msg = f"Error copying VNC session: {str(e)}"
            print(error_msg, file=sys.stderr)
            self.send_json_response({
                "success": False,
                "message": error_msg
            }, 500)

def load_server_config():
    """Load server configuration from JSON file"""
    config_path = Path(__file__).parent.parent.parent / "config" / "server_config.json"
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Server configuration file not found at {config_path}")
        return {
            "host": "localhost",
            "port": 8000,
            "debug": False,
            "max_connections": 5,
            "timeout": 30
        }
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in server configuration file")
        return {
            "host": "localhost",
            "port": 8000,
            "debug": False,
            "max_connections": 5,
            "timeout": 30
        }

def load_lsf_config():
    """Load LSF configuration from JSON file"""
    config_path = Path(__file__).parent.parent.parent / "config" / "lsf_config.json"
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: LSF configuration file not found at {config_path}")
        return {}
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in LSF configuration file")
        return {}

def source_lsf_environment():
    """Source the LSF environment file"""
    lsf_config = load_lsf_config()
    env_file = lsf_config.get("env_file")
    
    if not env_file or not os.path.exists(env_file):
        print(f"Warning: LSF environment file not found at {env_file}")
        return False
    
    try:
        # Source the environment file and capture the environment variables
        command = f"source {env_file} && env"
        proc = subprocess.Popen(['/bin/bash', '-c', command], stdout=subprocess.PIPE)
        for line in proc.stdout:
            # Fix for Python 3.6: Decode bytes to string
            line = line.decode('utf-8').strip()
            if line and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
        proc.communicate()  # Ensure process completes
        print(f"Successfully sourced LSF environment from {env_file}")
        return True
    except Exception as e:
        print(f"Error sourcing LSF environment: {str(e)}")
        return False

def run_server(host=None, port=None, directory=None, config=None):
    """Run the web server"""
    # Source LSF environment
    source_lsf_environment()
    
    # Load configuration if not provided
    if config is None:
        config = load_server_config()
    
    # Override with command line arguments if provided
    host = host or config.get("host", "localhost")
    port = port or config.get("port", 8000)
    
    if directory is None:
        # Use the web directory
        directory = Path(__file__).parent / 'static'
    
    # Ensure data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Set serving directory
    os.chdir(directory)
    
    # Check if the address and port are available
    try:
        # Create a test socket to check availability
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, port))
        sock.close()
    except OSError as e:
        if e.errno == 99:  # Cannot assign requested address
            print(f"Error: Cannot bind to address {host}:{port} - Address not available")
            print(f"       Verify that the host address is correct and exists on this machine")
            return
        elif e.errno == 98:  # Address already in use
            print(f"Error: Cannot bind to address {host}:{port} - Port is already in use")
            print(f"       Check if another instance of the server is already running")
            return
        else:
            print(f"Error: Cannot bind to address {host}:{port} - {e}")
            return
    
    # Create server
    server_address = (host, port)
    try:
        httpd = http.server.HTTPServer(server_address, VNCRequestHandler)
        
        # Set timeout if specified in config
        if "timeout" in config:
            httpd.timeout = config["timeout"]
        
        print(f"Starting server on http://{host}:{port}")
        if config.get("debug", False):
            print(f"Debug mode: ON")
            print(f"Config: {config}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server stopped")
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        return

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="MyVNC Web Server")
    parser.add_argument('--host', help='Host to bind to')
    parser.add_argument('--port', type=int, help='Port to bind to')
    parser.add_argument('--config', help='Path to server configuration file')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    
    if args.config:
        # Custom config path specified
        config_path = Path(args.config)
        print(f"Using custom config file: {config_path}")
        # Not implemented here, but you could load this config instead
    
    run_server(host=args.host, port=args.port) 