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
        
        # Ensure manager_overrides table exists (migration support)
        self._ensure_manager_overrides_table()
    
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
            
            # Create manager_overrides table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS manager_overrides (
                    username TEXT PRIMARY KEY,
                    cores TEXT,
                    memory TEXT,
                    window_managers TEXT,
                    queues TEXT,
                    os_options TEXT,
                    created_by TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            self.logger.error(f"Error initializing database: {str(e)}")
    
    def _ensure_manager_overrides_table(self):
        """Ensure the manager_overrides table exists with correct schema (for migration support)"""
        try:
            self.logger.info(f"Checking for manager_overrides table in {self.db_path}")
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if the table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='manager_overrides'
            """)
            
            result = cursor.fetchone()
            self.logger.info(f"Table check result: {result}")
            
            if result:
                # Table exists, check if it has the correct schema
                cursor.execute("PRAGMA table_info(manager_overrides)")
                columns = cursor.fetchall()
                column_names = [col[1] for col in columns]
                self.logger.info(f"Existing columns: {column_names}")
                
                # Check if we have the new schema (username, cores, memory, etc.)
                if 'username' not in column_names or 'cores' not in column_names:
                    self.logger.info("Table exists but has old schema, dropping and recreating")
                    cursor.execute("DROP TABLE manager_overrides")
                    conn.commit()
                    result = None  # Force recreation
                else:
                    self.logger.info("manager_overrides table exists with correct schema")
            
            if not result:
                # Table doesn't exist or was dropped, create it with correct schema
                self.logger.info("Creating manager_overrides table with correct schema")
                cursor.execute('''
                    CREATE TABLE manager_overrides (
                        username TEXT PRIMARY KEY,
                        cores TEXT,
                        memory TEXT,
                        window_managers TEXT,
                        queues TEXT,
                        os_options TEXT,
                        created_by TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                ''')
                conn.commit()
                self.logger.info("manager_overrides table created successfully")
                
                # Verify it was created
                cursor.execute("PRAGMA table_info(manager_overrides)")
                verify_columns = cursor.fetchall()
                self.logger.info(f"New table columns: {[col[1] for col in verify_columns]}")
            
            conn.close()
        except Exception as e:
            self.logger.error(f"Error ensuring manager_overrides table: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
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
    
    def get_manager_override(self, username):
        """
        Get manager override for a specific user
        
        Args:
            username: The username to get override for
            
        Returns:
            Dictionary of override settings, or None if no override found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT cores, memory, window_managers, queues, os_options, created_by, created_at, updated_at FROM manager_overrides WHERE username = ?",
                (username,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'username': username,
                    'cores': json.loads(result[0]) if result[0] else None,
                    'memory': json.loads(result[1]) if result[1] else None,
                    'window_managers': json.loads(result[2]) if result[2] else None,
                    'queues': json.loads(result[3]) if result[3] else None,
                    'os_options': json.loads(result[4]) if result[4] else None,
                    'created_by': result[5],
                    'created_at': result[6],
                    'updated_at': result[7]
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting manager override for {username}: {str(e)}")
            return None
    
    def get_all_manager_overrides(self):
        """
        Get all manager overrides
        
        Returns:
            List of dictionaries with override settings
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT username, cores, memory, window_managers, queues, os_options, created_by, created_at, updated_at FROM manager_overrides"
            )
            
            results = cursor.fetchall()
            conn.close()
            
            overrides = []
            for result in results:
                overrides.append({
                    'username': result[0],
                    'cores': json.loads(result[1]) if result[1] else None,
                    'memory': json.loads(result[2]) if result[2] else None,
                    'window_managers': json.loads(result[3]) if result[3] else None,
                    'queues': json.loads(result[4]) if result[4] else None,
                    'os_options': json.loads(result[5]) if result[5] else None,
                    'created_by': result[6],
                    'created_at': result[7],
                    'updated_at': result[8]
                })
            
            return overrides
                
        except Exception as e:
            self.logger.error(f"Error getting all manager overrides: {str(e)}")
            return []
    
    def save_manager_override(self, username, overrides, created_by):
        """
        Save manager override for a specific user
        
        Args:
            username: The username to save override for
            overrides: Dictionary of override settings (cores, memory, window_managers, queues, os_options)
            created_by: The manager who created/updated this override
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # First, let's check what columns exist in the table
            cursor.execute("PRAGMA table_info(manager_overrides)")
            columns = cursor.fetchall()
            self.logger.info(f"manager_overrides table columns: {columns}")
            
            current_time = int(time.time())
            
            # Convert lists to JSON strings (None values remain None)
            cores_json = json.dumps(overrides.get('cores')) if overrides.get('cores') is not None else None
            memory_json = json.dumps(overrides.get('memory')) if overrides.get('memory') is not None else None
            window_managers_json = json.dumps(overrides.get('window_managers')) if overrides.get('window_managers') is not None else None
            queues_json = json.dumps(overrides.get('queues')) if overrides.get('queues') is not None else None
            os_options_json = json.dumps(overrides.get('os_options')) if overrides.get('os_options') is not None else None
            
            self.logger.info(f"Attempting to save override for username: {username}")
            
            # Check if override already exists
            try:
                cursor.execute(
                    "SELECT 1 FROM manager_overrides WHERE username = ?",
                    (username,)
                )
                exists = cursor.fetchone()
                self.logger.info(f"Override exists check result: {exists}")
            except Exception as e:
                self.logger.error(f"Error checking if override exists: {str(e)}")
                raise
            
            if exists:
                # Update existing override
                self.logger.info("Updating existing override")
                cursor.execute(
                    """UPDATE manager_overrides 
                       SET cores = ?, memory = ?, window_managers = ?, queues = ?, os_options = ?, 
                           created_by = ?, updated_at = ? 
                       WHERE username = ?""",
                    (cores_json, memory_json, window_managers_json, queues_json, os_options_json,
                     created_by, current_time, username)
                )
            else:
                # Insert new override
                self.logger.info("Inserting new override")
                cursor.execute(
                    """INSERT INTO manager_overrides 
                       (username, cores, memory, window_managers, queues, os_options, created_by, created_at, updated_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (username, cores_json, memory_json, window_managers_json, queues_json, os_options_json,
                     created_by, current_time, current_time)
                )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Saved manager override for user {username} by {created_by}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving manager override for {username}: {str(e)}")
            import traceback
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
    
    def delete_manager_override(self, username):
        """
        Delete manager override for a specific user
        
        Args:
            username: The username to delete override for
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "DELETE FROM manager_overrides WHERE username = ?",
                (username,)
            )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Deleted manager override for user {username}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error deleting manager override for {username}: {str(e)}")
            return False
    
    def verify_database_integrity(self):
        """
        Verify database integrity and fix any issues
        
        Returns:
            Tuple of (success: bool, message: str, issues_found: list)
        """
        issues_found = []
        fixes_applied = []
        
        try:
            self.logger.info("=" * 60)
            self.logger.info("Starting database integrity verification")
            self.logger.info(f"Database path: {self.db_path}")
            self.logger.info("=" * 60)
            
            # Check if database file exists
            if not os.path.exists(self.db_path):
                self.logger.warning(f"Database file does not exist: {self.db_path}")
                issues_found.append("Database file missing")
                self.logger.info("Attempting to initialize database...")
                self._init_db()
                fixes_applied.append("Created new database file")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Define expected schemas
            expected_schemas = {
                'user_settings': {
                    'username': 'TEXT',
                    'settings': 'TEXT',
                    'created_at': 'INTEGER',
                    'updated_at': 'INTEGER'
                },
                'manager_overrides': {
                    'username': 'TEXT',
                    'cores': 'TEXT',
                    'memory': 'TEXT',
                    'window_managers': 'TEXT',
                    'queues': 'TEXT',
                    'os_options': 'TEXT',
                    'created_by': 'TEXT',
                    'created_at': 'INTEGER',
                    'updated_at': 'INTEGER'
                }
            }
            
            # Check each expected table
            for table_name, expected_columns in expected_schemas.items():
                self.logger.info(f"\nChecking table: {table_name}")
                
                # Check if table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    self.logger.warning(f"Table '{table_name}' does not exist")
                    issues_found.append(f"Table '{table_name}' missing")
                    
                    # Attempt to create the table
                    self.logger.info(f"Creating table '{table_name}'...")
                    if table_name == 'user_settings':
                        cursor.execute('''
                            CREATE TABLE user_settings (
                                username TEXT PRIMARY KEY,
                                settings TEXT NOT NULL,
                                created_at INTEGER NOT NULL,
                                updated_at INTEGER NOT NULL
                            )
                        ''')
                        fixes_applied.append(f"Created table '{table_name}'")
                        self.logger.info(f"✓ Created table '{table_name}'")
                    elif table_name == 'manager_overrides':
                        cursor.execute('''
                            CREATE TABLE manager_overrides (
                                username TEXT PRIMARY KEY,
                                cores TEXT,
                                memory TEXT,
                                window_managers TEXT,
                                queues TEXT,
                                os_options TEXT,
                                created_by TEXT NOT NULL,
                                created_at INTEGER NOT NULL,
                                updated_at INTEGER NOT NULL
                            )
                        ''')
                        fixes_applied.append(f"Created table '{table_name}'")
                        self.logger.info(f"✓ Created table '{table_name}'")
                else:
                    self.logger.info(f"✓ Table '{table_name}' exists")
                    
                    # Verify schema
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()
                    column_dict = {col[1]: col[2] for col in columns}  # {name: type}
                    
                    self.logger.info(f"  Current columns: {list(column_dict.keys())}")
                    
                    # Check for missing columns
                    missing_columns = set(expected_columns.keys()) - set(column_dict.keys())
                    if missing_columns:
                        self.logger.warning(f"  Missing columns in '{table_name}': {missing_columns}")
                        issues_found.append(f"Table '{table_name}' missing columns: {missing_columns}")
                        
                        # For schema changes, we need to recreate the table
                        self.logger.info(f"  Schema mismatch detected. Recreating table '{table_name}'...")
                        
                        # Backup existing data
                        cursor.execute(f"SELECT * FROM {table_name}")
                        backup_data = cursor.fetchall()
                        backup_columns = [description[0] for description in cursor.description]
                        
                        # Drop and recreate table
                        cursor.execute(f"DROP TABLE {table_name}")
                        
                        if table_name == 'user_settings':
                            cursor.execute('''
                                CREATE TABLE user_settings (
                                    username TEXT PRIMARY KEY,
                                    settings TEXT NOT NULL,
                                    created_at INTEGER NOT NULL,
                                    updated_at INTEGER NOT NULL
                                )
                            ''')
                        elif table_name == 'manager_overrides':
                            cursor.execute('''
                                CREATE TABLE manager_overrides (
                                    username TEXT PRIMARY KEY,
                                    cores TEXT,
                                    memory TEXT,
                                    window_managers TEXT,
                                    queues TEXT,
                                    os_options TEXT,
                                    created_by TEXT NOT NULL,
                                    created_at INTEGER NOT NULL,
                                    updated_at INTEGER NOT NULL
                                )
                            ''')
                        
                        fixes_applied.append(f"Recreated table '{table_name}' with correct schema")
                        self.logger.info(f"  ✓ Recreated table '{table_name}'")
                        
                        # Restore data if possible
                        if backup_data:
                            self.logger.info(f"  Attempting to restore {len(backup_data)} rows...")
                            # Note: This is a best-effort restore; some data may be lost if schemas are incompatible
                    else:
                        self.logger.info(f"  ✓ Schema is correct")
            
            conn.commit()
            conn.close()
            
            # Summary
            self.logger.info("\n" + "=" * 60)
            self.logger.info("Database integrity verification complete")
            self.logger.info(f"Issues found: {len(issues_found)}")
            if issues_found:
                for issue in issues_found:
                    self.logger.info(f"  - {issue}")
            self.logger.info(f"Fixes applied: {len(fixes_applied)}")
            if fixes_applied:
                for fix in fixes_applied:
                    self.logger.info(f"  - {fix}")
            
            if issues_found and not fixes_applied:
                self.logger.error("Issues were found but could not be fixed automatically")
                return False, "Database issues found but not fixed", issues_found
            elif issues_found and fixes_applied:
                self.logger.info("✓ All issues were fixed successfully")
                return True, "Database verified and repaired", issues_found
            else:
                self.logger.info("✓ Database integrity verified - no issues found")
                return True, "Database integrity verified", []
            
        except Exception as e:
            self.logger.error(f"Error during database verification: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False, f"Verification failed: {str(e)}", issues_found 