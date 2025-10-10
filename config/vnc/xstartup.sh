#!/bin/bash
# MyVNC custom xstartup script for VNC server
# This script is automatically used when starting a VNC session

# Load system-wide environment
if [ -f /etc/profile ]; then
    source /etc/profile
fi

# Load user profile
if [ -f "$HOME/.profile" ]; then
    source "$HOME/.profile"
elif [ -f "$HOME/.bash_profile" ]; then
    source "$HOME/.bash_profile"
fi

## Need to unset these if theyre defined so that we can start a new session up
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Uncomment to enable debug output
# set -x
exec >> "$HOME/.vnc/xstartup.log" 2>&1
echo "Starting VNC session at $(date)"

# Set basic X settings
touch $HOME/.Xresources
xrdb $HOME/.Xresources
xsetroot -solid grey
vncconfig -iconic &

# Get window manager from the command line or use default
WM="${WINDOW_MANAGER:-gnome}"
echo "Using window manager: $WM"

# Get script directory - this is where the window manager configs are located
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
echo "Script directory: $SCRIPT_DIR"

# Load window manager specific configuration if available
WM_CONFIG="${SCRIPT_DIR}/${WM}_config.sh"
if [ -f "$WM_CONFIG" ]; then
    echo "Loading window manager config from $WM_CONFIG"
    source "$WM_CONFIG"
else
    echo "Window manager config not found: $WM_CONFIG"
    
    # Default fallback based on window manager
    case "$WM" in
        gnome)
            export XDG_SESSION_TYPE=x11
            export GDK_BACKEND=x11
            exec gnome-session
            ;;
        kde)
            exec startkde
            ;;
        xfce)
            exec startxfce4
            ;;
        mate)
            exec mate-session
            ;;
        *)
            echo "Unknown window manager: $WM, falling back to TWM"
            xterm -geometry 80x24+10+10 -ls -title "$VNCDESKTOP Desktop" &
            twm
            ;;
    esac
fi

# This should not be reached if a window manager is correctly started
echo "ERROR: Window manager failed to start properly at $(date)"
xterm -geometry 80x24+10+10 -ls -title "VNC Error" &
twm 
