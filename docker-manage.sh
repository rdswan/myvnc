#!/bin/bash

# Script to manage Docker container operations for MyVNC

set -e  # Exit on errors

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"  # Ensure we're in the right directory

# Functions
show_help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start       - Start the MyVNC container"
    echo "  stop        - Stop the MyVNC container"
    echo "  restart     - Restart the MyVNC container"
    echo "  status      - Show status of the MyVNC container"
    echo "  logs        - Show logs of the MyVNC container"
    echo "  build       - Rebuild the MyVNC container"
    echo "  shell       - Get a shell inside the MyVNC container"
    echo "  help        - Show this help"
    echo ""
}

start_container() {
    echo "Starting MyVNC container..."
    docker compose up -d
    echo "Container started. Access MyVNC at: http://localhost:9123"
}

stop_container() {
    echo "Stopping MyVNC container..."
    docker compose down
    echo "Container stopped."
}

restart_container() {
    echo "Restarting MyVNC container..."
    docker compose restart
    echo "Container restarted."
}

show_status() {
    echo "MyVNC container status:"
    docker compose ps
    
    # Check if container is running
    if docker compose ps | grep -q "Up"; then
        # Show running container details
        CONTAINER_ID=$(docker compose ps -q)
        echo ""
        echo "Container details:"
        docker inspect --format "{{.Name}} - {{.State.Status}} - Started: {{.State.StartedAt}}" $CONTAINER_ID
        echo ""
        echo "Access URL: http://localhost:9123"
    fi
}

show_logs() {
    echo "MyVNC container logs:"
    docker compose logs --tail=50 -f
}

build_container() {
    echo "Building MyVNC container..."
    docker compose build
    echo "Container built."
}

get_shell() {
    echo "Opening shell in MyVNC container..."
    docker compose exec myvnc bash
}

# Main logic
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

case "$1" in
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    build)
        build_container
        ;;
    shell)
        get_shell
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

exit 0 
