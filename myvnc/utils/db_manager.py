#!/usr/bin/env python3

# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0

"""
Database manager for MyVNC application
"""

import os
import json
import sqlite3
import time
import logging
from pathlib import Path

class DatabaseManager:
    """
    Manages SQLite database connections and operations for MyVNC
    """
    
    def __init__(self, data_dir='/localdev/myvnc/data'):
        """Initialize the database manager with the specified data directory"""
        self.data_dir = data_dir
        self.logger = logging.getLogger('myvnc')
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Database file path
        self.db_path = os.path.join(self.data_dir, 'myvnc.db')
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema if it doesn't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create user_settings table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    username TEXT PRIMARY KEY,
                    settings TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            self.logger.error(f"Error initializing database: {str(e)}")
    
    def get_user_settings(self, username):
        """
        Get settings for a specific user
        
        Args:
            username: The username to get settings for
            
        Returns:
            Dictionary of user settings, or empty dict if no settings found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Query for user settings
            cursor.execute(
                "SELECT settings FROM user_settings WHERE username = ?", 
                (username,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # Parse JSON settings from database
                return json.loads(result[0])
            else:
                return {}
                
        except Exception as e:
            self.logger.error(f"Error getting user settings for {username}: {str(e)}")
            return {}
    
    def save_user_settings(self, username, settings):
        """
        Save settings for a specific user
        
        Args:
            username: The username to save settings for
            settings: Dictionary of settings to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert settings to JSON string
            settings_json = json.dumps(settings)
            current_time = int(time.time())
            
            # Check if user already has settings
            cursor.execute(
                "SELECT 1 FROM user_settings WHERE username = ?", 
                (username,)
            )
            
            if cursor.fetchone():
                # Update existing settings
                cursor.execute(
                    "UPDATE user_settings SET settings = ?, updated_at = ? WHERE username = ?",
                    (settings_json, current_time, username)
                )
            else:
                # Insert new settings
                cursor.execute(
                    "INSERT INTO user_settings (username, settings, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (username, settings_json, current_time, current_time)
                )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Saved settings for user {username}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving user settings for {username}: {str(e)}")
            return False
    
    def delete_user_settings(self, username):
        """
        Delete settings for a specific user
        
        Args:
            username: The username to delete settings for
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Delete user settings
            cursor.execute(
                "DELETE FROM user_settings WHERE username = ?", 
                (username,)
            )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Deleted settings for user {username}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error deleting user settings for {username}: {str(e)}")
            return False 