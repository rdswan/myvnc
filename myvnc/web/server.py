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
import importlib

# Import custom exceptions
from myvnc.utils.lsf_manager import LSFError

# Add parent directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from myvnc.utils.auth_manager import AuthManager
from myvnc.utils.lsf_manager import LSFManager
from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.vnc_manager import VNCManager
from myvnc.utils.db_manager import DatabaseManager
from myvnc.utils.log_manager import setup_logging, get_logger, get_current_log_file
from myvnc.utils.config_loader import load_server_config, load_lsf_config, load_vnc_config, get_logger

def setup_logger():
    """Set up detailed logging configuration"""
    # Create logger
    logger = logging.getLogger('myvnc')
    logger.setLevel(logging.DEBUG)
    
    # Create console handler with a higher log level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add formatter to handlers
    console_handler.setFormatter(formatter)
    
    # Add handlers to the logger
    logger.addHandler(console_handler)
    
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
        error_type, error_value, error_tb = sys.exc_info()
        
        # Check if it's a common connection error from client disconnection
        if error_type in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Just log these common errors as info, not error
            self.logger.info(f"Client {client_address[0]}:{client_address[1]} disconnected: {error_type.__name__}: {error_value}")
            return
        
        # Check for OSError with common socket error codes
        if error_type is OSError and error_value.errno in (32, 104, 110):  # Broken pipe, Connection reset, Connection timed out
            self.logger.info(f"Socket error from {client_address[0]}:{client_address[1]}: {error_value}")
            return
        
        # Log other errors as actual errors with traceback
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
        
        # Get data directory from configuration
        server_config = load_server_config()
        data_dir = server_config.get("datadir", "/localdev/myvnc/data")
        
        # Initialize database manager with the correct data directory
        self.db_manager = DatabaseManager(data_dir=data_dir)
        
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
        
        self.logger.debug(f"Checking if authentication is enabled. Method: '{auth_method}'")
        
        # Check if authentication method is configured
        if auth_method not in ["entra", "ldap"]:
            self.logger.debug(f"Authentication disabled: method '{auth_method}' not configured")
            return False
            
        # For LDAP, check if LDAP module is available
        if auth_method == "ldap":
            try:
                import ldap3
                self.logger.debug("LDAP authentication: module ldap3 available")
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
        
        # Log the request with more details
        client_address = self.client_address[0] if hasattr(self, 'client_address') and self.client_address else 'unknown'
        self.logger.info(f"GET request from {client_address}: {path}")
        self.logger.debug(f"Request headers: {self.headers}")
        self.logger.debug(f"Cookie header: {self.headers.get('Cookie', 'None')}")
        
        # Check if authentication is enabled and available
        auth_enabled = self.is_auth_enabled()
        self.logger.debug(f"Authentication enabled: {auth_enabled}")
        
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

        # Server status endpoint should always be accessible without authentication
        # This is needed for manage.py and status checks
        if path == "/api/server/status":
            self.logger.info(f"Allowing access to server status without authentication")
            self.handle_server_status()
            return
        
        # Allow access to login error page without authentication
        if path == "/login_error" or path == "/login_error.html":
            self.logger.info(f"Serving login error page")
            self.serve_file("login_error.html")
            return
        
        # Debug endpoints should also be accessible without authentication to help with debugging 
        if path.startswith("/api/debug"):
            self.logger.info(f"Allowing access to debug endpoint without authentication: {path}")
            if path == "/api/debug/environment":
                self.handle_debug_environment()
            elif path == "/api/debug/session":
                self.handle_debug_session()
            elif path == "/api/debug/app_info":
                self.handle_debug_app_info()
            elif path == "/api/debug/commands":
                self.handle_debug_commands() 
            elif path == "/api/debug":
                self.handle_debug()
            else:
                self.send_error(404)
            return
        
        # Only check authentication if it's enabled
        if auth_enabled:
            # Check authentication for all paths except login page and assets
            if not path.startswith("/login") and not path.startswith("/auth/") and not self._is_public_asset(path):
                session_id = self.get_session_cookie()
                if not session_id:
                    self.logger.warning(f"No session cookie found for request to {path}, redirecting to login")
                    self.send_response(302)
                    # Use not_authenticated error instead of session_expired for initial load
                    self.send_header("Location", "/login?error=not_authenticated")
                    self.end_headers()
                    return
                
                success, message, session = self.auth_manager.validate_session(session_id)
                if not success:
                    self.logger.warning(f"Invalid session for request to {path}: {message}, redirecting to login")
                    self.send_response(302)
                    self.send_header("Location", "/login?error=session_expired")
                    self.end_headers()
                    return
                
                self.logger.info(f"Authenticated request from {session.get('username', 'unknown')} to {path}")
            else:
                self.logger.debug(f"Skipping authentication check for {path} (public path)")
        
        # Handle specific paths
        if path == "/":
            # Check for session ID in query parameters (fallback for cookie issues)
            query_params = parse_qs(parsed_path.query)
            direct_session_id = query_params.get('sid', [''])[0]
            
            if direct_session_id:
                self.logger.info(f"Found direct session ID in URL, setting cookie")
                
                # Check if the session is valid before setting cookie
                success, message, session = self.auth_manager.validate_session(direct_session_id)
                if success:
                    # Set the session cookie directly
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    cookie = f"session_id={direct_session_id}; Path=/; Max-Age={self.auth_manager.session_expiry}"
                    username = session.get('username', 'user')
                    username_cookie = f"username={username}; Path=/; Max-Age={self.auth_manager.session_expiry}"
                    self.send_header("Set-Cookie", cookie)
                    self.send_header("Set-Cookie", username_cookie)
                    self.end_headers()
                    
                    # Read and serve the index.html file
                    with open(os.path.join(self.directory, "index.html"), 'rb') as f:
                        content = f.read()
                    self.wfile.write(content)
                    return
                else:
                    self.logger.warning(f"Direct session ID is invalid: {message}")
                    # If session ID is invalid, redirect to login page
                    self.send_response(302)
                    self.send_header("Location", "/login?error=invalid_session")
                    self.end_headers()
                    return
            
            # Normal handling
            self.serve_file("index.html")
        elif path == "/login" and auth_enabled:
            self.serve_file("login.html")
        elif path == "/session" or path == "/api/auth/session":
            self.handle_session()
        elif path == "/api/vnc/sessions" or path == "/api/vnc/list":
            self.handle_vnc_sessions()
        elif path == "/api/vnc/list_all" or path == "/api/vnc/manager":
            self.handle_vnc_manager_mode()
        elif path == "/api/lsf/config" or path == "/api/config/lsf":
            self.handle_lsf_config()
        elif path == "/api/config/vnc":
            self.handle_vnc_config()
        elif path == "/auth/entra" and auth_enabled and self.authentication_enabled.lower() == "entra":
            self.handle_auth_entra()
        elif (path == "/auth/callback" or path == "/auth/callback/") and auth_enabled and self.authentication_enabled.lower() == "entra":
            # Handle both with and without trailing slash
            self.logger.info(f"Handling Entra callback at: {path}")
            self.handle_auth_callback()
        elif path == "/api/auth/ldap/diagnose" and auth_enabled and self.authentication_enabled.lower() == "ldap":
            self.ldap_diagnostics()
        # New User Settings API endpoint
        elif path == "/api/user/settings":
            self.handle_user_settings()
        # Manager Overrides API endpoint
        elif path == "/api/manager/overrides":
            self.handle_manager_overrides()
        else:
            # Try to serve static file
            super().do_GET()
    
    def do_DELETE(self):
        """Handle DELETE requests"""
        # Parse URL path
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Log the request
        client_address = self.client_address[0] if hasattr(self, 'client_address') and self.client_address else 'unknown'
        self.logger.info(f"DELETE request from {client_address}: {path}")
        
        # Check if authentication is enabled and available
        auth_enabled = self.is_auth_enabled()
        
        # Only check authentication if it's enabled
        if auth_enabled:
            # Check authentication for protected endpoints
            is_authenticated, message, session = self.check_auth()
            if not is_authenticated:
                self.send_error_response("Authentication required", 401)
                return
        
        # Handle different endpoints
        if path == "/api/manager/overrides":
            self.handle_manager_overrides()
        else:
            self.send_error_response(f"Unknown endpoint: {path}", 404)
    
    def do_POST(self):
        """Handle POST requests"""
        # Parse URL path
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Log the request
        client_address = self.client_address[0] if hasattr(self, 'client_address') and self.client_address else 'unknown'
        self.logger.info(f"POST request from {client_address}: {path}")
        
        # Special handling for POST to root (/) - this is our login redirect handler
        if path == "/":
            self.logger.info("Handling login redirect to main page")
            # Just serve the index page - cookies should already be set from login
            self.serve_file("index.html")
            return
            
        # Handle logout requests - always allow these without authentication checks
        if path == "/api/logout" or path == "/api/auth/logout":
            self.handle_logout()
            return
            
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
                auth_result = self.check_auth()
                if not auth_result[0]:  # Using index since it returns (success, message, session)
                    self.send_json_response({
                        "success": False,
                        "message": "Authentication required"
                    }, 401)
                    return
        
        # Handle generic paths (always accessible)
        if path == "/api/vnc/start" or path == "/api/vnc/create":
            self.handle_vnc_start()
        elif path.startswith("/api/vnc/stop") or path.startswith("/api/vnc/kill"):
            self.handle_vnc_stop()
        elif path == "/api/vnc/copy":
            self.handle_vnc_copy()
        # New User Settings API endpoint
        elif path == "/api/user/settings":
            self.handle_user_settings()
        # Manager Overrides API endpoint
        elif path == "/api/manager/overrides":
            self.handle_manager_overrides()
        else:
            self.send_error_response(f"Unknown endpoint: {path}", 404)
    
    def serve_file(self, filename):
        """Serve a file from the static directory"""
        try:
            with open(os.path.join(self.directory, filename), 'rb') as f:
                content = f.read()
            
            self.logger.info(f"Serving file: {filename}")    
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                # Client disconnected - this is normal and not worth a stack trace
                self.logger.info(f"Client disconnected while serving {filename}: {str(e)}")
                return
            except OSError as e:
                # Handle other socket errors gracefully
                if e.errno in (32, 104, 110):  # Broken pipe, Connection reset, Connection timed out
                    self.logger.info(f"Socket error while serving {filename}: {str(e)}")
                    return
                else:
                    # Re-raise unexpected OS errors
                    self.logger.error(f"OS error serving {filename}: {str(e)}")
                    raise
        except FileNotFoundError:
            self.logger.error(f"File not found: {filename}")
            self.send_error(404)
        except PermissionError:
            self.logger.error(f"Permission denied reading file: {filename}")
            self.send_error(403)
        except Exception as e:
            self.logger.error(f"Error serving file {filename}: {str(e)}")
            self.send_error(500)
    
    def get_session_cookie(self):
        """Get session cookie from request"""
        cookies = {}
        if "Cookie" in self.headers:
            cookie_header = self.headers["Cookie"]
            self.logger.debug(f"Found Cookie header: {cookie_header}")
            
            # Try to parse cookies properly
            try:
                # First try to parse session_id using regex directly - more reliable
                import re
                session_match = re.search(r'(?:^|;)\s*session_id=([^;]+)', cookie_header)
                if session_match:
                    session_id = session_match.group(1)
                    self.logger.debug(f"Extracted session_id directly: {session_id[:8] if len(session_id) > 8 else session_id}")
                    return session_id
                
                # If direct extraction failed, try standard parsing
                for cookie in cookie_header.split(";"):
                    try:
                        if "=" in cookie:
                            name, value = cookie.strip().split("=", 1)
                            name = name.strip()
                            # Only store cookies we care about to avoid memory issues
                            if name in ["session_id", "username"]:
                                cookies[name] = value
                                if name == "session_id":
                                    self.logger.debug(f"Parsed session_id cookie: {value[:8] if len(value) > 8 else value}")
                    except ValueError:
                        self.logger.warning(f"Malformed cookie: {cookie}")
            except Exception as e:
                self.logger.error(f"Error parsing cookies: {str(e)}")
        else:
            self.logger.debug("No Cookie header found in request")
        
        session_id = cookies.get("session_id")
        if session_id:
            self.logger.debug(f"Session ID from cookie: {session_id[:8]}...")
        else:
            self.logger.debug("No session_id cookie found")
        return session_id
    
    def check_auth(self):
        """Check if user is authenticated using session cookie"""
        # Check for session cookie
        session_id = self.get_session_cookie()
        
        # More detailed logging to diagnose cookie issues
        if not session_id:
            self.logger.warning("No session cookie found in request")
            cookie_header = self.headers.get('Cookie', 'None')
            self.logger.warning(f"Cookie header: {cookie_header}")
            return False, "No session cookie found", None
        
        # Debug the session ID
        if isinstance(session_id, str) and len(session_id) > 8:
            self.logger.debug(f"Validating session ID: {session_id[:8]}...")
        else:
            self.logger.debug(f"Validating session ID: {session_id}")
        
        # Check all available cookies for debugging
        cookie_header = self.headers.get('Cookie', '')
        all_cookies = []
        for cookie in cookie_header.split(';'):
            if '=' in cookie:
                name, value = cookie.strip().split('=', 1)
                all_cookies.append(f"{name}={value[:8] if len(value) > 8 else value}")
        
        self.logger.debug(f"All cookies in request: {all_cookies}")
        
        # Validate session with auth manager
        success, message, session = self.auth_manager.validate_session(session_id)
        
        if success:
            self.logger.debug(f"Session valid for user: {session.get('username', 'unknown')}")
            return True, message, session
        else:
            self.logger.warning(f"Session validation failed: {message}")
            return False, message, None
    
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
            
            # Log the login attempt (without password)
            self.logger.info(f"Login attempt for user: {username}")
            
            # Authenticate user
            success, message, session_id = self.auth_manager.authenticate(username, password)
            
            if success:
                # Get hostname for cookie domain
                host = self.headers.get("Host", "").split(":")[0]
                self.logger.info(f"Login successful for {username}, setting cookie for host: {host}")
                
                # Set session cookie with detailed logging - safely handle slicing
                if isinstance(session_id, str):
                    session_preview = session_id[:8] if len(session_id) > 8 else session_id
                    self.logger.debug(f"Setting session cookie: session_id={session_preview}..., Max-Age={self.auth_manager.session_expiry}")
                else:
                    self.logger.debug(f"Setting session cookie with non-string session_id type: {type(session_id)}")
                
                # Create browser-compatible session cookie without restrictive flags
                cookie = f"session_id={session_id}; Path=/; Max-Age={self.auth_manager.session_expiry}"
                username_cookie = f"username={username}; Path=/; Max-Age={self.auth_manager.session_expiry}"
                self.logger.debug(f"Cookie being set: {cookie}")
                
                # Get the actual session to log expiry details
                _, _, session = self.auth_manager.validate_session(session_id)
                if session and 'expiry' in session:
                    expiry_time = session['expiry']
                    self.logger.info(f"Session expires at: {time.ctime(expiry_time)}")
                
                # Send response with cookies
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", cookie)
                self.send_header("Set-Cookie", username_cookie)
                self.end_headers()
                
                # Send success response with session ID included
                response_data = {
                    "success": True,
                    "message": message,
                    "session_id": session_id,  # Include session ID in response
                    "username": username
                }
                self.wfile.write(json.dumps(response_data).encode())
                # Log the response without causing errors on session_id slicing
                if isinstance(session_id, str) and len(session_id) > 8:
                    self.logger.info(f"Login response sent for user {username} with session {session_id[:8]}...")
                else:
                    self.logger.info(f"Login response sent for user {username}")
            else:
                # Send error response
                self.logger.warning(f"Login failed for user {username}: {message}")
                self.send_json_response({
                    "success": False,
                    "message": message
                }, 401)
                
        except Exception as e:
            # Send error response for any exceptions
            self.logger.error(f"Login error: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.send_json_response({
                "success": False,
                "message": f"Login error: {str(e)}"
            }, 500)
    
    def handle_logout(self):
        """Handle logout requests"""
        try:
            # Get session ID from cookie
            session_id = self.get_session_cookie()
            
            # Attempt to log out the user with auth manager
            success = False
            message = "No active session"
            
            if session_id:
                try:
                    # Try to logout actual session if exists
                    success, message = self.auth_manager.logout(session_id)
                except Exception as e:
                    self.logger.warning(f"Error during logout process: {str(e)}")
            
            # Clear session cookie regardless of success
            self.logger.info("Clearing session cookie")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            
            # Set expired cookie to clear it from browser
            self.send_header("Set-Cookie", "session_id=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:01 GMT")
            self.end_headers()
            
            # Send success response
            response_data = {
                "success": True,  # Always report success to client
                "message": message if success else "Logged out"
            }
            self.wfile.write(json.dumps(response_data).encode())
                
        except Exception as e:
            # Log error but still try to clear cookie
            self.logger.error(f"Logout error: {str(e)}")
            self.logger.error(traceback.format_exc())
            
            # Try to clear cookie even on error
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "session_id=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:01 GMT")
            self.end_headers()
            
            # Send error message
            self.wfile.write(json.dumps({
                "success": True,  # Still report success to ensure client redirects
                "message": "Logged out (with errors)"
            }).encode())
    
    def handle_session(self):
        """Handle session validation requests"""
        try:
            client_ip = self.client_address[0] if hasattr(self, 'client_address') else 'unknown'
            self.logger.info(f"Session check from {client_ip}, headers: {self.headers.get('User-Agent', 'unknown agent')}")
            self.logger.debug(f"Cookie header: {self.headers.get('Cookie', 'None')}")
            
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
            session_id = self.get_session_cookie()
            if not session_id:
                self.logger.warning("Session check failed: No session cookie found")
                self.send_json_response({
                    "authenticated": False,
                    "message": "No session cookie found. Please log in."
                }, 401)
                return
            
            # Log session ID for tracking
            self.logger.debug(f"Validating session ID: {session_id[:8] if isinstance(session_id, str) and len(session_id) > 8 else session_id}...")
            
            # Validate session
            success, message, session = self.auth_manager.validate_session(session_id)
            
            if success and session:
                # Send user data
                username = session.get('username', '')
                display_name = session.get('display_name', username) or username  # Ensure display_name is not empty
                
                self.logger.info(f"Session check: Authenticated user {username}")
                self.send_json_response({
                    "authenticated": True,
                    "username": username,
                    "display_name": display_name,
                    "email": session.get("email", ""),
                    "groups": session.get("groups", []),
                    "auth_method": auth_method
                })
            else:
                # Send unauthenticated response
                self.logger.warning(f"Session check: Not authenticated - {message}")
                self.send_json_response({
                    "authenticated": False,
                    "message": message
                }, 401)
                
        except Exception as e:
            # Send error response for any exceptions
            self.logger.error(f"Session error: {str(e)}")
            self.logger.error(traceback.format_exc())
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
            
            # Log the full URL for debugging
            self.logger.info(f"Processing Entra ID callback URL: {self.path}")
            
            # Extract query parameters
            query_params = parse_qs(parsed_url.query)
            
            # Get authorization code
            code = query_params.get("code", [""])[0]
            
            if code:
                self.logger.info("Received authorization code from Entra ID")
                # Process authorization code
                success, message, session_id = self.auth_manager.handle_auth_code(code)
                
                if success:
                    # Set session cookie and redirect to home page - use standard cookie without restrictive flags
                    self.send_response(302)
                    self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; Max-Age={self.auth_manager.session_expiry}")
                    self.send_header("Location", "/")
                    self.end_headers()
                else:
                    # Authentication failed
                    self.logger.error(f"Entra ID authentication failed: {message}")
                    self.send_response(401)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"Authentication failed: {message}".encode())
            else:
                # No authorization code provided
                self.logger.error("No authorization code provided in Entra ID callback")
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"No authorization code provided")
                
        except Exception as e:
            # Send error response for any exceptions
            self.logger.error(f"Authentication callback error: {str(e)}")
            self.logger.error(traceback.format_exc())
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
            # Get authenticated user
            authenticated_user = self.get_authenticated_user() if self.is_auth_enabled() else None
            self.logger.info(f"Handling VNC sessions request for user: {authenticated_user}")
            
            # Get VNC sessions
            try:
                self.logger.info("Calling get_active_vnc_jobs")
                jobs = self.lsf_manager.get_active_vnc_jobs(authenticated_user)
                self.logger.info(f"Retrieved {len(jobs)} VNC sessions")
                
                # Log job details for debugging
                for i, job in enumerate(jobs):
                    job_id = job.get('job_id', 'unknown')
                    self.logger.debug(f"Job {i+1}/{len(jobs)}: id={job_id}, status={job.get('status')}, host={job.get('host')}")
            except Exception as e:
                self.logger.error(f"Error getting VNC sessions: {str(e)}")
                self.logger.error(f"Exception type: {type(e).__name__}")
                self.logger.error(traceback.format_exc())
                self.send_json_response({"error": f"Error getting VNC sessions: {str(e)}"}, status=500)
                return
                
            # Analyze job permissions
            user_jobs = []
            for job in jobs:
                # Process job information
                try:
                    if 'job_id' in job:
                        job_id = job['job_id']
                        self.logger.debug(f"Processing job {job_id} with resource requirements: {job.get('resource_req', 'None')}")
                        
                        # Log original resources for debugging
                        self.logger.debug(f"Job {job_id} original resources - cores: {job.get('cores', 'None')}, num_cores: {job.get('num_cores', 'None')}, mem_gb: {job.get('mem_gb', 'None')}")
                        
                        # Map 'cores' to 'num_cores' for consistency with the frontend
                        if 'cores' in job and 'num_cores' not in job:
                            job['num_cores'] = job['cores']
                            self.logger.debug(f"Job {job_id} - mapped cores to num_cores: {job['num_cores']}")
                        
                        # Map 'mem_gb' to 'memory_gb' for consistency with the frontend
                        if 'mem_gb' in job and 'memory_gb' not in job:
                            job['memory_gb'] = job['mem_gb']
                            self.logger.debug(f"Job {job_id} - mapped mem_gb to memory_gb: {job['memory_gb']}")
                        
                        # Add default resource values if not present and resources_unknown is not True
                        if 'resources_unknown' not in job or job['resources_unknown'] is not True:
                            if 'num_cores' not in job:
                                job['num_cores'] = 2  # Default value
                                self.logger.debug(f"Job {job_id} - using default num_cores: {job['num_cores']}")
                            if 'memory_gb' not in job:
                                job['memory_gb'] = 16  # Default value
                                self.logger.debug(f"Job {job_id} - using default memory_gb: {job['memory_gb']}")
                        else:
                            self.logger.debug(f"Job {job_id} - not applying default resources because resources_unknown is True")
                        
                        # Ensure runtime_display is set (for compatibility)
                        if 'runtime' in job and 'runtime_display' not in job:
                            job['runtime_display'] = job['runtime']
                        
                        # Add the name property if not present
                        if 'name' not in job:
                            job['name'] = 'VNC Session'
                        
                        # Ensure host is present
                        if 'exec_host' not in job or not job['exec_host'] or job['exec_host'] == 'N/A':
                            self.logger.warning(f"Job {job_id} has no exec_host specified")
                        else:
                            job['host'] = job['exec_host']  # Duplicate for backward compatibility
                                                
                        # Get connection details if needed
                        if ('display' not in job or 'port' not in job) and job.get('host') and job.get('host') != 'N/A':
                            conn_details = self.lsf_manager.get_vnc_connection_details(job_id, authenticated_user)
                            if conn_details:
                                if 'port' in conn_details and 'port' not in job:
                                    job['port'] = conn_details['port']
                                if 'display' in conn_details and 'display' not in job:
                                    job['display'] = conn_details['display']
                                    
                        # Log final resources for debugging
                        self.logger.debug(f"Job {job_id} final resources - num_cores: {job.get('num_cores', 'None')}, memory_gb: {job.get('memory_gb', 'None')}")
                        self.logger.debug(f"Job {job_id} OS field: {job.get('os', 'NOT SET')}")
                        user_jobs.append(job)
                except Exception as e:
                    self.logger.error(f"Error processing job {job.get('job_id', 'unknown')}: {str(e)}")
            
            self.logger.info(f"Sending {len(user_jobs)} processed jobs to client")
            # Log a sample job to see what's being sent
            if user_jobs:
                self.logger.debug(f"Sample job data: {user_jobs[0]}")
            self.send_json_response(user_jobs)
        except Exception as e:
            self.logger.error(f"Error handling VNC sessions request: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.send_json_response({"error": str(e)}, status=500)
    
    def handle_lsf_config(self):
        """Handle LSF configuration request"""
        try:
            self.logger.info("Handling LSF configuration request")
            
            # Get authenticated user
            username = None
            if self.is_auth_enabled():
                is_authenticated, message, session = self.check_auth()
                if is_authenticated:
                    username = session.get("username", None)
            else:
                username = os.environ.get("USER", None)
            
            # Get user-specific override if it exists
            user_override = None
            if username:
                user_override = self.db_manager.get_manager_override(username)
            
            # Get base LSF configuration
            config = {
                'defaults': self.config_manager.get_lsf_defaults(),
                'queues': self.config_manager.get_available_queues(),
                'memory_options': self.config_manager.get_memory_options(),
                'memory_options_gb': self.config_manager.get_memory_options(),  # For consistency
                'core_options': self.config_manager.get_core_options(),
                'sites': self.config_manager.get_available_sites(),
                'os_options': self.config_manager.lsf_config.get('os_options', [])
            }
            
            # Add enabled/user-specific options
            if user_override:
                # User has override - return their specific options
                config["enabled_cores"] = user_override.get('cores') if user_override.get('cores') is not None else self.config_manager.get_enabled_core_options()
                config["enabled_memory"] = user_override.get('memory') if user_override.get('memory') is not None else self.config_manager.get_enabled_memory_options()
                config["enabled_queues"] = user_override.get('queues') if user_override.get('queues') is not None else self.config_manager.get_available_queues()
                
                # For OS options, we need to filter the full os_options list
                if user_override.get('os_options') is not None:
                    os_names = user_override.get('os_options')
                    config["enabled_os_options"] = [os_opt for os_opt in config['os_options'] if os_opt.get("name") in os_names]
                else:
                    config["enabled_os_options"] = self.config_manager.get_enabled_os_options()
            else:
                # Return globally enabled options
                config["enabled_cores"] = self.config_manager.get_enabled_core_options()
                config["enabled_memory"] = self.config_manager.get_enabled_memory_options()
                config["enabled_queues"] = self.config_manager.get_available_queues()
                config["enabled_os_options"] = self.config_manager.get_enabled_os_options()
            
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
            
            self.logger.debug(f"Auth method: {auth_method}, auth_enabled: {auth_enabled}")
            
            # Always include LDAP/Entra module availability regardless of auth_enabled status
            if auth_method == 'ldap':
                # Force ldap_available to true when LDAP is the configured auth method
                # This matches what we'd return when the module is available
                config['ldap_available'] = True
                self.logger.debug("Setting ldap_available=True for LDAP auth method")
            
            if auth_method == 'entra':
                try:
                    import msal
                    config['msal_available'] = True
                    self.logger.debug("Adding msal_available=True to server config response")
                except ImportError:
                    config['msal_available'] = False
                    self.logger.debug("Adding msal_available=False to server config response")
            
            # Log the full config response to verify ldap_available is included
            self.logger.debug(f"Full server config response: {config}")
            if auth_method == 'ldap':
                self.logger.debug(f"LDAP available in response: {config.get('ldap_available', 'NOT PRESENT')}")
            
            # Send response with cache control headers
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            
            # Convert response to JSON and send
            response_json = json.dumps(config)
            self.wfile.write(response_json.encode())
            self.logger.debug("Finished sending server config response")
            return
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
            
            # Get server information
            server_info = {
                "server_version": getattr(self, "server_version", "1.0.0"),
                "python_version": platform.python_version(),
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "hostname": platform.node(),
                "platform": platform.platform(),
                "os_name": os.name,
                "system": platform.system()
            }
            
            # Get LSF information
            lsf_info = {
                "version": "Unknown",
                "lsf_root": os.environ.get("LSF_LIBDIR", "Unknown").replace("/lib", ""),
                "default_queue": self.config_manager.lsf_config.get("defaults", {}).get("queue", "Unknown")
            }
            
            # Try to get LSF version
            try:
                lsf_version_cmd = "lsid 2>/dev/null | grep 'My cluster name is' | cut -d' ' -f5-"
                lsf_info["version"] = subprocess.check_output(lsf_version_cmd, shell=True).decode().strip()
            except Exception as e:
                self.logger.error(f"Error getting LSF version: {str(e)}")
            
            # Get VNC information
            vnc_info = {
                "server_path": self.config_manager.vnc_config.get("defaults", {}).get("vncserver_path", "Unknown"),
                "default_resolution": self.config_manager.vnc_config.get("defaults", {}).get("resolution", "Unknown"),
                "default_window_manager": self.config_manager.vnc_config.get("defaults", {}).get("window_manager", "Unknown")
            }
            
            # Get environment variables
            env_info = {}
            for key, value in os.environ.items():
                env_info[key] = value
            
            # Send response
            self.send_json_response({
                "success": True,
                # Include server info fields both at root level and in server_info object
                "server_version": server_info["server_version"],
                "python_version": server_info["python_version"],
                "server_time": server_info["server_time"],
                "hostname": server_info["hostname"],
                "platform": server_info["platform"],
                "system": server_info["system"],
                # Include nested objects
                "lsf_info": lsf_info,
                "vnc_info": vnc_info,
                "server_info": server_info,
                "environment": env_info
            })
        except Exception as e:
            self.logger.error(f"Error handling debug environment: {str(e)}")
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": f"Error: {str(e)}"
            })
    
    def handle_debug_session(self):
        """Handle /debug/session endpoint to display session information"""
        try:
            self.logger.info("Handling debug session request")
            # Get session from cookies if present
            session_id = self.get_session_cookie()
            auth_success = False
            session_data = {}
            
            if session_id:
                auth_success, message, session = self.check_auth()
                if auth_success and session:
                    session_data = session
            
            # Get authentication method
            auth_method = self.authentication_enabled.lower() if self.authentication_enabled else "none"
            
            # Calculate expiry time if available
            expiry_info = "Not available"
            expiry_days = 0
            if session_data and 'expiry' in session_data:
                expiry_timestamp = session_data['expiry']
                current_time = time.time()
                if expiry_timestamp > current_time:
                    # Calculate days remaining
                    seconds_remaining = expiry_timestamp - current_time
                    days_remaining = seconds_remaining / (60 * 60 * 24)
                    expiry_days = round(days_remaining, 1)
                    expiry_info = f"{expiry_days} days remaining (expires {time.ctime(expiry_timestamp)})"
                else:
                    expiry_info = "Expired"
            
            # Get basic session info
            data = {
                "session_id": session_id or "Not set",
                "authenticated": auth_success,
                "username": session_data.get("username", "Anonymous"),
                "auth_method": auth_method,
                "login_time": session_data.get("login_time", "N/A"),
                "ip_address": self.client_address[0] if hasattr(self, 'client_address') else "Unknown",
                "user_agent": self.headers.get("User-Agent", "Unknown"),
                "permissions": session_data.get("permissions", []),
                "expiry_info": expiry_info,
                "expiry_days": expiry_days,
                "display_name": session_data.get("display_name", "N/A"),
                "email": session_data.get("email", "N/A"),
                "groups": session_data.get("groups", [])
            }
            
            # Send response
            self.send_json_response({
                "success": True,
                **data
            })
        except Exception as e:
            self.logger.error(f"Error handling debug session: {str(e)}")
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": f"Error: {str(e)}"
            })
    
    def handle_debug_app_info(self):
        """Handle /debug/app_info endpoint to display application status information"""
        try:
            self.logger.info("Handling debug app_info request")
            
            # Get server status using the shared function
            app_info = self.get_server_status()
            
            # Add VNC and LSF specific details that are only needed for the debug info
            app_info["vnc_config"] = {
                "window_managers": self.config_manager.get_available_window_managers() if hasattr(self, 'config_manager') else [],
                "default_resolution": self.config_manager.get_vnc_defaults().get("resolution", "Unknown") if hasattr(self, 'config_manager') else "Unknown",
                "vncserver_path": self.config_manager.get_vnc_defaults().get("vncserver_path", "Unknown") if hasattr(self, 'config_manager') else "Unknown"
            }
            
            app_info["lsf_config"] = {
                "default_queue": self.config_manager.get_lsf_defaults().get("queue", "Unknown") if hasattr(self, 'config_manager') else "Unknown",
                "default_cores": self.config_manager.get_lsf_defaults().get("num_cores", "Unknown") if hasattr(self, 'config_manager') else "Unknown",
                "default_memory_gb": self.config_manager.get_lsf_defaults().get("memory_gb", "Unknown") if hasattr(self, 'config_manager') else "Unknown"
            }
            
            # Send response
            self.send_json_response({
                "success": True,
                "app_info": app_info
            })
            
        except Exception as e:
            self.logger.error(f"Error handling app info: {str(e)}")
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "message": f"Error: {str(e)}"
            })
    
    def _is_ldap_available(self):
        """Check if LDAP module is available"""
        try:
            import ldap3
            return True
        except ImportError:
            return False
            
    def _is_entra_available(self):
        """Check if Microsoft Entra ID (MSAL) module is available"""
        try:
            import msal
            return True
        except ImportError:
            return False

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
        elif debug_command == 'session':
            self.handle_debug_session()
        elif debug_command == 'app_info':
            self.handle_debug_app_info()
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
                
            # Write the data to the response with error handling
            try:
                self.wfile.write(json_data.encode())
                self.logger.debug("JSON response sent successfully")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                # Client disconnected - this is normal and not worth a stack trace
                self.logger.info(f"Client disconnected while sending JSON response: {str(e)}")
                return
            except OSError as e:
                # Handle other socket errors gracefully
                if e.errno in (32, 104, 110):  # Broken pipe, Connection reset, Connection timed out
                    self.logger.info(f"Socket error while sending JSON response: {str(e)}")
                    return
                # Re-raise other OS errors
                self.logger.error(f"OS error in send_json_response: {str(e)}")
                raise
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
        
        try:
            self.wfile.write(error_json.encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
            # Client disconnected - this is normal and not worth a stack trace
            self.logger.info(f"Client disconnected while sending error response: {str(e)}")
            return
        except OSError as e:
            # Handle other socket errors gracefully
            if e.errno in (32, 104, 110):  # Broken pipe, Connection reset, Connection timed out
                self.logger.info(f"Socket error while sending error response: {str(e)}")
                return
            # Re-raise other OS errors
            self.logger.error(f"OS error in send_error_response: {str(e)}")
            raise

    def handle_vnc_config(self):
        """Handle VNC configuration request"""
        try:
            self.logger.info("Handling VNC configuration request")
            
            # Get authenticated user
            username = None
            if self.is_auth_enabled():
                is_authenticated, message, session = self.check_auth()
                if is_authenticated:
                    username = session.get("username", None)
            else:
                username = os.environ.get("USER", None)
            
            # Get user-specific override if it exists
            user_override = None
            if username:
                user_override = self.db_manager.get_manager_override(username)
            
            # Get base VNC configuration
            config = {
                "window_managers": self.config_manager.get_available_window_managers(),
                "resolutions": self.config_manager.get_available_resolutions(),
                "defaults": self.config_manager.get_vnc_defaults(),
                "sites": self.config_manager.get_available_sites()
            }
            
            # Add enabled/user-specific options
            if user_override:
                # User has override - return their specific options
                config["enabled_window_managers"] = user_override.get('window_managers') if user_override.get('window_managers') is not None else self.config_manager.get_enabled_window_managers()
            else:
                # Return globally enabled options
                config["enabled_window_managers"] = self.config_manager.get_enabled_window_managers()
            
            self.logger.debug(f"Sending VNC config: {config}")
            self.send_json_response(config)
        except Exception as e:
            self.logger.error(f"Error handling VNC config request: {str(e)}")
            self.send_error_response(str(e))

    def handle_vnc_start(self):
        """Handle VNC start request"""
        try:
            self.logger.info("Handling VNC start request")
            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(post_data)
            
            # Log all incoming data for debugging
            self.logger.info(f"VNC start request data: {json.dumps(data)}")
            
            # Get default settings from config
            vnc_defaults = self.config_manager.get_vnc_defaults()
            lsf_defaults = self.config_manager.get_lsf_defaults()
            
            # Extract VNC settings from request
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
            
            # Extract LSF settings from request
            lsf_settings = {
                "queue": data.get("queue", lsf_defaults.get("queue")),
                "num_cores": int(data.get("num_cores", lsf_defaults.get("num_cores"))),
                "memory_gb": int(data.get("memory_gb", lsf_defaults.get("memory_gb"))),
                "job_name": lsf_defaults.get("job_name", "myvnc_vncserver")
            }
            
            # Convert OS name to os_select and get container path if applicable
            os_name = data.get("os", lsf_defaults.get("os", "Any"))
            os_config = self.config_manager.get_os_config_by_name(os_name)
            if os_config:
                lsf_settings["os_select"] = os_config.get("select", "any")
                if "container" in os_config:
                    lsf_settings["container"] = os_config.get("container")
                    self.logger.info(f"Using container for OS '{os_name}': {os_config.get('container')}")
                if "bindpaths" in os_config:
                    lsf_settings["bindpaths"] = os_config.get("bindpaths")
                    self.logger.info(f"Using bindpaths for OS '{os_name}': {os_config.get('bindpaths')}")
            else:
                self.logger.warning(f"OS '{os_name}' not found in configuration, using default")
                lsf_settings["os_select"] = "any"
            
            # Log the settings that will be used
            self.logger.info(f"Using VNC settings: {json.dumps(vnc_settings)}")
            self.logger.info(f"Using LSF settings: {json.dumps(lsf_settings)}")
            
            # Get authenticated user if available
            authenticated_user = None
            if self.is_auth_enabled():
                is_authenticated, message, session = self.check_auth()
                if is_authenticated and session and 'username' in session:
                    authenticated_user = session.get('username')
                    self.logger.debug(f"Using authenticated user for LSF commands: {authenticated_user}")
            
            # Check for testing parameter to fake missing home directory
            fake_no_home = data.get("nohome", False)
            if fake_no_home:
                self.logger.warning("Testing mode: faking missing home directory (nohome=true)")
            
            # Get the server hostname for error messages
            server_hostname = self.server_config.get("host", "localhost")
            
            # Submit VNC job with authenticated user
            job_id = self.lsf_manager.submit_vnc_job(vnc_settings, lsf_settings, authenticated_user, fake_no_home=fake_no_home, server_hostname=server_hostname)
            
            # Return result - job_id is a string, not a dictionary
            self.send_json_response({
                "success": True,
                "message": "VNC session created successfully",
                "job_id": job_id,
                "status": "pending"
            })
        except LSFError as e:
            # LSF errors have clean error messages that should be shown to the user
            error_msg = str(e)
            self.logger.error(f"LSF error creating VNC session: {error_msg}")
            # Don't print stack trace for LSF errors as they are expected user errors
            self.send_json_response({
                "success": False,
                "message": error_msg
            }, 500)
        except Exception as e:
            # For other unexpected errors, show generic message and log details
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
            
            # Get authenticated user if available
            authenticated_user = None
            if self.is_auth_enabled():
                is_authenticated, message, session = self.check_auth()
                if is_authenticated and session and 'username' in session:
                    authenticated_user = session.get('username')
                    self.logger.debug(f"Using authenticated user for LSF commands: {authenticated_user}")
            
            # Kill VNC job using the correct method name and authenticated user
            self.logger.info(f"Stopping VNC job: {job_id}")
            result = self.lsf_manager.kill_vnc_job(job_id, authenticated_user)
            
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
            
            # Get authenticated user if available
            authenticated_user = None
            if self.is_auth_enabled():
                is_authenticated, message, session = self.check_auth()
                if is_authenticated and session and 'username' in session:
                    authenticated_user = session.get('username')
                    self.logger.debug(f"Using authenticated user for LSF commands: {authenticated_user}")
            
            # Get session details
            active_sessions = self.lsf_manager.get_active_vnc_jobs(authenticated_user)
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
            
            # Submit new VNC job with the authenticated user
            job_id = self.lsf_manager.submit_vnc_job(vnc_settings, lsf_settings, authenticated_user)
            
            # Return result
            self.send_json_response({
                "success": True,
                "message": "VNC session copied successfully",
                "job_id": job_id,
                "status": "pending"
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

    def handle_user_settings(self):
        """Handle GET and POST for user settings"""
        # Check authentication if enabled
        if self.is_auth_enabled():
            is_authenticated, message, session = self.check_auth()
            if not is_authenticated:
                self.send_error_response("Authentication required", 401)
                return
            
            # Get username from session
            username = session.get("username", "unknown")
        else:
            # If authentication is disabled, use system username
            username = os.environ.get("USER", "unknown")
        
        # Handle GET or POST
        if self.command == "GET":
            self.handle_get_user_settings(username)
        elif self.command == "POST":
            self.handle_post_user_settings(username)
    
    def handle_get_user_settings(self, username):
        """Handle GET request for user settings"""
        try:
            # Get user settings from database
            self.logger.info(f"Getting user settings for {username}")
            settings = self.db_manager.get_user_settings(username)
            
            # Log the settings for debugging
            self.logger.info(f"Retrieved settings for {username}: {json.dumps(settings)}")
            
            # Check specifically for VNC settings
            if 'vnc_settings' in settings:
                self.logger.info(f"VNC settings found: {json.dumps(settings['vnc_settings'])}")
            else:
                self.logger.warning(f"No VNC settings found for user {username}")
            
            # Send response
            response = {
                "success": True,
                "settings": settings
            }
            
            self.logger.info(f"Sending user settings response: {json.dumps(response)}")
            self.send_json_response(response)
            
        except Exception as e:
            self.logger.error(f"Error getting user settings: {str(e)}")
            self.send_error_response(f"Error getting user settings: {str(e)}")
    
    def handle_post_user_settings(self, username):
        """Handle POST request for user settings"""
        try:
            # Get content length
            content_length = int(self.headers.get('Content-Length', 0))
            
            # Read and parse request body
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(post_data)
            
            # Validate settings
            if not isinstance(data, dict) or "settings" not in data:
                self.send_error_response("Invalid request: 'settings' field is required", 400)
                return
            
            settings = data["settings"]
            
            # Validate settings structure
            if not isinstance(settings, dict):
                self.send_error_response("Invalid request: 'settings' must be an object", 400)
                return
            
            # Save user settings
            success = self.db_manager.save_user_settings(username, settings)
            
            if success:
                # Send success response
                response = {
                    "success": True,
                    "message": "Settings saved successfully"
                }
                self.send_json_response(response)
            else:
                self.send_error_response("Failed to save settings", 500)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in request: {str(e)}")
            self.send_error_response(f"Invalid JSON in request: {str(e)}", 400)
        except Exception as e:
            self.logger.error(f"Error saving user settings: {str(e)}")
            self.send_error_response(f"Error saving user settings: {str(e)}", 500)
    
    def handle_manager_overrides(self):
        """Handle GET, POST, and DELETE requests for manager overrides"""
        # Check authentication
        if self.is_auth_enabled():
            is_authenticated, message, session = self.check_auth()
            if not is_authenticated:
                self.send_error_response("Authentication required", 401)
                return
            
            # Get username from session
            manager_username = session.get("username", "unknown")
        else:
            # If authentication is disabled, use system username
            manager_username = os.environ.get("USER", "unknown")
        
        # Verify manager permission
        managers = self.server_config.get('managers', [])
        if manager_username not in managers:
            self.logger.warning(f"Unauthorized access to manager overrides by user {manager_username}")
            self.send_error_response("Forbidden: Manager access required", 403)
            return
        
        # Route to appropriate handler
        if self.command == "GET":
            self.handle_get_manager_overrides()
        elif self.command == "POST":
            self.handle_post_manager_override(manager_username)
        elif self.command == "DELETE":
            self.handle_delete_manager_override()
    
    def handle_get_manager_overrides(self):
        """Handle GET request for all manager overrides"""
        try:
            # Get all overrides from database
            self.logger.info("Getting all manager overrides")
            overrides = self.db_manager.get_all_manager_overrides()
            
            # Send response
            response = {
                "success": True,
                "overrides": overrides
            }
            
            self.logger.info(f"Retrieved {len(overrides)} manager overrides")
            self.send_json_response(response)
            
        except Exception as e:
            self.logger.error(f"Error getting manager overrides: {str(e)}")
            self.send_error_response(f"Error getting manager overrides: {str(e)}")
    
    def handle_post_manager_override(self, manager_username):
        """Handle POST request to create/update a manager override"""
        try:
            self.logger.info(f"Handling POST manager override request from {manager_username}")
            
            # Get content length
            content_length = int(self.headers.get('Content-Length', 0))
            self.logger.info(f"Content length: {content_length}")
            
            # Read and parse request body
            post_data = self.rfile.read(content_length).decode('utf-8')
            self.logger.info(f"Request body: {post_data}")
            
            data = json.loads(post_data)
            self.logger.info(f"Parsed data: {data}")
            
            # Validate request
            if not isinstance(data, dict) or "username" not in data or "overrides" not in data:
                self.logger.error("Invalid request structure")
                self.send_error_response("Invalid request: 'username' and 'overrides' fields are required", 400)
                return
            
            target_username = data["username"]
            overrides = data["overrides"]
            
            self.logger.info(f"Target username: {target_username}")
            self.logger.info(f"Overrides: {overrides}")
            
            # Validate overrides structure
            if not isinstance(overrides, dict):
                self.logger.error(f"Overrides is not a dict: {type(overrides)}")
                self.send_error_response("Invalid request: 'overrides' must be an object", 400)
                return
            
            # Save manager override
            self.logger.info(f"Calling db_manager.save_manager_override for {target_username}")
            success = self.db_manager.save_manager_override(target_username, overrides, manager_username)
            
            self.logger.info(f"Save result: {success}")
            
            if success:
                # Send success response
                response = {
                    "success": True,
                    "message": f"Override saved successfully for user {target_username}"
                }
                self.logger.info(f"Sending success response: {response}")
                self.send_json_response(response)
            else:
                self.logger.error("Database save returned False")
                self.send_error_response("Failed to save override", 500)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in request: {str(e)}")
            self.logger.error(f"JSON decode error traceback: {traceback.format_exc()}")
            self.send_error_response(f"Invalid JSON in request: {str(e)}", 400)
        except Exception as e:
            self.logger.error(f"Error saving manager override: {str(e)}")
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            self.send_error_response(f"Error saving manager override: {str(e)}", 500)
    
    def handle_delete_manager_override(self):
        """Handle DELETE request to remove a manager override"""
        try:
            # Get content length
            content_length = int(self.headers.get('Content-Length', 0))
            
            # Read and parse request body
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(post_data)
            
            # Validate request
            if not isinstance(data, dict) or "username" not in data:
                self.send_error_response("Invalid request: 'username' field is required", 400)
                return
            
            target_username = data["username"]
            
            # Delete manager override
            success = self.db_manager.delete_manager_override(target_username)
            
            if success:
                # Send success response
                response = {
                    "success": True,
                    "message": f"Override deleted successfully for user {target_username}"
                }
                self.send_json_response(response)
            else:
                self.send_error_response("Failed to delete override", 500)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in request: {str(e)}")
            self.send_error_response(f"Invalid JSON in request: {str(e)}", 400)
        except Exception as e:
            self.logger.error(f"Error deleting manager override: {str(e)}")
            self.send_error_response(f"Error deleting manager override: {str(e)}", 500)

    def get_server_status(self):
        """Get comprehensive server status information"""
        try:
            # Get server configuration
            server_config = self.server_config.copy()
            
            # Get hostname for current configuration
            host = server_config.get("host", "localhost")
            port = server_config.get("port", 9143)
            ssl_cert = server_config.get("ssl_cert", "")
            ssl_key = server_config.get("ssl_key", "")
            ssl_ca_chain = server_config.get("ssl_ca_chain", "")
            auth_method = server_config.get("authentication", "").lower()
            
            # Determine SSL status
            ssl_enabled = ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key)
            
            # Determine auth status
            auth_enabled = self.is_auth_enabled()
            auth_status = "Disabled"
            if auth_enabled:
                auth_status = f"{auth_method.upper()} (Active)"
            elif auth_method:
                auth_status = f"{auth_method.upper()} (Configured but not active)"
                
            # Get process info
            pid = os.getpid()
            
            # Calculate uptime
            uptime = "Unknown"
            uptime_seconds = 0
            try:
                import psutil
                process = psutil.Process(pid)
                start_time = process.create_time()
                uptime_seconds = time.time() - start_time
                
                # Format uptime nicely
                if uptime_seconds < 60:
                    uptime = f"{int(uptime_seconds)}s"
                elif uptime_seconds < 3600:
                    minutes = int(uptime_seconds / 60)
                    seconds = int(uptime_seconds % 60)
                    uptime = f"{minutes}m {seconds}s"
                elif uptime_seconds < 86400:
                    hours = int(uptime_seconds / 3600)
                    minutes = int((uptime_seconds % 3600) / 60)
                    uptime = f"{hours}h {minutes}m"
                else:
                    days = int(uptime_seconds / 86400)
                    hours = int((uptime_seconds % 86400) / 3600)
                    uptime = f"{days}d {hours}h"
            except:
                # If psutil not available, use a simpler approach
                uptime = "Not available (psutil required)"
            
            # Get current log file
            log_file = get_current_log_file()
            log_file_path = str(log_file.absolute()) if log_file else "Unknown"
            
            # Determine if we need to include port in URL (not needed for standard ports)
            include_port = True
            if ssl_enabled and port == 443:
                include_port = False
            elif not ssl_enabled and port == 80:
                include_port = False
                
            # Create URL with proper port handling
            if include_port:
                url = f"https://{host}:{port}" if ssl_enabled else f"http://{host}:{port}"
            else:
                url = f"https://{host}" if ssl_enabled else f"http://{host}"
            
            # Config directory information
            config_dir = os.environ.get("MYVNC_CONFIG_DIR", "")
            server_config_file = os.environ.get("MYVNC_SERVER_CONFIG_FILE", "")
            vnc_config_file = os.environ.get("MYVNC_VNC_CONFIG_FILE", "")
            lsf_config_file = os.environ.get("MYVNC_LSF_CONFIG_FILE", "")
            
            # If environment variables don't provide paths, use default locations
            if not server_config_file:
                if config_dir:
                    server_config_file = os.path.join(config_dir, "server_config.json")
                else:
                    server_config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "server_config.json")
            
            # Get VNC config path if not provided
            if not vnc_config_file:
                if config_dir:
                    vnc_config_file = os.path.join(config_dir, "vnc_config.json")
                else:
                    vnc_config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "vnc_config.json")
            
            # Get LSF config path if not provided
            if not lsf_config_file:
                if config_dir:
                    lsf_config_file = os.path.join(config_dir, "lsf_config.json")
                else:
                    lsf_config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "lsf_config.json")
            
            # Ensure paths are absolute
            server_config_file = os.path.abspath(server_config_file)
            vnc_config_file = os.path.abspath(vnc_config_file)
            lsf_config_file = os.path.abspath(lsf_config_file)
            
            # Get LDAP and Entra config paths, resolve relative paths
            ldap_config_path = server_config.get('ldap_config', '')
            entra_config_path = server_config.get('entra_config', '')
            
            # Ensure LDAP config path is absolute if it exists
            if ldap_config_path and not os.path.isabs(ldap_config_path):
                ldap_config_path = os.path.abspath(os.path.join(os.path.dirname(server_config_file), ldap_config_path))
            
            # Ensure Entra config path is absolute if it exists
            if entra_config_path and not os.path.isabs(entra_config_path):
                entra_config_path = os.path.abspath(os.path.join(os.path.dirname(server_config_file), entra_config_path))
            
            # Get module availability
            ldap_available = self._is_ldap_available()
            msal_available = self._is_entra_available()
            
            # Build detailed status information
            status = {
                "status": "Running",
                "pid": pid,
                "host": host,
                "port": port,
                "url": url,
                "ssl_enabled": ssl_enabled,
                "ssl_cert": ssl_cert if ssl_enabled else "",
                "ssl_key": ssl_key if ssl_enabled else "",
                "ssl_ca_chain": ssl_ca_chain if ssl_enabled and ssl_ca_chain else "",
                "auth_enabled": auth_enabled,
                "auth_method": auth_method,
                "auth_method_configured": bool(auth_method),
                "auth_status": auth_status,
                "ldap_available": ldap_available,
                "msal_available": msal_available,
                "log_directory": os.path.abspath(server_config.get("logdir", "")),
                "log_file": log_file_path,
                "data_directory": os.path.abspath(server_config.get("datadir", "")),
                "uptime": uptime,
                "uptime_seconds": uptime_seconds,
                "debug_mode": server_config.get("debug", False),
                "python_executable": sys.executable,
                "python_version": platform.python_version(),
                
                # Include command line arguments used to start the server
                "cli_args": sys.argv,
                
                # Include information about config file locations
                "config_dir": config_dir,
                "server_config_file": server_config_file,
                "vnc_config_file": vnc_config_file,
                "lsf_config_file": lsf_config_file,
                "ldap_config_file": ldap_config_path or "Not configured",
                "entra_config_file": entra_config_path or "Not configured",
                
                # Include the full server configuration
                "server_config": server_config,
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting server status: {str(e)}")
            return {
                "error": f"Error getting server status: {str(e)}",
                "status": "Error"
            }
    
    def handle_server_status(self):
        """Handle server status request"""
        try:
            # Get server status
            status = self.get_server_status()
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            
            # Convert response to JSON and send
            response_json = json.dumps(status)
            self.wfile.write(response_json.encode())
            
        except Exception as e:
            self.logger.error(f"Error handling server status request: {str(e)}")
            self.send_error_response(f"Error getting server status: {str(e)}", 500)

    def get_authenticated_user(self):
        """Get the authenticated username from the session"""
        auth_enabled = self.is_auth_enabled()
        if not auth_enabled:
            return None
            
        is_authenticated, message, session = self.check_auth()
        if is_authenticated and session and 'username' in session:
            return session.get('username')
        
        return None

    def _process_vnc_jobs(self, jobs, authenticated_user):
        """Internal helper to process job dictionaries to the format expected by UI."""
        user_jobs = []
        for job in jobs:
            try:
                if 'job_id' in job:
                    job_id = job['job_id']

                    # Map cores/memory for consistency
                    if 'cores' in job and 'num_cores' not in job:
                        job['num_cores'] = job['cores']
                    if 'mem_gb' in job and 'memory_gb' not in job:
                        job['memory_gb'] = job['mem_gb']

                    # Add defaults if unknown
                    if 'resources_unknown' not in job or job['resources_unknown'] is not True:
                        job.setdefault('num_cores', 2)
                        job.setdefault('memory_gb', 16)

                    # Ensure runtime_display
                    if 'runtime' in job and 'runtime_display' not in job:
                        job['runtime_display'] = job['runtime']

                    # Ensure name
                    job.setdefault('name', 'VNC Session')

                    # Ensure host field
                    if 'exec_host' in job and job.get('exec_host') and job.get('exec_host') != 'N/A':
                        job['host'] = job['exec_host']

                    # Get connection details if missing
                    if ('display' not in job or 'port' not in job) and job.get('host') and job.get('host') != 'N/A':
                        conn_details = self.lsf_manager.get_vnc_connection_details(job_id, authenticated_user)
                        if conn_details:
                            job.setdefault('port', conn_details.get('port'))
                            job.setdefault('display', conn_details.get('display'))

                    user_jobs.append(job)
            except Exception as e:
                self.logger.error(f"Error processing job {job.get('job_id', 'unknown')}: {str(e)}")

        return user_jobs

    def handle_vnc_manager_mode(self):
        """Handle Manager Mode VNC session listing - lists all users' VNC jobs if requester is in managers list."""
        try:
            authenticated_user = self.get_authenticated_user() if self.is_auth_enabled() else None

            # Verify permission
            managers = self.server_config.get('managers', [])
            if authenticated_user not in managers:
                self.logger.warning(f"Unauthorized access to manager mode by user {authenticated_user}")
                self.send_json_response({"error": "Forbidden"}, status=403)
                return

            self.logger.info(f"Manager mode request by {authenticated_user}")

            # Get all jobs (no user filter) but run under the requesting user's credentials
            jobs = self.lsf_manager.get_active_vnc_jobs(authenticated_user=authenticated_user, all_users=True)

            processed_jobs = self._process_vnc_jobs(jobs, authenticated_user)

            self.send_json_response(processed_jobs)
        except Exception as e:
            self.logger.error(f"Error handling manager mode VNC sessions: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.send_json_response({"error": str(e)}, status=500)

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
    
    # Load LSF and VNC configs too
    lsf_config = load_lsf_config()
    vnc_config = load_vnc_config()
    
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
    data_dir = config.get("datadir", "myvnc/data")
    
    # Create the directory if it doesn't exist
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    
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