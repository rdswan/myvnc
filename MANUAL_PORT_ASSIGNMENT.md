# Manual Port Assignment Feature

This feature was added to avoid unnecessary SSH calls when determining the display number for a VNC server. By manually assigning a display number at server invocation time, we can extract that information directly from the command stored in the bjobs output, eliminating the need for SSH calls in many cases.

## Implementation Details

### 1. Random Display Number Assignment

The system now randomly assigns a display number between 500 and 999 when creating a new VNC server. This range was chosen to avoid conflicts with other VNC servers that might be running on the system.

```python
# Randomly pick a display number between 500 and 999
import random
display_num = random.randint(500, 999)
```

### 2. Fallback to Free Port

To handle cases where the randomly assigned display is already in use, we've added the `-fallbacktofreeport` switch to the vncserver command. This ensures that the VNC server will still start successfully by using another available port if needed.

```
vncserver_cmd.append('-fallbacktofreeport')
```

### 3. Display Detection Logic

The system now uses a tiered approach for determining the display number:

1. **First attempt**: Extract the display number directly from the bjobs command output
   - Searches for a pattern like `:123` in the command string
   - If found, uses this number without making an SSH call

2. **Fallback**: Only if the display number isn't found in the command, an SSH call is made to the host machine
   - Connects to the remote machine
   - Searches for Xvnc processes to determine the display number

### 4. Benefits

- **Reduced Latency**: Faster connection to VNC servers by avoiding SSH calls
- **Reduced Network Traffic**: Fewer SSH connections to remote machines
- **Improved Reliability**: Less dependency on SSH connectivity to determine VNC server details
- **More Predictable Display Numbers**: The large range (500-999) reduces the chance of conflicts

## How It Works

When a user creates a new VNC server:

1. The system generates a random display number between 500 and 999
2. The vncserver command is constructed with this display number at the beginning
3. The `-fallbacktofreeport` switch is added to ensure the server starts even if the port is taken
4. When retrieving the VNC server details, the system first checks if the display number can be extracted from the command output
5. Only if the display number isn't found in the command, an SSH call is made to determine it

## Technical Implementation

The changes were made to the following files:

1. `myvnc/utils/lsf_manager.py`:
   - Modified `submit_vnc_job()` to assign a random display number and add -fallbacktofreeport
   - Modified `get_active_vnc_jobs()` to check for display number in command output before SSH
   - Modified `get_vnc_connection_details()` to follow the same pattern

These changes maintain backward compatibility while improving efficiency. 