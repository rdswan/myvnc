#!/usr/bin/env python3
"""
Command-line interface for MyVNC Manager
Uses curl to interact with the web server
"""

import argparse
import json
import subprocess
import sys
import os
from pathlib import Path
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import server config loader
from myvnc.web.server import load_server_config

logger = logging.getLogger(__name__)

def get_server_url():
    """Get the server URL from configuration file or environment variable"""
    # First try environment variable
    if "MYVNC_SERVER_URL" in os.environ:
        return os.environ.get("MYVNC_SERVER_URL")
    
    # Otherwise use config file
    config = load_server_config()
    host = config.get("host", "localhost")
    port = config.get("port", 8000)
    
    # Import get_fully_qualified_hostname here to avoid circular import
    from myvnc.web.server import get_fully_qualified_hostname
    
    # Convert localhost or simple hostname to FQDN
    host = get_fully_qualified_hostname(host)
    
    return f"http://{host}:{port}"

def run_curl_command(endpoint, method="GET", data=None):
    """
    Run a curl command to interact with the web server
    
    Args:
        endpoint: API endpoint
        method: HTTP method (GET, POST, etc.)
        data: Data to send (for POST requests)
    
    Returns:
        Response as Python object
    
    Raises:
        RuntimeError: If the command fails
    """
    server_url = get_server_url()
    url = f"{server_url}/api/{endpoint}"
    
    cmd = ["curl", "-s"]
    
    # Add method if not GET
    if method != "GET":
        cmd.extend(["-X", method])
    
    # Add content type if we have data
    if data:
        cmd.extend(["-H", "Content-Type: application/json"])
        cmd.extend(["-d", json.dumps(data)])
    
    # Add URL
    cmd.append(url)
    
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e.stderr}")
        raise RuntimeError(f"Command failed with exit code {e.returncode}")
    except json.JSONDecodeError:
        logger.error("Error: Invalid JSON response")
        raise RuntimeError("Failed to parse server response")

def list_vnc_sessions():
    """List all active VNC sessions"""
    try:
        jobs = run_curl_command("vnc/list")
        
        if not jobs:
            print("No active VNC sessions found.")
            return
        
        # Print table header
        print(f"{'Job ID':<10} {'Name':<20} {'User':<10} {'Status':<10} {'Queue':<15}")
        print("-" * 65)
        
        # Print jobs
        for job in jobs:
            print(f"{job['job_id']:<10} {job['name']:<20} {job['user']:<10} {job['status']:<10} {job['queue']:<15}")
    
    except Exception as e:
        print(f"Error listing VNC sessions: {str(e)}", file=sys.stderr)
        sys.exit(1)

def create_vnc_session(args):
    """Create a new VNC session"""
    try:
        # Get VNC and LSF configurations
        vnc_config = run_curl_command("config/vnc")
        lsf_config = run_curl_command("config/lsf")
        
        # Prepare data
        data = {}
        
        # Use provided values or defaults
        data["name"] = args.name or vnc_config["defaults"]["name_prefix"]
        data["resolution"] = args.resolution or vnc_config["defaults"]["resolution"]
        data["window_manager"] = args.window_manager or vnc_config["defaults"]["window_manager"]
        data["color_depth"] = args.color_depth or vnc_config["defaults"]["color_depth"]
        data["site"] = args.site or vnc_config["defaults"]["site"]
        data["vncserver_path"] = args.vncserver_path or vnc_config["defaults"].get("vncserver_path", "/usr/bin/vncserver")
        
        data["queue"] = args.queue or lsf_config["defaults"]["queue"]
        data["num_cores"] = args.cores or lsf_config["defaults"]["num_cores"]
        data["memory_gb"] = args.memory or lsf_config["defaults"]["memory_gb"]
        
        # Submit job
        result = run_curl_command("vnc/create", "POST", data)
        
        if "job_id" in result:
            print(f"VNC session created successfully. Job ID: {result['job_id']}")
        else:
            print("Failed to create VNC session.")
            sys.exit(1)
    
    except Exception as e:
        print(f"Error creating VNC session: {str(e)}", file=sys.stderr)
        sys.exit(1)

