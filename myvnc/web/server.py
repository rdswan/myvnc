#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
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
import traceback
from pathlib import Path
import time
import urllib.parse
import platform
import http.cookies
from urllib.parse import parse_qs, urlparse, quote
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
import socket
import logging
import ssl

# Add parent directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from myvnc.utils.auth_manager import AuthManager
from myvnc.utils.lsf_manager import LSFManager
from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.vnc_manager import VNCManager
from myvnc.utils.log_manager import setup_logging, get_logger, get_current_log_file

def setup_logger():
    """Set up detailed logging configuration"""
    # Create logger
    logger = logging.getLogger('myvnc')
    logger.setLevel(logging.DEBUG)
    
    # Create console handler with a higher log level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create file handler for detailed logs
    try:
        file_handler = logging.FileHandler('myvnc.log')
        file_handler.setLevel(logging.DEBUG)
    except Exception as e:
        print(f"Warning: Could not create log file: {str(e)}")
        file_handler = None
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add formatter to handlers
    console_handler.setFormatter(formatter)
    if file_handler:
        file_handler.setFormatter(formatter)
    
    # Add handlers to the logger
    logger.addHandler(console_handler)
    if file_handler:
        logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()

def get_fully_qualified_hostname(host):
    """Get the fully qualified domain name for a host"""
    if host == 'localhost' or host == '127.0.0.1' or host == '0.0.0.0':
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
            logger.warning(f"Could not get FQDN for {host}: {e}")
    
    # Return the original host if no FQDN could be determined
    return host

class LoggingHTTPServer(http.server.HTTPServer):
    """HTTP Server that logs all requests"""
    
    def __init__(self, *args, **kwargs):
        self.logger = get_logger()
        super().__init__(*args, **kwargs)
    
    def service_actions(self):
        """Called once per handle_request() cycle to perform any periodic tasks"""
        super().service_actions()
    
    def process_request(self, request, client_address):
        """Log each incoming request"""
        self.logger.debug(f"New connection from {client_address[0]}:{client_address[1]}")
        super().process_request(request, client_address)
    
    def handle_error(self, request, client_address):
        """Log server errors"""
        self.logger.error(f"Error handling request from {client_address[0]}:{client_address[1]}")
        self.logger.error(traceback.format_exc())
        super().handle_error(request, client_address)

