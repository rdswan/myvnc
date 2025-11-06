# MyVNC Server Monitor

A monitoring utility for MyVNC server that checks server health and automatically restarts it if unresponsive.

## Features

- **Health Monitoring**: Performs HTTP health checks on the MyVNC server
- **Automatic Restart**: Restarts the server if it becomes unresponsive
- **Semaphore Locking**: Prevents concurrent executions (safe for frequent cron jobs)
- **Comprehensive Logging**: All actions are logged with timestamps
- **Quiet Mode**: Perfect for cron - only logs to file, no stdout/stderr spam
- **Graceful Shutdown**: Attempts SIGTERM before SIGKILL when restarting

## Installation

1. The script is located in the `utils/` directory of the MyVNC repository.

2. You can run it directly from there, or copy it to a system location:
   ```bash
   cp utils/monitor_myvnc.py /usr/local/bin/
   chmod +x /usr/local/bin/monitor_myvnc.py
   ```

3. Ensure the `requests` module is installed:
   ```bash
   pip3 install requests
   ```

## Usage

### Basic Command

```bash
./utils/monitor_myvnc.py \
  --url https://myvnc-yyz.local.tenstorrent.com \
  --logfile /var/log/myvnc-monitor.log \
  --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config"
```

Or with full path:

```bash
/mnt/git/myvnc/utils/monitor_myvnc.py \
  --url https://myvnc-yyz.local.tenstorrent.com \
  --logfile /var/log/myvnc-monitor.log \
  --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config"
```

### For Self-Signed SSL Certificates

If your server uses a self-signed SSL certificate, add the `--no-verify-ssl` flag:

```bash
/mnt/git/myvnc/utils/monitor_myvnc.py \
  --url https://myvnc-yyz.local.tenstorrent.com \
  --logfile /var/log/myvnc-monitor.log \
  --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" \
  --no-verify-ssl
```

### Quiet Mode (for Cron)

```bash
/mnt/git/myvnc/utils/monitor_myvnc.py \
  --url https://myvnc-yyz.local.tenstorrent.com \
  --logfile /var/log/myvnc-monitor.log \
  --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" \
  --quiet
```

### Custom Timeout

```bash
/mnt/git/myvnc/utils/monitor_myvnc.py \
  --url https://myvnc-yyz.local.tenstorrent.com \
  --logfile /var/log/myvnc-monitor.log \
  --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" \
  --timeout 15
```

## Command-Line Options

| Option | Required | Description |
|--------|----------|-------------|
| `--url` | Yes | URL of the MyVNC server to monitor |
| `--logfile` | Yes | Path to log file |
| `--restart-cmd` | Yes | Command to restart the server |
| `--quiet` | No | Suppress stdout/stderr (only write to log) |
| `--timeout` | No | HTTP request timeout in seconds (default: 10) |
| `--no-verify-ssl` | No | Disable SSL certificate verification (for self-signed certs) |

## Setting Up Cron

### Check Every Minute

Edit your crontab:
```bash
crontab -e
```

Add this line (with `--no-verify-ssl` if using self-signed certificate):
```cron
* * * * * /usr/bin/python3 /mnt/git/myvnc/utils/monitor_myvnc.py --url https://myvnc-yyz.local.tenstorrent.com --logfile /var/log/myvnc-monitor.log --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" --no-verify-ssl --quiet
```

### Check Every 5 Minutes

```cron
*/5 * * * * /usr/bin/python3 /mnt/git/myvnc/utils/monitor_myvnc.py --url https://myvnc-yyz.local.tenstorrent.com --logfile /var/log/myvnc-monitor.log --restart-cmd "/tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config" --no-verify-ssl --quiet
```

### Important Note for Cron

Always use the `--quiet` flag when running from cron. This ensures:
- No stdout/stderr output that could fill up cron mail
- All logging goes to the log file
- Multiple executions won't overlap (semaphore locking)

## How It Works

### Health Check Process

1. **Acquire Lock**: Attempts to acquire an exclusive file lock (prevents concurrent runs)
2. **HTTP Check**: Sends HTTP GET request to the server URL
3. **Evaluate Response**:
   - Status 200-399 = Healthy
   - Timeout/Connection Error/4xx/5xx = Unhealthy
