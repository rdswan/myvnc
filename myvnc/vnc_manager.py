import subprocess
import psutil
import os
from typing import List, Dict, Optional

class VNCServer:
    def __init__(self, name: str, host: str, port: int, display: int, 
                 resolution: str = "1024x768", window_manager: str = "gnome"):
        self.name = name
        self.host = host
        self.port = port
        self.display = display
        self.resolution = resolution
        self.window_manager = window_manager
        self.pid = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "display": self.display,
            "resolution": self.resolution,
            "window_manager": self.window_manager,
            "pid": self.pid
        }

class VNCManager:
    def __init__(self):
        self.servers: List[VNCServer] = []

    def start_server(self, server: VNCServer) -> bool:
        """Start a VNC server with the given configuration."""
        try:
            # Construct the VNC server command
            cmd = [
                "vncserver",
                f":{server.display}",
                "-geometry", server.resolution,
                "-depth", "24",
                "-name", server.name
            ]
            
            # Start the VNC server
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            server.pid = process.pid
            self.servers.append(server)
            return True
        except Exception as e:
            print(f"Error starting VNC server: {e}")
            return False

    def stop_server(self, server: VNCServer) -> bool:
        """Stop a VNC server."""
        try:
            if server.pid:
                # Kill the VNC server process
                subprocess.run(["vncserver", "-kill", f":{server.display}"])
                self.servers.remove(server)
                return True
            return False
        except Exception as e:
            print(f"Error stopping VNC server: {e}")
            return False

    def list_servers(self) -> List[Dict]:
        """List all running VNC servers."""
        return [server.to_dict() for server in self.servers]

    def get_server_by_name(self, name: str) -> Optional[VNCServer]:
        """Get a VNC server by its name."""
        for server in self.servers:
            if server.name == name:
                return server
        return None

    def is_server_running(self, server: VNCServer) -> bool:
        """Check if a VNC server is running."""
        if not server.pid:
            return False
        try:
            return psutil.pid_exists(server.pid)
        except:
            return False 