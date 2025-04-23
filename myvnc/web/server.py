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
        endpoint = self.path.replace('/api/', '').split('?')[0]  # Remove query parameters
        
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
        elif endpoint == 'debug/commands':
            self.handle_debug_commands()
        elif endpoint == 'debug/environment':
            self.handle_debug_environment()
        elif endpoint == 'debug':
            self.handle_debug()
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
            # Get content length
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # Log the raw form data for debugging
            print(f"Received raw post data: {post_data}")
            
            # Parse the request data
            form_data = {}
            
            # Try to parse as JSON first
            if post_data.startswith('{'):
                try:
                    form_data = json.loads(post_data)
                    print(f"Parsed JSON data: {form_data}")
                except json.JSONDecodeError as e:
                    print(f"JSON parsing error: {str(e)}")
            else:
                # Fall back to form data parsing if not JSON
                try:
                    for field in post_data.split('&'):
                        if '=' in field:
                            key, value = field.split('=', 1)
                            form_data[key] = urllib.parse.unquote_plus(value)
                    print(f"Parsed form data: {form_data}")
                except Exception as e:
                    print(f"Form parsing error: {str(e)}")
            
            # Get default configurations
            vnc_defaults = self.config_manager.get_vnc_defaults()
            lsf_defaults = self.config_manager.get_lsf_defaults()
            
            # Extract VNC configuration
            vnc_config = {
                'resolution': form_data.get('resolution', vnc_defaults['resolution']),
                'window_manager': form_data.get('window_manager', vnc_defaults['window_manager']),
                'color_depth': int(form_data.get('color_depth', vnc_defaults['color_depth'])),
                'site': form_data.get('site', vnc_defaults['site']),
                'vncserver_path': vnc_defaults.get('vncserver_path', '/usr/bin/vncserver')
            }
            
            # Add name only if provided and not empty
            if 'name' in form_data and form_data['name'] and form_data['name'].strip():
                vnc_config['name'] = form_data['name']
            
            # Extract LSF configuration
            # The memory value from the UI is already in GB
            lsf_config = {
                'queue': form_data.get('queue', lsf_defaults['queue']),
                'num_cores': int(form_data.get('num_cores', lsf_defaults['num_cores'])),
                'memory_mb': int(form_data.get('memory_mb', lsf_defaults['memory_mb'] // 1024)),  # Keep in GB, do not convert
                'job_name': lsf_defaults.get('job_name', 'myvnc_vncserver')  # Always get from config
            }
            
            # Add host_filter only if provided and not empty
            if 'host_filter' in form_data and form_data['host_filter'] and form_data['host_filter'].strip():
                lsf_config['host_filter'] = form_data['host_filter']
            
            # Log the configuration being submitted for debugging
            print(f"Submitting VNC job with config: {vnc_config}")
            print(f"Using LSF settings: {lsf_config}")
            
            # Record the attempt in command history before executing
            command_entry = {
                'command': f"[VNC Create Request] Settings: {vnc_config}, LSF: {lsf_config}",
                'stdout': '',
                'stderr': '',
                'success': True
            }
            self.lsf_manager.command_history.append(command_entry)
            
            try:
                # Submit VNC job
                job_id = self.lsf_manager.submit_vnc_job(vnc_config, lsf_config)
                
                # Send response
                self.send_json_response({'job_id': job_id, 'status': 'submitted'})
                
            except Exception as e:
                error_msg = f"Error submitting VNC job: {str(e)}"
                print(error_msg, file=sys.stderr)
                
                # Update command entry with error
                command_entry['stderr'] = error_msg
                command_entry['success'] = False
                
                self.send_error_response(error_msg)
                
        except Exception as e:
            error_msg = f"Error processing VNC creation request: {str(e)}"
            print(error_msg, file=sys.stderr)
            # Add error to command history for debugging
            self.lsf_manager.command_history.append({
                'command': "[VNC Form Processing Error]",
                'stdout': '',
                'stderr': error_msg,
                'success': False
            })
            self.send_error_response(error_msg)
    
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
    
    def handle_debug_commands(self):
        """Handle debug command history request"""
        try:
            # Check if we should run tests
            # Parse the query string directly since FieldStorage doesn't work well with GET
            query_string = self.path.split('?', 1)[1] if '?' in self.path else ''
            params = {}
            for param in query_string.split('&'):
                if param and '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            run_tests = params.get('run_tests') == 'true'
            
            # Add test commands to the history only if explicitly requested
            if run_tests:
                try:
                    print("Running test commands as requested")
                    # Run LSF test commands to populate history
                    self.lsf_manager.run_test_commands()
                    
                    # Run a test VNC submission
                    self.lsf_manager.test_vnc_submission()
                except Exception as e:
                    print(f"Error running test commands: {str(e)}", file=sys.stderr)
                    # Still add the error to command history
                    self.lsf_manager.command_history.append({
                        'command': '[Test Command Execution]',
                        'stdout': '',
                        'stderr': f"Error running test commands: {str(e)}",
                        'success': False,
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            # Get command history from LSF manager
            commands = self.lsf_manager.get_command_history()
            
            # If still no commands, add a placeholder
            if not commands:
                commands = [{
                    'command': 'echo "Debug information"',
                    'stdout': 'No commands have been executed yet. Try clicking "Run Tests" to populate with test commands.',
                    'stderr': '',
                    'success': True,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }]
            
            # Get server environment info
            env_info = {
                'python_version': sys.version,
                'path': os.environ.get('PATH', 'Not set'),
                'lsf_profile': load_lsf_config().get('env_file', 'Not configured'),
                'lsf_available': 'bjobs' in os.environ.get('PATH', ''),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Check if vncserver is available
            try:
                vncserver_path = subprocess.run(['which', 'vncserver'], 
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.PIPE)
                env_info['vncserver_available'] = vncserver_path.stdout.decode('utf-8').strip() if vncserver_path.returncode == 0 else 'Not found'
            except Exception:
                env_info['vncserver_available'] = 'Error checking'
            
            # Send both as response
            self.send_json_response({
                'commands': commands,
                'environment': env_info
            })
        except Exception as e:
            error_msg = f"Error processing debug request: {str(e)}"
            print(error_msg, file=sys.stderr)
            self.send_error_response(error_msg)
    
    def handle_debug_environment(self):
        """Returns environment information for the application"""
        # Get environment info
        env_info = {
            "Python Version": platform.python_version(),
            "Platform": platform.platform(),
            "User": os.environ.get("USER", "Unknown"),
            "Hostname": platform.node(),
            "LSB_JOBID": os.environ.get("LSB_JOBID", "Not in LSF environment"),
            "LSF_ENVDIR": os.environ.get("LSF_ENVDIR", "Not set"),
            "PATH": os.environ.get("PATH", "Not set")
        }
        
        # Check if vncserver is available
        try:
            vncserver_path = subprocess.run(['which', 'vncserver'], 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE)
            env_info['VNC Server'] = vncserver_path.stdout.decode('utf-8').strip() if vncserver_path.returncode == 0 else 'Not found'
        except Exception:
            env_info['VNC Server'] = 'Error checking'
        
        # Send environment info in the expected format
        self.send_json_response({'environment': env_info})
    
    def handle_debug(self):
        """Returns debug information for the application"""
        # Get command history from the LSF manager
        command_history = self.lsf_manager.command_history
        
        # Get environment info
        env_info = {
            "Python Version": platform.python_version(),
            "Platform": platform.platform(),
            "User": os.environ.get("USER", "Unknown"),
            "Hostname": platform.node(),
            "LSB_JOBID": os.environ.get("LSB_JOBID", "Not in LSF environment"),
            "LSF_ENVDIR": os.environ.get("LSF_ENVDIR", "Not set")
        }
        
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
        
        # Build debug data
        debug_data = {
            "command_history": formatted_history,
            "environment": env_info,
            "config": {
                "vnc_config": self.config_manager.vnc_config,
                "lsf_config": self.config_manager.lsf_config
            }
        }
        
        # Set response headers
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Send response
        self.wfile.write(json.dumps(debug_data).encode('utf-8'))
    
    def send_json_response(self, data):
        """Send a JSON response"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def send_error_response(self, message):
        """Send an error response"""
        # Ensure message is a string, not bytes
        if isinstance(message, bytes):
            message = message.decode('utf-8')
        elif not isinstance(message, str):
            message = str(message)
        
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        # Ensure we're sending a string that can be encoded to bytes
        error_json = json.dumps({'error': message})
        self.wfile.write(error_json.encode('utf-8'))

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

def run_server(host=None, port=None, directory=None):
    """Run the web server"""
    # Source LSF environment
    source_lsf_environment()
    
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