class VNCRequestHandler(http.server.CGIHTTPRequestHandler):
    """Handler for VNC manager CGI requests"""
    
    def __init__(self, *args, **kwargs):
        self.config_manager = ConfigManager()
        self.lsf_manager = LSFManager()
        self.auth_manager = AuthManager()
        self.vnc_manager = VNCManager()
        self.directory = os.path.join(os.path.dirname(__file__), "static")
        self.logger = get_logger()
        
        # Load server configuration
        self.server_config = load_server_config()
        # Get authentication setting
        self.authentication_enabled = self.server_config.get("authentication", "")
        
        super().__init__(*args, **kwargs)
    
    def is_auth_enabled(self):
        """Check if authentication is enabled and available"""
        auth_method = self.authentication_enabled.lower() if self.authentication_enabled else ""
        
        # Check if authentication method is configured
        if auth_method not in ["entra", "ldap"]:
            self.logger.debug(f"Authentication disabled: method '{auth_method}' not configured")
            return False
            
        # For LDAP, check if LDAP module is available
        if auth_method == "ldap":
            try:
                import ldap3
                self.logger.debug("LDAP authentication: module available")
                return True
            except ImportError:
                self.logger.warning("LDAP authentication configured but ldap3 module not available")
                return False
        
        # For Entra, check if MSAL module is available
        if auth_method == "entra":
            try:
                import msal
                self.logger.debug("Entra authentication: MSAL module available")
                return True
            except ImportError:
                self.logger.warning("Entra authentication configured but msal module not available")
                return False
                
        # If we get here, the configured authentication method is invalid
        self.logger.warning(f"Unknown authentication method configured: {auth_method}")
        return False
    
    def do_GET(self):
        """Handle GET requests"""
        # Parse URL path
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Log the request
        client_address = self.client_address[0] if hasattr(self, 'client_address') and self.client_address else 'unknown'
        self.logger.info(f"GET request from {client_address}: {path}")
        
        # Check if authentication is enabled and available
        auth_enabled = self.is_auth_enabled()
        
        # Special case: redirect /login to / if authentication is disabled
        if path == "/login" and not auth_enabled:
            self.logger.info(f"Login page requested but authentication is disabled, redirecting to main page")
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        
        # Server config endpoint should always be accessible without authentication
        # This is needed for the login page and for system status checks
        if path == "/api/server/config" or path == "/api/config/server":
            self.logger.info(f"Allowing access to server config without authentication")
            self.handle_server_config()
            return
        
        # Only check authentication if it's enabled
        if auth_enabled:
            # Check authentication for all paths except login page and assets
            if not path.startswith("/login") and not path.startswith("/auth/") and not self._is_public_asset(path):
                is_authenticated, message, _ = self.check_auth()
                if not is_authenticated:
                    # Redirect to login page
                    self.logger.info(f"Unauthenticated request to {path}, redirecting to login")
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
            
        # Handle specific paths
        if path == "/":
            self.serve_file("index.html")
        elif path == "/login" and auth_enabled:
            self.serve_file("login.html")
        elif path == "/session" or path == "/api/auth/session":
            self.handle_session()
        elif path == "/api/vnc/sessions" or path == "/api/vnc/list":
            self.handle_vnc_sessions()
        elif path == "/api/lsf/config" or path == "/api/config/lsf":
            self.handle_lsf_config()
        elif path == "/api/config/vnc":
            self.handle_vnc_config()
        elif path == "/api/debug":
            self.handle_debug()
        elif path == "/api/debug/commands":
            self.handle_debug_commands()
        elif path == "/api/debug/environment":
            self.handle_debug_environment()
        elif path == "/auth/entra" and auth_enabled and self.authentication_enabled.lower() == "entra":
            self.handle_auth_entra()
        elif path == "/auth/callback" and auth_enabled and self.authentication_enabled.lower() == "entra":
            self.handle_auth_callback()
        elif path == "/api/auth/ldap/diagnose" and auth_enabled and self.authentication_enabled.lower() == "ldap":
            self.ldap_diagnostics()
        else:
            # Try to serve static file
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests"""
        # Parse URL path
        path = urlparse(self.path).path
        
        # Log the request
        client_address = self.client_address[0] if hasattr(self, 'client_address') and self.client_address else 'unknown'
        self.logger.info(f"POST request from {client_address}: {path}")
        
        # Check if authentication is enabled and available
        auth_enabled = self.is_auth_enabled()
        
        # Only check authentication if it's enabled
        if auth_enabled:
            # Allow login without authentication
            if path == "/api/auth/login" or path == "/api/login":
                self.handle_login()
                return
            
            # Check authentication for all other paths
            if not path.startswith("/auth/"):
                is_authenticated, message, _ = self.check_auth()
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
            
            self.logger.info(f"Serving file: {filename}")    
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.logger.error(f"Error serving file {filename}: {str(e)}")
            self.send_error(500)
    
    def check_auth(self):
        """Check if user is authenticated"""
        session_id = self.get_session_cookie()
        if not session_id:
            return False, "No session cookie found", None
        
        success, message, session = self.auth_manager.validate_session(session_id)
        if not success:
            return False, message, None
        
        return True, message, session
    
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
            auth_method = self.authentication_enabled.lower() if self.authentication_enabled else ""
            if not auth_method:
                self.logger.info("Session check with authentication disabled, returning anonymous user")
                self.send_json_response({
                    "authenticated": True,
                    "username": "anonymous",
                    "display_name": "Anonymous User",
                    "email": "",
                    "groups": [],
                    "auth_method": ""
                })
                return
                
            # Check if user is authenticated
            is_authenticated, message, session = self.check_auth()
            
            if is_authenticated:
                # Send user data
                self.logger.info(f"Session check: Authenticated user {session.get('username', '')}")
                self.send_json_response({
                    "authenticated": True,
                    "username": session.get("username", ""),
                    "display_name": session.get("display_name", ""),
                    "email": session.get("email", ""),
                    "groups": session.get("groups", []),
                    "auth_method": auth_method
                })
            else:
                # Send unauthenticated response
                self.logger.info(f"Session check: Not authenticated - {message}")
                self.send_json_response({
                    "authenticated": False,
                    "message": message
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
            self.logger.info("Fetching active VNC sessions")
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
                        
                        # Ensure runtime_display is set (for compatibility)
                        if 'runtime' in job and 'runtime_display' not in job:
                            job['runtime_display'] = job['runtime']
                        
                        # Ensure host is present
                        if 'exec_host' not in job or not job['exec_host'] or job['exec_host'] == 'N/A':
                            self.logger.warning(f"Job {job['job_id']} has no exec_host specified")
                        else:
                            job['host'] = job['exec_host']  # Duplicate for backward compatibility
                                                
                        # Get connection details if needed
                        if ('display' not in job or 'port' not in job) and job.get('host') and job.get('host') != 'N/A':
                            conn_details = self.lsf_manager.get_vnc_connection_details(job['job_id'])
                            if conn_details:
                                if 'port' in conn_details and 'port' not in job:
                                    job['port'] = conn_details['port']
                                if 'display' in conn_details and 'display' not in job:
                                    job['display'] = conn_details['display']
                except Exception as e:
                    self.logger.error(f"Error processing job {job.get('job_id', 'unknown')}: {str(e)}")
            
            self.send_json_response(jobs)
        except Exception as e:
            self.logger.error(f"Error handling VNC sessions: {str(e)}")
            self.send_error_response(str(e))
    
    def handle_lsf_config(self):
        """Handle LSF configuration request"""
        try:
            self.logger.info("Handling LSF configuration request")
            config = {
                'defaults': self.config_manager.get_lsf_defaults(),
                'queues': self.config_manager.get_available_queues(),
                'memory_options': self.config_manager.get_memory_options(),
                'core_options': self.config_manager.get_core_options(),
                'sites': self.config_manager.get_available_sites()
            }
            self.logger.debug(f"Sending LSF config: {config}")
            self.send_json_response(config)
        except Exception as e:
            self.logger.error(f"Error handling LSF config request: {str(e)}")
            self.send_error_response(str(e))
            
    def handle_server_config(self):
        """Handle server configuration request"""
        try:
            self.logger.debug("Starting handle_server_config method")
            config = self.server_config.copy()
            
            # Add auth config status to the response
            auth_method = config.get('authentication', '').lower()
            auth_enabled = self.is_auth_enabled()
            config['auth_enabled'] = auth_enabled
            
            # Add extra information for debugging
            if not auth_enabled and auth_method in ['entra', 'ldap']:
                # Authentication is configured but not available (missing modules)
                if auth_method == 'ldap':
                    try:
                        import ldap3
                        config['ldap_available'] = True
                    except ImportError:
                        config['ldap_available'] = False
                        
                if auth_method == 'entra':
                    try:
                        import msal
                        config['msal_available'] = True
                    except ImportError:
                        config['msal_available'] = False
            
            self.logger.debug(f"Sending server config response: {config}")
            self.send_json_response(config)
            self.logger.debug("Finished sending server config response")
        except Exception as e:
            self.logger.error(f"Error getting server config: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.send_error_response(f"Failed to get server configuration: {str(e)}")
    
    def handle_debug_commands(self):
        """Handle /debug/commands endpoint to display command history"""
        try:
            self.logger.info("Handling debug commands request")
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
            self.logger.debug(f"Sending command history with {len(formatted_history)} entries")
            self.send_json_response({
                "success": True,
                "command_history": formatted_history
            })
        except Exception as e:
            self.logger.error(f"Error handling debug commands: {str(e)}")
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": f"Error: {str(e)}"
            })
            
    def handle_debug_environment(self):
        """Handle /debug/environment endpoint to display environment information"""
        try:
            self.logger.info("Handling debug environment request")
            # Get basic environment info
            env_info = {
                "Python Version": platform.python_version(),
                "Platform": platform.platform(),
                "User": os.environ.get("USER", "Unknown"),
                "Hostname": platform.node(),
            }
            
            # Add all environment variables
            for key, value in os.environ.items():
                env_info[key] = value
            
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
            self.logger.error(f"Error handling debug environment: {str(e)}")
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
        self.logger.debug(f"Sending JSON response with status {status}")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            
            # Convert data to JSON string first to catch encoding errors
            json_data = json.dumps(data)
            self.logger.debug(f"JSON data length: {len(json_data)} bytes")
            
            # Log a brief summary of the data if it's large
            if isinstance(data, list) and len(data) > 5:
                self.logger.debug(f"Response data: list with {len(data)} items")
            elif isinstance(data, dict) and len(data) > 10:
                keys = list(data.keys())[:10]
                self.logger.debug(f"Response data: dictionary with {len(data)} keys, first keys: {keys}")
            else:
                self.logger.debug(f"Response data: {data}")
                
            # Write the data to the response
            self.wfile.write(json_data.encode())
            self.logger.debug("JSON response sent successfully")
        except Exception as e:
            self.logger.error(f"Error in send_json_response: {str(e)}")
            self.logger.error(traceback.format_exc())
    
    def send_error_response(self, message, status_code=500):
        """Send an error response"""
        # Ensure message is a string, not bytes
        if isinstance(message, bytes):
            message = message.decode('utf-8')
        elif not isinstance(message, str):
            message = str(message)
        
        self.logger.error(f"Sending error response with status {status_code}: {message}")
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        # Ensure we're sending a string that can be encoded to bytes
        error_json = json.dumps({'error': message})
        self.wfile.write(error_json.encode('utf-8'))

    def handle_vnc_config(self):
        """Handle VNC configuration request"""
        try:
            self.logger.info("Handling VNC configuration request")
            # Get VNC configuration
            config = {
                "window_managers": self.config_manager.get_available_window_managers(),
                "resolutions": self.config_manager.get_available_resolutions(),
                "defaults": self.config_manager.get_vnc_defaults(),
                "sites": self.config_manager.get_available_sites()
            }
            self.logger.debug(f"Sending VNC config: {config}")
            self.send_json_response(config)
        except Exception as e:
            self.logger.error(f"Error handling VNC config request: {str(e)}")
            self.send_error_response(str(e))

    def handle_vnc_start(self):
        """Handle VNC start request"""
        try:
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            self.logger.debug(f"Received raw post data: {post_data}")
            
            data = json.loads(post_data)
            self.logger.debug(f"Parsed JSON data: {data}")
            
            # Get default settings from config
            vnc_defaults = self.config_manager.get_vnc_defaults()
            lsf_defaults = self.config_manager.get_lsf_defaults()
            
            # Extract VNC settings
            vnc_settings = {
                "resolution": data.get("resolution", vnc_defaults.get("resolution")),
                "window_manager": data.get("window_manager", vnc_defaults.get("window_manager")),
                "color_depth": vnc_defaults.get("color_depth", 24),
                "site": data.get("site", vnc_defaults.get("site")),
                "vncserver_path": vnc_defaults.get("vncserver_path", "/usr/bin/vncserver"),
                "name": data.get("name", vnc_defaults.get("name_prefix", "vnc_session")),
                # Add xstartup configuration
                "xstartup_path": vnc_defaults.get("xstartup_path", ""),
                "use_custom_xstartup": vnc_defaults.get("use_custom_xstartup", False)
            }
            
            # Extract LSF settings
            lsf_settings = {
                "queue": data.get("queue", lsf_defaults.get("queue")),
                "num_cores": int(data.get("num_cores", lsf_defaults.get("num_cores"))),
                "memory_gb": int(data.get("memory_gb", lsf_defaults.get("memory_gb"))),
                "job_name": lsf_defaults.get("job_name", "myvnc_vncserver")
            }
            
            self.logger.info(f"Submitting VNC job with config: {vnc_settings}")
            self.logger.info(f"Using LSF settings: {lsf_settings}")
            
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
            self.logger.error(error_msg)
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
            self.logger.info(f"Stopping VNC job: {job_id}")
            result = self.lsf_manager.kill_vnc_job(job_id)
            
            # Return result
            self.send_json_response({
                "success": result,
                "message": "VNC session stopped successfully" if result else "Failed to stop VNC session",
                "job_id": job_id
            })
        except Exception as e:
            error_msg = f"Error stopping VNC session: {str(e)}"
            self.logger.error(error_msg)
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
            
            self.logger.info(f"Copying VNC session: {session_id}")
            
            # Get session details
            active_sessions = self.lsf_manager.get_active_vnc_jobs()
            session_to_copy = None
            
            for session in active_sessions:
                if str(session.get("job_id")) == str(session_id):
                    session_to_copy = session
                    break
            
            if not session_to_copy:
                raise ValueError(f"Session with ID {session_id} not found")
            
            # Get default settings from config
            vnc_defaults = self.config_manager.get_vnc_defaults()
            lsf_defaults = self.config_manager.get_lsf_defaults()
            
            # Extract and prepare settings for new session
            vnc_settings = {
                "resolution": session_to_copy.get("resolution", vnc_defaults.get("resolution")),
                "window_manager": session_to_copy.get("window_manager", vnc_defaults.get("window_manager")),
                "color_depth": vnc_defaults.get("color_depth", 24),
                "site": session_to_copy.get("site", vnc_defaults.get("site")),
                "vncserver_path": vnc_defaults.get("vncserver_path", "/usr/bin/vncserver"),
                "name": f"Copy of {session_to_copy.get('name', vnc_defaults.get('name_prefix', 'vnc_session'))}",
                # Add xstartup configuration
                "xstartup_path": vnc_defaults.get("xstartup_path", ""),
                "use_custom_xstartup": vnc_defaults.get("use_custom_xstartup", False)
            }
            
            lsf_settings = {
                "queue": session_to_copy.get("queue", lsf_defaults.get("queue")),
                "num_cores": int(session_to_copy.get("num_cores", lsf_defaults.get("num_cores"))),
                "memory_gb": int(session_to_copy.get("memory_gb", lsf_defaults.get("memory_gb"))),
                "job_name": lsf_defaults.get("job_name", "myvnc_vncserver")
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
            self.logger.error(error_msg)
            self.send_json_response({
                "success": False,
                "message": error_msg
            }, 500)

    def ldap_diagnostics(self):
        """Run LDAP diagnostic tests and return results"""
        try:
            # Check if LDAP is the configured authentication method
            if self.authentication_enabled.lower() != 'ldap':
                return self.send_json_response({
                    'success': False,
                    'message': f'LDAP is not the configured authentication method. Current method: {self.authentication_enabled}'
                }, 400)
                
            # Run the diagnostics
            self.logger.info("Running LDAP diagnostics...")
            results = self.auth_manager.ldap_manager.run_diagnostics()
            
            # Return the results
            return self.send_json_response({
                'success': True,
                'results': results
            })
        except Exception as e:
            self.logger.error(f"Error running LDAP diagnostics: {str(e)}")
            return self.send_json_response({
                'success': False,
                'message': f'Error running LDAP diagnostics: {str(e)}'
            }, 500)

def load_server_config():
    """Load server configuration from JSON file"""
    # Use only the default_server_config.json file
    config_path = Path(__file__).parent.parent.parent / "config" / "default_server_config.json"
    
    # Initialize logger early
    logger = logging.getLogger('myvnc')
    
    try:
        logger.info(f"Loading configuration from: {config_path}")
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.info(f"Successfully loaded config from: {config_path}")
            logger.info(f"Using configuration file: {config_path}")
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config_path}")
        logger.warning(f"Using default configuration values")
        config = {
            "host": "aus-misc",
            "port": 9143,
            "debug": False,
            "max_connections": 5,
            "timeout": 30,
            "logdir": "/tmp"  # Default to a safe location
        }
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON in configuration file: {config_path}")
        logger.warning(f"Using default configuration values")
        config = {
            "host": "aus-misc",
            "port": 9143,
            "debug": False,
            "max_connections": 5,
            "timeout": 30,
            "logdir": "/tmp"  # Default to a safe location
        }
    
    # Log config info to console for visibility
    logger.info(f"Server configuration: host={config.get('host')}, port={config.get('port')}, logdir={config.get('logdir')}")
    
    return config

def load_lsf_config():
    """Load LSF configuration from JSON file"""
    # Use a basic console logger until the full logging system is set up
    logger = get_logger()
    default_config_path = Path(__file__).parent.parent.parent / "config" / "default_lsf_config.json"
    
    try:
        logger.info(f"Loading LSF configuration from: {default_config_path}")
        with open(default_config_path, 'r') as f:
            config = json.load(f)
            logger.info(f"Successfully loaded LSF config from: {default_config_path}")
            return config
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning(f"LSF configuration file not found or invalid at {default_config_path}")
        logger.warning("Using default LSF configuration values")
        return {
            "default_settings": {
                "queue": "interactive",
                "num_cores": 2,
                "memory_gb": 16,
                "job_name": "myvnc_vncserver"
            },
            "available_queues": ["interactive"],
            "memory_options_gb": [2, 4, 8, 16, 32, 64],
            "core_options": [1, 2, 4, 8]
        }

def source_lsf_environment():
    """Source the LSF environment file"""
    logger = get_logger()
    lsf_config = load_lsf_config()
    env_file = lsf_config.get("env_file")
    
    if not env_file or not os.path.exists(env_file):
        # Try common LSF environment file locations
        common_locations = [
            "/site/lsf/aus-hw/conf/profile.lsf",
            "/etc/lsf/conf/profile.lsf",
            "/opt/lsf/conf/profile.lsf"
        ]
        
        for location in common_locations:
            if os.path.exists(location):
                env_file = location
                logger.info(f"Using LSF environment file: {env_file}")
                break
        else:
            # No LSF environment file found
            logger.warning("No LSF environment file found")
            return False
    else:
        logger.info(f"Using LSF environment file: {env_file}")
    
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
        logger.info(f"Successfully sourced LSF environment from {env_file}")
        return True
    except Exception as e:
        logger.error(f"Error sourcing LSF environment: {str(e)}")
        return False

def run_server(host=None, port=None, directory=None, config=None):
    """Run the web server"""
    # Load configuration if not provided
    if config is None:
        config = load_server_config()
    
    # Just get the existing logger rather than setting up logging again
    logger = get_logger()
    
    # Log the config only once in this function
    if config.get("debug", False):
        logger.debug(f"Server configuration: {config}")
    
    # Get log file path and display it clearly
    log_file = get_current_log_file()
    if log_file:
        log_path = log_file.absolute()
        # Log to file
        logger.info(f"Server logs are being written to: {log_path}")
    else:
        logger.warning("No log file is being used. Logs are only being written to console.")
    
    # Source LSF environment after logging is set up
    source_lsf_environment()

    # Override with command line arguments if provided
    host = host or config.get("host", "localhost")
    port = port or config.get("port", 9143)
    
    logger.info(f"Server initially configured for: {host}:{port}")
    
    # Always get fully qualified domain name, especially for localhost
    original_host = host
    fqdn_host = get_fully_qualified_hostname(host)
    
    # Log the transformation and update config for consistency
    if fqdn_host != original_host:
        logger.info(f"Resolved {original_host} to FQDN: {fqdn_host}")
        # Also update the config for other parts of the application that need the FQDN
        config["host"] = fqdn_host
    
    # Use 0.0.0.0 for binding to allow connections from any interface
    binding_host = "0.0.0.0"
    logger.info(f"Server will bind to {binding_host}:{port} but will report as {fqdn_host}")
    
    if directory is None:
        # Use the web directory
        directory = Path(__file__).parent / 'static'
    
    logger.info(f"Using static directory: {directory}")
    
    # Ensure data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    logger.info(f"Ensuring data directory exists: {data_dir}")
    
    # Set serving directory
    os.chdir(directory)
    logger.info(f"Changed working directory to: {os.getcwd()}")
    
    # Check if the address and port are available
    try:
        # Create a test socket to check availability
        logger.info(f"Testing if {binding_host}:{port} is available...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set socket option to allow reuse of the address
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((binding_host, port))
        sock.close()
        logger.info(f"Socket test successful, {binding_host}:{port} is available")
    except OSError as e:
        if e.errno == 99:  # Cannot assign requested address
            logger.error(f"Error: Cannot bind to address {binding_host}:{port} - Address not available")
            logger.error(f"       Verify that the host address is correct and exists on this machine")
            return
        elif e.errno == 98:  # Address already in use
            logger.error(f"Error: Cannot bind to address {binding_host}:{port} - Port is already in use")
            logger.error(f"       Check if another instance of the server is already running")
            logger.error(f"       You might need to kill the previous process using: `lsof -i :{port} | grep LISTEN`")
            return
        else:
            logger.error(f"Error: Cannot bind to address {binding_host}:{port} - {e}")
            return
    
    # Create server
    server_address = (binding_host, port)
    try:
        # Check for SSL certificate and key files in config
        ssl_cert = config.get("ssl_cert")
        ssl_key = config.get("ssl_key")
        ssl_ca_chain = config.get("ssl_ca_chain")
        use_https = ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key)
        
        # Create HTTP or HTTPS server based on SSL configuration
        logger.info(f"Creating {'HTTPS' if use_https else 'HTTP'} server on {binding_host}:{port}")
        httpd = LoggingHTTPServer(server_address, VNCRequestHandler)
        
        # Set timeout if specified in config
        if "timeout" in config:
            httpd.timeout = config["timeout"]
            logger.info(f"Server timeout set to {config['timeout']} seconds")
        
        # Wrap the socket with SSL if HTTPS is enabled
        if use_https:
            # Create SSL context with more permissive settings
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            
            # Load cert chain - first load the cert and key
            ssl_context.load_cert_chain(certfile=ssl_cert, keyfile=ssl_key)
            
            # If CA chain bundle is provided and exists, load it separately
            if ssl_ca_chain and os.path.exists(ssl_ca_chain):
                try:
                    # Try to load CA chain file using file path directly
                    ssl_context.load_verify_locations(cafile=ssl_ca_chain)
                    logger.info(f"SSL enabled with certificate: {ssl_cert}, key: {ssl_key}, CA chain: {ssl_ca_chain}")
                except Exception as e:
                    logger.warning(f"Failed to load CA chain bundle: {str(e)}")
                    # Try alternate method of loading CA chain
                    try:
                        with open(ssl_ca_chain, 'rb') as ca_file:
                            ca_data = ca_file.read()
                            # Create a temporary file with the correct format
                            import tempfile
                            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                                temp_path = temp_file.name
                                temp_file.write(ca_data)
                            
                            # Try to load from the temp file
                            ssl_context.load_verify_locations(cafile=temp_path)
                            logger.info(f"SSL enabled with certificate: {ssl_cert}, key: {ssl_key}, CA chain: {ssl_ca_chain} (via temp file)")
                            
                            # Clean up temp file
                            try:
                                os.unlink(temp_path)
                            except:
                                pass
                    except Exception as e2:
                        logger.warning(f"Failed to load CA chain bundle (alternate method): {str(e2)}")
                        logger.info(f"SSL enabled with certificate: {ssl_cert}, key: {ssl_key}")
            else:
                logger.info(f"SSL enabled with certificate: {ssl_cert}, key: {ssl_key}")
            
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE  # Don't verify client certificates
            
            # Wrap the socket with SSL
            httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
            
            # Log server startup with HTTPS
            logger.info(f"Server started - accessible at https://{fqdn_host}:{port}")
        else:
            # Log server startup with HTTP
            logger.info(f"Server started - accessible at http://{fqdn_host}:{port}")
        
        # Get log file path and log it clearly
        log_file = get_current_log_file()
        if log_file:
            log_path = log_file.absolute()
            logger.info(f"All server logs will be written to: {log_path}")
        
        if config.get("debug", False):
            logger.info(f"Debug mode: ON")
        
        logger.info("Server is ready to handle requests")
        
        try:
            logger.info("Starting server loop - waiting for connections")
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Server stopped by keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in server loop: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating server: {str(e)}")
        return
    
    logger.info("Server has been shutdown")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="MyVNC Web Server")
    parser.add_argument('--host', help='Host to bind to')
    parser.add_argument('--port', type=int, help='Port to bind to')
    parser.add_argument('--config', help='Path to server configuration file')
    parser.add_argument('--ssl-cert', help='Path to SSL certificate file for HTTPS')
    parser.add_argument('--ssl-key', help='Path to SSL private key file for HTTPS')
    parser.add_argument('--ssl-ca-chain', help='Path to SSL CA chain bundle file for HTTPS')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    
    # Initialize logger
    logger = get_logger()
    
    # Load configuration
    config = load_server_config()
    
    if args.config:
        # Custom config path specified
        config_path = Path(args.config)
        logger.info(f"Using custom config file: {config_path}")
        # Not implemented here, but you could load this config instead
    
    # Override config with command line SSL arguments if provided
    if args.ssl_cert:
        config["ssl_cert"] = args.ssl_cert
    
    if args.ssl_key:
        config["ssl_key"] = args.ssl_key
    
    if args.ssl_ca_chain:
        config["ssl_ca_chain"] = args.ssl_ca_chain
    
    run_server(host=args.host, port=args.port, config=config) 