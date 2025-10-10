# Singularity Container Directory

This directory contains singularity containers used for different OS environments in myvnc.

## Current Containers

### RedHat 9.6 (`rh9_6.sif`)

This container provides a RedHat 9.6 (Rocky Linux 9) environment for VNC sessions with full desktop environments and development tools.

**Container Contents:**
- TigerVNC server
- Multiple desktop environments (GNOME, XFCE, MATE)
- Development tools (gcc, g++, make, cmake, autotools)
- Python 3 with pip
- Common editors (vim, emacs, nano)
- Firefox browser and gedit editor
- All necessary fonts and X11 libraries
- NFS client utilities
- Pre-created mount points for NFS directories

**Building the container:**

Build from the provided definition file:
```bash
cd /home/bswan/tools_src/myvnc/containers
sudo singularity build --force rh9_6.sif rh9_6.def
```

**Container Size:** ~842 MB

**NFS Mount Support:**
When the container is launched by myvnc, **all NFS and WekaFS mounts are automatically detected and bound** from the host. The system uses `df -T /* | egrep 'wekafs|nfs' | grep -v truenas` to dynamically discover mount points at runtime (excluding truenas mounts).

This gives you seamless access to all filesystems including:
- Project directories (e.g., `/proj_risc`, `/proj_pd`, `/proj_soc`)
- Tool directories (e.g., `/tools_vendor`, `/tools_risc`, `/tools_soc`)
- Site directories (`/site`, `/tech`)
- Home directories (`/home`)
- Scratch spaces (e.g., `/weka_scratch`, `/proj_perf_scratch`)
- Vendor IP directories (`/vendor_ip`)
- Any other NFS/WekaFS mounts available on the compute node

No manual configuration needed - if it's mounted on the host, it's available in the container!

## Configuration

Containers are configured in `config/lsf_config.json` under the `os_options` array. Each OS option can optionally include a `container` field:

```json
{
  "name": "RedHat 9.6",
  "select": "rh96",
  "container": "containers/rh9_6.sif"
}
```

When a container is specified:
- The LSF job submission will wrap the vncserver command with `singularity exec`
- The vncserver will run inside the specified container environment
- The host's LSF scheduling constraints (specified by the `select` field) still apply

## Adding New Containers

To add a new containerized OS option:

1. Build or copy your singularity container to this directory
2. Add an entry to `config/lsf_config.json` in the `os_options` array:
   ```json
   {
     "name": "Your OS Name",
     "select": "lsf_select_string",
     "container": "containers/your_container.sif"
   }
   ```
3. Restart the myvnc server to pick up the new configuration

## Notes

- Container paths are relative to the myvnc installation root
- The `select` field is still used for LSF resource selection
- Users will see the OS option in the web UI and can select it when creating VNC sessions
- The container wrapping happens automatically at job submission time

