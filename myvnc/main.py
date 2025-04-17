import sys
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PyQt6.QtCore import Qt

from .gui.vnc_manager_tab import VNCManagerTab
from .gui.vnc_creator_tab import VNCreatorTab
from .utils.config_manager import ConfigManager

class MyVNCApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyVNC Manager")
        self.setMinimumSize(800, 600)
        
        # Initialize configuration
        self.config_manager = ConfigManager()
        
        # Create main widget and layout
        self.central_widget = QTabWidget()
        self.setCentralWidget(self.central_widget)
        
        # Create tabs
        self.vnc_manager_tab = VNCManagerTab(self.config_manager)
        self.vnc_creator_tab = VNCreatorTab(self.config_manager)
        
        # Add tabs to widget
        self.central_widget.addTab(self.vnc_manager_tab, "VNC Manager")
        self.central_widget.addTab(self.vnc_creator_tab, "Create VNC")

def main():
    app = QApplication(sys.argv)
    window = MyVNCApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 