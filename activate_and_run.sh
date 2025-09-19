#!/bin/bash
# Script to activate virtual environment and run MyVNC commands
# Usage: ./activate_and_run.sh [command]
# Example: ./activate_and_run.sh status
# Example: ./activate_and_run.sh start
# Example: ./activate_and_run.sh stop

# This virtual environment uses NFS Python 3.10.12 for cross-machine compatibility
# Virtual environment path: /home/bswan/tools_src/myvnc/.venv (uses /tools_vendor/FOSS/python3/3.10.12/bin/python3)

# Activate the virtual environment
source /home/bswan/tools_src/myvnc/.venv/bin/activate

# Default command if none provided
COMMAND=${1:-status}

# Run the manage.py script with the provided command
python /tools_vendor/FOSS/myvnc/1.1/manage.py --config_dir=/localdev/myvnc/config "$COMMAND"
