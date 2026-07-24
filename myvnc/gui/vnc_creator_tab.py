# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QComboBox, QPushButton, QSpinBox,
                             QFormLayout, QMessageBox)
from PyQt6.QtCore import Qt
from ..utils.lsf_manager import LSFManager
from ..utils.slurm_manager import SLURMManager


def _get_job_manager(config_manager):
    """Get the appropriate job manager based on scheduler configuration"""
    if config_manager.get_scheduler_type() == 'slurm':
        return SLURMManager()
    return LSFManager()


class VNCreatorTab(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.lsf_manager = _get_job_manager(config_manager)
        
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
        
        # Scheduler Settings (queues/partitions)
        self.scheduler_type = self.config_manager.get_scheduler_type()
        self.queue_combo = QComboBox()
        if self.scheduler_type == 'slurm':
            self.queue_combo.addItems(self.config_manager.get_available_partitions())
        else:
            self.queue_combo.addItems(self.config_manager.get_available_queues())
        
        self.cores_spin = QSpinBox()
        self.cores_spin.setRange(1, 32)
        
        self.memory_combo = QComboBox()
        
        # Populate cores/memory for the initially selected queue and react to
        # queue changes so per-queue defaults/options take effect.
        self._apply_queue_settings(self.queue_combo.currentText())
        self.queue_combo.currentTextChanged.connect(self._apply_queue_settings)
        
        scheduler_type = self.scheduler_type
        # Add fields to form
        queue_label = "SLURM Partition:" if scheduler_type == 'slurm' else "LSF Queue:"
        form_layout.addRow("Session Name:", self.name_input)
        form_layout.addRow("Resolution:", self.resolution_combo)
        form_layout.addRow("Window Manager:", self.wm_combo)
        form_layout.addRow(queue_label, self.queue_combo)
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

    def _apply_queue_settings(self, queue):
        """Populate cores/memory options and defaults for the selected queue.

        Uses per-queue overrides from queue_settings when present, otherwise the
        global options (fully backward compatible).
        """
        if not queue:
            return

        scheduler_defaults = self.config_manager.get_scheduler_defaults(queue=queue)

        if self.scheduler_type == 'slurm':
            memory_options = self.config_manager.get_slurm_memory_options(queue)
        else:
            memory_options = self.config_manager.get_memory_options(queue)

        # Repopulate the memory combo, preserving the previous selection if valid
        previous_memory = self.memory_combo.currentText()
        self.memory_combo.blockSignals(True)
        self.memory_combo.clear()
        self.memory_combo.addItems([str(x) for x in memory_options])
        self.memory_combo.blockSignals(False)

        default_memory = str(scheduler_defaults.get('memory_gb', ''))
        target_memory = previous_memory if previous_memory in [str(x) for x in memory_options] else default_memory
        idx = self.memory_combo.findText(target_memory)
        if idx >= 0:
            self.memory_combo.setCurrentIndex(idx)

        # Update the default core count for this queue
        self.cores_spin.setValue(scheduler_defaults.get('num_cores', 2))

    def create_vnc_session(self):
        # Validate inputs
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Error", "Please enter a session name")
            return
        
        # Prepare VNC configuration
        vnc_defaults = self.config_manager.get_vnc_defaults()
        vnc_config = {
            'name': self.name_input.text().strip(),
            'resolution': self.resolution_combo.currentText(),
            'window_manager': self.wm_combo.currentText(),
            'color_depth': 24,
            'vncserver_path': vnc_defaults.get('vncserver_path', '/usr/bin/vncserver'),
            'vncserver_wrapper_path': vnc_defaults.get('vncserver_wrapper_path')
        }
        
        # Prepare scheduler configuration (resolve per-queue defaults)
        selected_queue = self.queue_combo.currentText()
        scheduler_defaults = self.config_manager.get_scheduler_defaults(queue=selected_queue)
        lsf_config = {
            'queue': self.queue_combo.currentText(),
            'partition': self.queue_combo.currentText(),
            'num_cores': self.cores_spin.value(),
            'cpus_per_task': self.cores_spin.value(),
            'memory_gb': int(self.memory_combo.currentText()),
            'memlimit_multiplier': scheduler_defaults.get('memlimit_multiplier', 1.0)
        }
        
        try:
            job_id = self.lsf_manager.submit_vnc_job(vnc_config, lsf_config)
            QMessageBox.information(self, "Success", 
                                  f"VNC session created successfully!\nJob ID: {job_id}")
            
            # Clear inputs
            self.name_input.clear()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create VNC session: {str(e)}") 