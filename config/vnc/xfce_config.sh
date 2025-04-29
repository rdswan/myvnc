#!/bin/bash
# XFCE window manager configuration for MyVNC

# Set XFCE-specific environment variables
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce

# Disable screen locking and power management
mkdir -p $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/
cat > $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml << EOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-power-manager" version="1.0">
  <property name="xfce4-power-manager" type="empty">
    <property name="power-button-action" type="empty"/>
    <property name="dpms-enabled" type="bool" value="false"/>
    <property name="blank-on-ac" type="int" value="0"/>
    <property name="lock-screen-suspend-hibernate" type="bool" value="false"/>
    <property name="logind-handle-lid-switch" type="bool" value="false"/>
    <property name="inactivity-on-ac" type="uint" value="0"/>
    <property name="lid-action-on-ac" type="uint" value="0"/>
    <property name="lid-action-on-battery" type="uint" value="0"/>
  </property>
</channel>
EOF

# Disable XFCE session saving
mkdir -p $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/
cat > $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml << EOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-session" version="1.0">
  <property name="general" type="empty">
    <property name="SaveOnExit" type="bool" value="false"/>
  </property>
  <property name="shutdown" type="empty">
    <property name="LockScreen" type="bool" value="false"/>
  </property>
</channel>
EOF

# Configure window manager for performance
mkdir -p $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/
cat > $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml << EOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="use_compositing" type="bool" value="false"/>
    <property name="show_frame_shadow" type="bool" value="false"/>
    <property name="show_popup_shadow" type="bool" value="false"/>
    <property name="theme" type="string" value="Default"/>
  </property>
</channel>
EOF

# Start XFCE session
exec startxfce4 