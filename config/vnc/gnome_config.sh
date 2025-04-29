#!/bin/bash
# GNOME window manager configuration for MyVNC

# Set GNOME-specific environment variables
export XDG_SESSION_TYPE=x11
export GDK_BACKEND=x11

# Disable screen lock and power management
gsettings set org.gnome.desktop.lockdown disable-lock-screen true
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.session idle-delay 0

# Set GNOME theme preferences
gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita'
gsettings set org.gnome.desktop.interface icon-theme 'Adwaita'
gsettings set org.gnome.desktop.wm.preferences theme 'Adwaita'

# Enable minimize/maximize buttons
gsettings set org.gnome.desktop.wm.preferences button-layout 'appmenu:minimize,maximize,close'

# Disable animation for better performance over VNC
gsettings set org.gnome.desktop.interface enable-animations false

# Start GNOME session
exec gnome-session 