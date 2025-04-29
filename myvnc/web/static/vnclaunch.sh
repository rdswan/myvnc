#!/bin/bash
# VNC launcher script
# Usage: ./vnclaunch.sh rv-c-32:1

if [ -z "$1" ]; then
  echo "Error: No VNC connection string provided"
  echo "Usage: $0 hostname:display"
  exit 1
fi

CONNECTION=$1

# Try to find available VNC viewers
if command -v vncviewer >/dev/null 2>&1; then
  vncviewer $CONNECTION
elif command -v xtightvncviewer >/dev/null 2>&1; then
  xtightvncviewer $CONNECTION
elif command -v tigervnc >/dev/null 2>&1; then
  tigervnc $CONNECTION
elif command -v realvnc >/dev/null 2>&1; then
  realvnc $CONNECTION
elif [ -f /usr/bin/vncviewer ]; then
  /usr/bin/vncviewer $CONNECTION
elif [ -f /usr/local/bin/vncviewer ]; then
  /usr/local/bin/vncviewer $CONNECTION
else
  echo "No VNC viewer found on your system"
  echo "Please connect manually to $CONNECTION"
  exit 1
fi 