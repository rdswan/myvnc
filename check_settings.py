#!/usr/bin/env python3

import os
import json
import sqlite3

data_dir = '/localdev/myvnc/data'
db_path = os.path.join(data_dir, 'myvnc.db')

print(f'Checking database at {db_path}')
print(f'Database exists: {os.path.exists(db_path)}')

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all users with settings
        cursor.execute('SELECT username, settings FROM user_settings')
        rows = cursor.fetchall()
        
        print(f'Found {len(rows)} users with settings')
        
        for username, settings_json in rows:
            print(f'\nUser: {username}')
            try:
                settings = json.loads(settings_json)
                print(f'Settings: {json.dumps(settings, indent=2)}')
                
                # Check for VNC settings
                if 'vnc_settings' in settings:
                    print('VNC settings found:')
                    for key, value in settings['vnc_settings'].items():
                        print(f'  {key}: {value}')
                else:
                    print('No VNC settings found')
            except Exception as e:
                print(f'Error parsing settings: {e}')
                print(f'Raw settings: {settings_json}')
        
        conn.close()
    except Exception as e:
        print(f'Error accessing database: {e}')
else:
    print('Database file does not exist') 