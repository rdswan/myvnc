# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QPushButton, QHBoxLayout, QHeaderView)
from PyQt6.QtCore import QTimer, Qt
from ..utils.lsf_manager import LSFManager

class VNCManagerTab(QWidget):
    def __init__(self, config_manager, authenticated_user=None):
        super().__init__()
        self.config_manager = config_manager
        self.lsf_manager = LSFManager()
        self.authenticated_user = authenticated_user
        
        self.init_ui()
        
        # Set up auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_vnc_list)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
        
        # Initial refresh
        self.refresh_vnc_list()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Job ID", "Name", "User", "Status", "Queue"])
        
        # Set table properties
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # Create buttons
        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.kill_button = QPushButton("Kill Selected")
        
        self.refresh_button.clicked.connect(self.refresh_vnc_list)
        self.kill_button.clicked.connect(self.kill_selected_vnc)
        
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.kill_button)
        button_layout.addStretch()
        
        # Add widgets to layout
        layout.addWidget(self.table)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def refresh_vnc_list(self):
        try:
            jobs = self.lsf_manager.get_active_vnc_jobs(authenticated_user=self.authenticated_user)
            self.table.setRowCount(len(jobs))
            
            for row, job in enumerate(jobs):
                self.table.setItem(row, 0, QTableWidgetItem(job['job_id']))
                self.table.setItem(row, 1, QTableWidgetItem(job['name']))
                self.table.setItem(row, 2, QTableWidgetItem(job['user']))
                self.table.setItem(row, 3, QTableWidgetItem(job['status']))
                self.table.setItem(row, 4, QTableWidgetItem(job['queue']))
                
                # Make items non-editable
                for col in range(5):
                    item = self.table.item(row, col)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        except Exception as e:
            # TODO: Add proper error handling/display
            print(f"Error refreshing VNC list: {e}")
    
    def kill_selected_vnc(self):
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            return
        
        # Get the job ID from the first column of the selected row
        row = selected_rows[0].row()
        job_id = self.table.item(row, 0).text()
        
        if self.lsf_manager.kill_vnc_job(job_id, authenticated_user=self.authenticated_user):
            self.refresh_vnc_list() 