4. **Restart if Unhealthy**:
   - Find server process(es) using `pgrep`
   - Send SIGTERM to gracefully stop
   - Wait up to 10 seconds for termination
   - Force SIGKILL if needed
   - Start server using restart command
   - Wait up to 30 seconds for server to respond
5. **Release Lock**: Cleanup and exit

### Semaphore Locking

The monitor uses file-based locking (`fcntl.flock`) to ensure only one instance runs at a time:
- Lock file: `.<logfile_stem>.lock` in the same directory as the log file
- Non-blocking: If lock is held, the script exits immediately (exit code 0)
- PID tracking: Lock file contains the PID of the running instance

This allows you to run the monitor every minute without worrying about overlapping executions.

## Log File

The log file contains timestamped entries for all actions:

```
[2025-11-06 21:30:01] [INFO] Starting health check for https://myvnc-yyz.local.tenstorrent.com
[2025-11-06 21:30:01] [DEBUG] Checking server health: https://myvnc-yyz.local.tenstorrent.com
[2025-11-06 21:30:01] [DEBUG] Server responded with status 200
[2025-11-06 21:30:01] [INFO] ✓ Server is healthy (status: 200)
```

When a restart is triggered:

```
[2025-11-06 21:35:01] [ERROR] ✗ Server is unresponsive: Connection error: ...
[2025-11-06 21:35:01] [INFO] ================================================================================
[2025-11-06 21:35:01] [INFO] RESTARTING SERVER
[2025-11-06 21:35:01] [INFO] ================================================================================
[2025-11-06 21:35:01] [INFO] Stopping server processes: [68389]
[2025-11-06 21:35:01] [INFO] Sent SIGTERM to PID 68389
[2025-11-06 21:35:01] [INFO] Waiting for processes to terminate...
[2025-11-06 21:35:03] [INFO] All processes terminated successfully
[2025-11-06 21:35:05] [INFO] Starting server with command: /tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config
[2025-11-06 21:35:07] [INFO] Server started successfully (PID: 72451)
[2025-11-06 21:35:07] [INFO] Waiting for server to become responsive...
[2025-11-06 21:35:12] [INFO] Server is now responsive after 5 seconds
[2025-11-06 21:35:12] [INFO] ================================================================================
```

## Troubleshooting

### Script not restarting server

Check that:
1. The restart command is correct and has proper paths
2. The user running the script has permission to kill the server process
3. The log file shows what error occurred

### Lock file issues

If the lock file gets stuck (rare), you can manually remove it:
```bash
rm /var/log/.myvnc-monitor.lock
```

### Server starts but doesn't respond

- Check if there are port conflicts
- Look at the server's own logs
- Increase the `--timeout` value if your server takes longer to start

### Permission denied errors

The monitoring script needs:
- Permission to send signals (SIGTERM/SIGKILL) to the server process
- Write permission to the log file directory
- Execute permission for the restart command

## Advanced Configuration

### Custom Restart Command

You can use any command as the restart command. Examples:

**With systemd:**
```bash
--restart-cmd "systemctl restart myvnc"
```

**With custom wrapper script:**
```bash
--restart-cmd "/usr/local/bin/start-myvnc.sh"
```

**With environment variables:**
```bash
--restart-cmd "source /etc/profile && /tools_vendor/FOSS/myvnc/latest/manage.py --config_dir=/localdev/myvnc/config"
```

### Multiple Log Files

If you want to keep separate logs per day:
```bash
LOGFILE="/var/log/myvnc-monitor-$(date +%Y%m%d).log"
./monitor_myvnc.py --url ... --logfile "$LOGFILE" --restart-cmd "..." --quiet
```

### Log Rotation

Consider setting up logrotate for the monitor log:

Create `/etc/logrotate.d/myvnc-monitor`:
```
/var/log/myvnc-monitor.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 username groupname
}
```

## Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success (server healthy or restarted successfully) |
| 1 | Error (restart failed or unexpected error) |

## License

Same as MyVNC (Apache License 2.0)