def kill_vnc_session(args):
    """Kill a VNC session"""
    try:
        job_id = args.job_id
        result = run_curl_command(f"vnc/kill/{job_id}", "POST")
        
        if result.get("status") == "success":
            print(f"VNC session {job_id} killed successfully.")
        else:
            print(f"Failed to kill VNC session {job_id}.")
            sys.exit(1)
    
    except Exception as e:
        print(f"Error killing VNC session: {str(e)}", file=sys.stderr)
        sys.exit(1)

def server_info():
    """Display server information"""
    try:
        # Get server configuration
        config = run_curl_command("config/server")
        logger.debug(f"Server Configuration:")
        logger.debug(f"Host: {config.get('host', 'localhost')}")
        logger.debug(f"Port: {config.get('port', 8000)}")
        logger.debug(f"Debug Mode: {'Enabled' if config.get('debug', False) else 'Disabled'}")
        logger.debug(f"Max Connections: {config.get('max_connections', 5)}")
        logger.debug(f"Timeout: {config.get('timeout', 30)} seconds")
    except Exception as e:
        logger.error(f"Error getting server information: {str(e)}")
        sys.exit(1)

def start_server(args):
    """Start the web server"""
    try:
        server_path = Path(__file__).parent.parent / "web" / "server.py"
        
        # Build command
        cmd = [sys.executable, str(server_path)]
        
        if args.host:
            # Import get_fully_qualified_hostname here if needed
            from myvnc.web.server import get_fully_qualified_hostname
            # Ensure we're using FQDN even for command line arguments
            fqdn_host = get_fully_qualified_hostname(args.host)
            cmd.extend(["--host", fqdn_host])
        
        if args.port:
            cmd.extend(["--port", str(args.port)])
        
        if args.config:
            cmd.extend(["--config", args.config])
        
        # Get configuration to display info
        config = load_server_config()
        host = args.host or config.get("host", "localhost")
        port = args.port or config.get("port", 8000)
        
        # Always use FQDN
        from myvnc.web.server import get_fully_qualified_hostname
        host = get_fully_qualified_hostname(host)
        
        print(f"Starting server on {host}:{port}...")
        subprocess.run(cmd)
    
    except KeyboardInterrupt:
        print("Server stopped.")
    except Exception as e:
        print(f"Error starting server: {str(e)}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main CLI entrypoint"""
    parser = argparse.ArgumentParser(description="MyVNC Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List active VNC sessions")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new VNC session")
    create_parser.add_argument("--name", help="Name for the VNC session")
    create_parser.add_argument("--resolution", help="Resolution for the VNC session")
    create_parser.add_argument("--window-manager", help="Window manager for the VNC session")
    create_parser.add_argument("--color-depth", type=int, help="Color depth for the VNC session")
    create_parser.add_argument("--site", help="Site for the VNC session")
    create_parser.add_argument("--queue", help="LSF queue to use")
    create_parser.add_argument("--cores", type=int, help="Number of cores to allocate")
    create_parser.add_argument("--memory", type=int, help="Memory to allocate in GB")
    create_parser.add_argument("--vncserver-path", help="Path to vncserver")
    
    # Kill command
    kill_parser = subparsers.add_parser("kill", help="Kill a VNC session")
    kill_parser.add_argument("job_id", help="Job ID to kill")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start the web server")
    server_parser.add_argument("--host", help="Host to bind to")
    server_parser.add_argument("--port", type=int, help="Port to bind to")
    server_parser.add_argument("--config", help="Path to custom config file")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Display server information")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run appropriate command
    if args.command == "list":
        list_vnc_sessions()
    elif args.command == "create":
        create_vnc_session(args)
    elif args.command == "kill":
        kill_vnc_session(args)
    elif args.command == "server":
        start_server(args)
    elif args.command == "info":
        server_info()
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 