FROM python:3.9-slim

# Install system dependencies including VNC server and window managers
RUN apt-get update && apt-get install -y \
    tigervnc-standalone-server \
    tigervnc-common \
    gnome-session \
    xfce4 \
    mate-desktop-environment-core \
    kde-plasma-desktop \
    net-tools \
    procps \
    curl \
    xterm \
    python3-ldap \
    vim \
    sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the application files
COPY . /app/

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create needed directories
RUN mkdir -p /localdev/myvnc/data /localdev/myvnc/logs

# Expose the port (default in the config file is 9123)
EXPOSE 9123

# Set environment variables 
ENV PYTHONPATH=/app
ENV MYVNC_CONFIG_DIR=/app/config

# Create a non-root user for running vnc and the app
RUN useradd -m -s /bin/bash vncuser && \
    echo "vncuser ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Set up the entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Switch to non-root user for better security
USER vncuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "run_server.py", "--host", "0.0.0.0", "--port", "9123"] 