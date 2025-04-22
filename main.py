#!/usr/bin/env python3
"""
Main entry point for the MyVNC application
"""

import sys
from myvnc.web.server import run_server

if __name__ == "__main__":
    # Parse command line arguments
    host = "localhost"
    port = 8000
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    # Run the server
    run_server(host=host, port=port) 