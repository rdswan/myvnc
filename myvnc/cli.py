import click
from .vnc_manager import VNCManager, VNCServer
from tabulate import tabulate

@click.group()
def cli():
    """VNC Manager CLI"""
    pass

@cli.command()
@click.option('--name', required=True, help='Name of the VNC server')
@click.option('--host', required=True, help='Host to connect to')
@click.option('--display', type=int, required=True, help='Display number')
@click.option('--resolution', default='1024x768', help='Screen resolution')
@click.option('--window-manager', default='gnome', help='Window manager to use')
def start(name, host, display, resolution, window_manager):
    """Start a new VNC server"""
    vnc_manager = VNCManager()
    server = VNCServer(
        name=name,
        host=host,
        port=5900 + display,
        display=display,
        resolution=resolution,
        window_manager=window_manager
    )
    
    if vnc_manager.start_server(server):
        click.echo(f"Successfully started VNC server {name}")
    else:
        click.echo(f"Failed to start VNC server {name}", err=True)

@cli.command()
@click.argument('name')
def stop(name):
    """Stop a VNC server by name"""
    vnc_manager = VNCManager()
    server = vnc_manager.get_server_by_name(name)
    
    if server and vnc_manager.stop_server(server):
        click.echo(f"Successfully stopped VNC server {name}")
    else:
        click.echo(f"Failed to stop VNC server {name}", err=True)

@cli.command()
def list():
    """List all VNC servers"""
    vnc_manager = VNCManager()
    servers = vnc_manager.list_servers()
    
    if not servers:
        click.echo("No VNC servers running")
        return
    
    headers = ['Name', 'Host', 'Display', 'Resolution', 'Status']
    table_data = []
    
    for server in servers:
        this_server = vnc_manager.get_server_by_name(server['name'])
        status = 'Running' if this_server and vnc_manager.is_server_running(this_server) else 'Stopped'
        table_data.append([
            server['name'],
            server['host'],
            server['display'],
            server['resolution'],
            status
        ])
    
    click.echo(tabulate(table_data, headers=headers, tablefmt='grid'))

def main():
    cli() 