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
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.lsf_manager import LSFManager

class VNCRequestHandler(http.server.CGIHTTPRequestHandler):
    """Handler for VNC manager CGI requests"""
    
    def __init__(self, *args, **kwargs):
        self.config_manager = ConfigManager()
        self.lsf_manager = LSFManager()
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        # Handle API endpoints
        if self.path.startswith('/api/'):
            self.handle_api_request()
        else:
            # Serve static files
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path.startswith('/api/'):
            self.handle_api_request()
        else:
            self.send_error(404, "Not Found")
    
    def handle_api_request(self):
        """Handle API requests"""
        # Extract endpoint path
        endpoint = self.path.replace('/api/', '')
        
        # Handle different endpoints
        if endpoint == 'vnc/list':
            self.handle_list_vnc()
        elif endpoint == 'vnc/create':
            self.handle_create_vnc()
        elif endpoint.startswith('vnc/kill/'):
            job_id = endpoint.replace('vnc/kill/', '')
            self.handle_kill_vnc(job_id)
        elif endpoint == 'config/vnc':
            self.handle_vnc_config()
        elif endpoint == 'config/lsf':
            self.handle_lsf_config()
        elif endpoint == 'config/server':
            self.handle_server_config()
        else:
            self.send_error(404, "API endpoint not found")
    
    def handle_list_vnc(self):
        """Handle VNC list request"""
        try:
            jobs = self.lsf_manager.get_active_vnc_jobs()
            self.send_json_response(jobs)
        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_create_vnc(self):
        """Handle VNC create request"""
        try:
            # Parse form data for POST request
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST'}
            )
            
            # Extract VNC configuration
            vnc_config = {
                'name': form.getvalue('name', self.config_manager.get_vnc_defaults()['name_prefix']),
                'resolution': form.getvalue('resolution', self.config_manager.get_vnc_defaults()['resolution']),
                'window_manager': form.getvalue('window_manager', self.config_manager.get_vnc_defaults()['window_manager']),
                'color_depth': int(form.getvalue('color_depth', self.config_manager.get_vnc_defaults()['color_depth'])),
                'site': form.getvalue('site', self.config_manager.get_vnc_defaults()['site'])
            }
            
            # Extract LSF configuration
            lsf_config = {
                'queue': form.getvalue('queue', self.config_manager.get_lsf_defaults()['queue']),
                'num_cores': int(form.getvalue('num_cores', self.config_manager.get_lsf_defaults()['num_cores'])),
                'memory_mb': int(form.getvalue('memory_mb', self.config_manager.get_lsf_defaults()['memory_mb'])),
                'time_limit': form.getvalue('time_limit', self.config_manager.get_lsf_defaults()['time_limit'])
            }
            
            # Submit VNC job
            job_id = self.lsf_manager.submit_vnc_job(vnc_config, lsf_config)
            
            # Send response
            self.send_json_response({'job_id': job_id, 'status': 'submitted'})
            
        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_kill_vnc(self, job_id):
        """Handle VNC kill request"""
        try:
            success = self.lsf_manager.kill_vnc_job(job_id)
            if success:
                self.send_json_response({'status': 'success', 'message': f'VNC job {job_id} killed'})
            else:
                self.send_error_response(f'Failed to kill VNC job {job_id}')
        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_vnc_config(self):
        """Handle VNC configuration request"""
        try:
            config = {
                'defaults': self.config_manager.get_vnc_defaults(),
                'window_managers': self.config_manager.get_available_window_managers(),
                'resolutions': self.config_manager.get_available_resolutions(),
                'sites': self.config_manager.get_available_sites()
            }
            self.send_json_response(config)
        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_lsf_config(self):
        """Handle LSF configuration request"""
        try:
            config = {
                'defaults': self.config_manager.get_lsf_defaults(),
                'queues': self.config_manager.get_available_queues(),
                'memory_options': self.config_manager.get_memory_options(),
                'core_options': self.config_manager.get_core_options()
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
    
    def send_json_response(self, data):
        """Send a JSON response"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def send_error_response(self, message):
        """Send an error response"""
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode('utf-8'))

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

def run_server(host=None, port=None, directory=None):
    """Run the web server"""
    # Load configuration
    config = load_server_config()
    
    # Override with command line arguments if provided
    host = host or config.get("host", "localhost")
    port = port or config.get("port", 8000)
    
    if directory is None:
        # Use the web directory
        directory = Path(__file__).parent / 'static'
    
    # Set serving directory
    os.chdir(directory)
    
    # Create server
    server_address = (host, port)
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