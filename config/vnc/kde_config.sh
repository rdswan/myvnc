#!/bin/bash
# KDE window manager configuration for MyVNC

# Set KDE-specific environment variables
export KDE_FULL_SESSION=true
export DESKTOP_SESSION=plasma
export XDG_CURRENT_DESKTOP=KDE

# Disable screen locking and power management
mkdir -p $HOME/.config/kscreenlockerrc
cat > $HOME/.config/kscreenlockerrc << EOF
[Daemon]
Autolock=false
LockOnResume=false
EOF

# Disable compositor effects for better VNC performance
mkdir -p $HOME/.config/kwinrc
cat > $HOME/.config/kwinrc << EOF
[Compositing]
Enabled=false
OpenGLIsUnsafe=true
EOF

# Disable animations
mkdir -p $HOME/.config/kdeglobals
cat >> $HOME/.config/kdeglobals << EOF
[KDE]
AnimationDurationFactor=0
EOF

# Start KDE Plasma
if command -v startkde >/dev/null 2>&1; then
    exec startkde
elif command -v startplasma-x11 >/dev/null 2>&1; then
    exec startplasma-x11
else
    echo "KDE Plasma startup command not found."
    exit 1
fi 