#!/bin/bash
# XFCE window manager configuration for MyVNC

# Set XFCE-specific environment variables
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce

# Disable screensaver and all lock screen features
mkdir -p $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/
cat > $HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-screensaver.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>

<channel name="xfce4-screensaver" version="1.0">
  <property name="lock" type="empty">
    <property name="sleep-activation" type="bool" value="false"/>
    <property name="enabled" type="bool" value="false"/>
    <property name="saver-activation" type="empty">
      <property name="enabled" type="bool" value="false"/>
    </property>
    <property name="user-switching" type="empty">
      <property name="enabled" type="bool" value="false"/>
    </property>
    <property name="status-messages" type="empty">
      <property name="enabled" type="bool" value="false"/>
    </property>
  </property>
  <property name="saver" type="empty">
    <property name="mode" type="int" value="0"/>
  </property>
</channel>
EOF

# Disable power management
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


## Time to disable a ton of start that xfce autostarts and its total crap for us...
# Define the target directory
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

DISABLE_LIST=(
    "geoclue-demo-agent.desktop"
    "tracker-extract.desktop"
    "tracker-miner-apps.desktop"
    "tracker-miner-fs.desktop"
    "tracker-store.desktop"
    "xdg-user-dirs.desktop"
    "xfce4-power-manager.desktop"
    "xfce4-screensaver.desktop"
    "xfce-polkit.desktop"
)

for file in "${DISABLE_LIST[@]}"; do
    cat > "$AUTOSTART_DIR/$file" << EOF
[Desktop Entry]
Hidden=true
EOF
    echo "Disabled: $file"
done

echo "All specified autostart entries have been disabled."

# Disable screensaver and lock screen via xfconf-query after the session starts
# (needs a running xfconf daemon, so we background it with a delay)
(sleep 5 && \
 xfconf-query -c xfce4-screensaver -p /lock/enabled -s false 2>/dev/null; \
 xfconf-query -c xfce4-screensaver -p /screensaver/enabled -s false 2>/dev/null; \
 echo "Screensaver and lock screen disabled via xfconf-query") &

# Start XFCE session
exec startxfce4 
