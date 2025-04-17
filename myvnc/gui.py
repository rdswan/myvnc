from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QTableWidget, QTableWidgetItem, QMessageBox,
                             QFormLayout, QSpinBox, QComboBox)
from PyQt6.QtCore import Qt, QTimer
from .vnc_manager import VNCManager, VNCServer
import sys

class VNCManagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.vnc_manager = VNCManager()
        self.init_ui()
        
        # Update server list every 5 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_server_list)
        self.timer.start(5000)

    def init_ui(self):
        self.setWindowTitle('VNC Manager')
        self.setGeometry(100, 100, 800, 600)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Server list
        self.server_table = QTableWidget()
        self.server_table.setColumnCount(5)
        self.server_table.setHorizontalHeaderLabels(['Name', 'Host', 'Display', 'Resolution', 'Status'])
        layout.addWidget(self.server_table)

        # New server form
        form_group = QWidget()
        form_layout = QFormLayout(form_group)
        
        self.name_input = QLineEdit()
        self.host_input = QLineEdit()
        self.display_input = QSpinBox()
        self.display_input.setRange(1, 99)
        self.resolution_input = QComboBox()
        self.resolution_input.addItems(['1024x768', '1280x1024', '1920x1080'])
        self.window_manager_input = QComboBox()
        self.window_manager_input.addItems(['gnome', 'kde', 'xfce'])

        form_layout.addRow('Name:', self.name_input)
        form_layout.addRow('Host:', self.host_input)
        form_layout.addRow('Display:', self.display_input)
        form_layout.addRow('Resolution:', self.resolution_input)
        form_layout.addRow('Window Manager:', self.window_manager_input)

        layout.addWidget(form_group)

        # Buttons
        button_layout = QHBoxLayout()
        start_button = QPushButton('Start Server')
        start_button.clicked.connect(self.start_server)
        stop_button = QPushButton('Stop Server')
        stop_button.clicked.connect(self.stop_server)
        
        button_layout.addWidget(start_button)
        button_layout.addWidget(stop_button)
        layout.addLayout(button_layout)

        self.update_server_list()

    def update_server_list(self):
        servers = self.vnc_manager.list_servers()
        self.server_table.setRowCount(len(servers))
        
        for i, server in enumerate(servers):
            self.server_table.setItem(i, 0, QTableWidgetItem(server['name']))
            self.server_table.setItem(i, 1, QTableWidgetItem(server['host']))
            this_server = self.vnc_manager.get_server_by_name(server['name'])
            status = 'Running' if this_server and self.vnc_manager.is_server_running(this_server) else 'Stopped'
            self.server_table.setItem(i, 2, QTableWidgetItem(str(server['display'])))
            self.server_table.setItem(i, 3, QTableWidgetItem(server['resolution']))
            self.server_table.setItem(i, 4, QTableWidgetItem(status))

    def start_server(self):
        name = self.name_input.text()
        host = self.host_input.text()
        display = self.display_input.value()
        resolution = self.resolution_input.currentText()
        window_manager = self.window_manager_input.currentText()

        if not name or not host:
            QMessageBox.warning(self, 'Error', 'Please fill in all required fields')
            return

        server = VNCServer(
            name=name,
            host=host,
            port=5900 + display,
            display=display,
            resolution=resolution,
            window_manager=window_manager
        )

        if self.vnc_manager.start_server(server):
            QMessageBox.information(self, 'Success', f'VNC server {name} started successfully')
            self.update_server_list()
        else:
            QMessageBox.critical(self, 'Error', 'Failed to start VNC server')

    def stop_server(self):
        current_row = self.server_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, 'Error', 'Please select a server to stop')
            return

        server_name = self.server_table.item(current_row, 0).text()
        server = self.vnc_manager.get_server_by_name(server_name)
        
        if server and self.vnc_manager.stop_server(server):
            QMessageBox.information(self, 'Success', f'VNC server {server_name} stopped successfully')
            self.update_server_list()
        else:
            QMessageBox.critical(self, 'Error', 'Failed to stop VNC server')

def run_gui():
    app = QApplication(sys.argv)
    window = VNCManagerGUI()
    window.show()
    sys.exit(app.exec()) 