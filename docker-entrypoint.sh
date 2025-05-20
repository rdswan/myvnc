#!/bin/bash
set -e

# Create ~/.vnc directory for VNC user
mkdir -p ~/.vnc

# Copy the xstartup file to user's vnc directory if it doesn't exist
if [ ! -f ~/.vnc/xstartup ]; then
    cp /app/config/vnc/xstartup.sh ~/.vnc/xstartup
    chmod +x ~/.vnc/xstartup
fi

# Make sure logs and data directories exist and are writable
sudo mkdir -p /localdev/myvnc/logs /localdev/myvnc/data
sudo chown -R $(whoami) /localdev/myvnc

# Update server configuration to use correct host
if [ -f /app/config/server_config.json ]; then
    # Replace the hostname with the container's hostname or the provided value
    if [ -n "$MYVNC_HOSTNAME" ]; then
        sed -i "s/\"host\":.*/\"host\": \"$MYVNC_HOSTNAME\",/" /app/config/server_config.json
    else
        sed -i "s/\"host\":.*/\"host\": \"$(hostname)\",/" /app/config/server_config.json
    fi
    
    # Set the port to what we expose (9123)
    sed -i "s/\"port\":.*/\"port\": 9123,/" /app/config/server_config.json
    
    # Update paths if necessary
    sed -i "s|\"datadir\":.*|\"datadir\": \"/localdev/myvnc/data\",|" /app/config/server_config.json
    sed -i "s|\"logdir\":.*|\"logdir\": \"/localdev/myvnc/logs\",|" /app/config/server_config.json
fi

# Make sure VNC config points to the right places
if [ -f /app/config/vnc_config.json ]; then
    # Update paths to xstartup and window manager configs
    sed -i "s|\"vncserver_path\":.*|\"vncserver_path\": \"/usr/bin/vncserver\",|" /app/config/vnc_config.json
    sed -i "s|\"xstartup_path\":.*|\"xstartup_path\": \"/home/vncuser/.vnc/xstartup\",|" /app/config/vnc_config.json
    
    # Update window manager config paths
    sed -i "s|\"gnome\":.*|\"gnome\": \"/app/config/vnc/gnome_config.sh\",|" /app/config/vnc_config.json
    sed -i "s|\"kde\":.*|\"kde\": \"/app/config/vnc/kde_config.sh\",|" /app/config/vnc_config.json
    sed -i "s|\"xfce\":.*|\"xfce\": \"/app/config/vnc/xfce_config.sh\",|" /app/config/vnc_config.json
    sed -i "s|\"mate\":.*|\"mate\": \"/app/config/vnc/mate_config.sh\",|" /app/config/vnc_config.json
fi

# Check if we need to update LSF config
if [ -f /app/config/lsf_config.json ]; then
    # If LSF_ENV_FILE environment variable is set, use it
    if [ -n "$LSF_ENV_FILE" ]; then
        sed -i "s|\"env_file\":.*|\"env_file\": \"$LSF_ENV_FILE\"|" /app/config/lsf_config.json
    else
        # Use a default that doesn't rely on a specific path
        sed -i "s|\"env_file\":.*|\"env_file\": \"/etc/profile.d/lsf.sh\"|" /app/config/lsf_config.json
    fi
fi

# Execute the command provided as arguments (CMD in Dockerfile)
exec "$@" 