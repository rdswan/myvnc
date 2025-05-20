# MyVNC Docker Containerization

This document describes how to run the MyVNC application in a Docker container, providing an isolated and portable environment.

## Prerequisites

- Docker installed on your system
- Docker Compose installed on your system
- Basic understanding of Docker concepts

## Quick Start

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd myvnc
   ```

2. Build and start the container:
   ```bash
   docker-compose up -d
   ```

3. Access the application at:
   ```
   http://<your-host-ip>:9123
   ```

## Configuration

### Environment Variables

You can customize the container by setting these environment variables:

- `MYVNC_HOSTNAME`: The hostname to use for the application (default: myvnc.local)
- `LSF_ENV_FILE`: Path to the LSF environment file (default: /etc/profile.d/lsf.sh)

You can set these in a `.env` file in the same directory as the docker-compose.yml file:

```
MYVNC_HOSTNAME=myvnc.example.com
LSF_ENV_FILE=/path/to/lsf.sh
```

### Persistent Data

The Docker Compose file sets up two volumes for persistent data:

- `myvnc_data`: Stores application data
- `myvnc_logs`: Stores application logs

These volumes persist even when the container is stopped or removed.

### Custom Configuration

The `config` directory is mounted into the container, allowing you to modify configuration files without rebuilding the image:

1. Edit any file in the `config` directory
2. Restart the container:
   ```bash
   docker-compose restart
   ```

## VNC Port Mapping

The Docker Compose file maps VNC ports in the range 6400-6499, corresponding to VNC displays 500-599. If you need a different range, modify the `ports` section in the docker-compose.yml file.

## Troubleshooting

### Viewing Logs

To view container logs:
```bash
docker-compose logs -f
```

### Container Shell Access

To open a shell inside the container:
```bash
docker-compose exec myvnc bash
```

### Permission Issues

If you encounter permission issues, make sure the `vncuser` inside the container has proper permissions:
```bash
docker-compose exec myvnc sudo chown -R vncuser:vncuser /localdev/myvnc
```

## Advanced Configuration

### Using Host Network Mode

If you need direct network access from the VNC sessions, you can use host network mode by uncommenting the `network_mode: "host"` line in docker-compose.yml. This will give the container direct access to the host's network stack.

### Security Considerations

- The container runs as a non-root user (`vncuser`) for better security
- The container requires `privileged: true` for the VNC server to work correctly
- Consider enabling SSL by providing certificates in the configuration

## Building for Different Environments

To build for different environments, create separate docker-compose override files:

**docker-compose.prod.yml**:
```yaml
services:
  myvnc:
    environment:
      - MYVNC_HOSTNAME=myvnc.production.com
```

Then run:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
``` 