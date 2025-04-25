from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QComboBox, QPushButton, QSpinBox,
                             QFormLayout, QMessageBox)
from PyQt6.QtCore import Qt
from ..utils.lsf_manager import LSFManager

class VNCreatorTab(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.lsf_manager = LSFManager()
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # VNC Settings
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter VNC session name")
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(self.config_manager.get_available_resolutions())
        
        self.wm_combo = QComboBox()
        self.wm_combo.addItems(self.config_manager.get_available_window_managers())
        
        # LSF Settings
        self.queue_combo = QComboBox()
        self.queue_combo.addItems(self.config_manager.get_available_queues())
        
        self.cores_spin = QSpinBox()
        self.cores_spin.setRange(1, 32)
        self.cores_spin.setValue(self.config_manager.get_lsf_defaults()['num_cores'])
        
        self.memory_combo = QComboBox()
        self.memory_combo.addItems([str(x) for x in self.config_manager.get_memory_options()])
        
        # Add fields to form
        form_layout.addRow("Session Name:", self.name_input)
        form_layout.addRow("Resolution:", self.resolution_combo)
        form_layout.addRow("Window Manager:", self.wm_combo)
        form_layout.addRow("LSF Queue:", self.queue_combo)
        form_layout.addRow("Number of Cores:", self.cores_spin)
        form_layout.addRow("Memory (GB):", self.memory_combo)
        
        # Create submit button
        self.submit_button = QPushButton("Create VNC Session")
        self.submit_button.clicked.connect(self.create_vnc_session)
        
        # Add layouts to main layout
        layout.addLayout(form_layout)
        layout.addWidget(self.submit_button)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def create_vnc_session(self):
        # Validate inputs
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Error", "Please enter a session name")
            return
        
        # Prepare VNC configuration
        vnc_config = {
            'name': self.name_input.text().strip(),
            'resolution': self.resolution_combo.currentText(),
            'window_manager': self.wm_combo.currentText(),
            'color_depth': 24,  # Default color depth
            'vncserver_path': self.config_manager.get_vnc_defaults().get('vncserver_path', '/usr/bin/vncserver')
        }
        
        # Prepare LSF configuration
        lsf_config = {
            'queue': self.queue_combo.currentText(),
            'num_cores': self.cores_spin.value(),
            'memory_gb': int(self.memory_combo.currentText())
        }
        
        try:
            job_id = self.lsf_manager.submit_vnc_job(vnc_config, lsf_config)
            QMessageBox.information(self, "Success", 
                                  f"VNC session created successfully!\nJob ID: {job_id}")
            
            # Clear inputs
            self.name_input.clear()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create VNC session: {str(e)}") 