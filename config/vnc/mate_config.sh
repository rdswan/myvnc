#!/bin/bash
# MATE window manager configuration for MyVNC

# Set MATE-specific environment variables
export XDG_CURRENT_DESKTOP=MATE
export DESKTOP_SESSION=mate

# Disable screen locking and power management
gsettings set org.mate.power-manager sleep-display-ac 0
gsettings set org.mate.power-manager sleep-display-battery 0
gsettings set org.mate.power-manager idle-dim-ac false
gsettings set org.mate.power-manager idle-dim-battery false
gsettings set org.mate.session idle-delay 0
gsettings set org.mate.screensaver lock-enabled false
gsettings set org.mate.screensaver idle-activation-enabled false

# Configure theme for performance
gsettings set org.mate.Marco.general compositing-manager false
gsettings set org.mate.Marco.general reduced-resources true
gsettings set org.mate.interface gtk-theme 'Menta'
gsettings set org.mate.interface icon-theme 'menta'

# Disable unnecessary services
gsettings set org.mate.desktop.background show-desktop-icons true
gsettings set org.mate.Marco.general show-minimized-windows true

# MATE panel configuration
gsettings set org.mate.panel.toplevels.top auto-hide false
gsettings set org.mate.panel.toplevels.top expand true

# Start MATE session
exec mate-session 