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

## Capture the LSF job ID so it's available in the desktop session
export MYVNC_JOBID="${LSB_JOBID}"

## Need to unset these if theyre defined so that we can start a new session up
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Uncomment to enable debug output
# set -x
exec >> "$HOME/.vnc/xstartup.${HOSTNAME}${DISPLAY}.log" 2>&1
echo "Starting VNC session at $(date)"

# Per-cgroup early-OOM watcher: kills the largest non-protected child before
# LSF's OOM killer takes down the whole job (and Xvnc with it).
# Controlled by the "cgroup_earlyoom" block in server_config.json:
#   "enabled": true/false   -- launch the watcher (default: false)
#   "pretend": true/false   -- dry-run mode, log but don't kill (default: false)
SCRIPT_ROOT="$(dirname "$(readlink -f "$0")")"
EARLYOOM_SH="${SCRIPT_ROOT}/../../utils/cgroup_earlyoom.sh"
SERVER_CFG="${SCRIPT_ROOT}/../../config/server_config.json"

# Read earlyoom settings from server_config.json (default: disabled).
EARLYOOM_ENABLED=false
EARLYOOM_PRETEND_CFG=false
if [ -r "$SERVER_CFG" ]; then
    if command -v python3 >/dev/null 2>&1; then
        EARLYOOM_ENABLED=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$SERVER_CFG'))
    print(str(cfg.get('cgroup_earlyoom', {}).get('enabled', False)).lower())
except Exception:
    print('false')
" 2>/dev/null)
        EARLYOOM_PRETEND_CFG=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$SERVER_CFG'))
    print(str(cfg.get('cgroup_earlyoom', {}).get('pretend', False)).lower())
except Exception:
    print('false')
" 2>/dev/null)
    else
        echo "WARNING: python3 not found; cannot read cgroup_earlyoom config"
    fi
fi

if [ "$EARLYOOM_ENABLED" = "true" ]; then
    if [ -x "$EARLYOOM_SH" ]; then
        EARLYOOM_ARGS=""
        if [ "$EARLYOOM_PRETEND_CFG" = "true" ]; then
            EARLYOOM_ARGS="--pretend"
            echo "Launching cgroup_earlyoom watcher in PRETEND mode: $EARLYOOM_SH"
        else
            echo "Launching cgroup_earlyoom watcher: $EARLYOOM_SH"
        fi
        nohup "$EARLYOOM_SH" $EARLYOOM_ARGS \
            > "$HOME/.vnc/cgroup_earlyoom.${HOSTNAME}${DISPLAY}.log" 2>&1 &
        disown
    else
        echo "WARNING: cgroup_earlyoom.sh not found or not executable at $EARLYOOM_SH"
    fi
else
    echo "cgroup_earlyoom watcher is disabled in server_config.json (cgroup_earlyoom.enabled=false)"
fi

## disable screensaver and any lockscreen
xset -dpms
xset s off
xset s 0 0
xset s noblank
## print out verification that these settings are in place
echo "These are the screen saver settings which should be all off: "
xset q

# Set basic X settings
touch $HOME/.Xresources
xrdb $HOME/.Xresources
xsetroot -solid grey
vncconfig -iconic &

# Preserve SSH agent forwarding inside the VNC desktop.
if [ -n "$SSH_AUTH_SOCK" ] && [ -S "$SSH_AUTH_SOCK" ]; then
    export SSH_AUTH_SOCK
else
    for sock in /tmp/ssh-*/agent.*; do
        if [ -S "$sock" ]; then
            SSH_AUTH_SOCK="$sock"
            export SSH_AUTH_SOCK
            break
        fi
    done
fi

# Get window manager from the command line or use default
WM="${WINDOW_MANAGER:-xfce}"
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
        none)
            xterm -geometry 80x24+10+10 -ls &
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
