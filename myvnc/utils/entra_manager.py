# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""
Microsoft Entra ID (formerly Azure AD) authentication handler for VNC Manager
"""

import os
import time
import json
import uuid
import logging
import requests
from urllib.parse import urlencode
from pathlib import Path

class EntraManager:
    """Manages Microsoft Entra ID authentication for VNC Manager"""
    
    def __init__(self):
        """Initialize the Entra ID manager with credentials from environment variables or config file"""
        # Initialize logger
        self.logger = logging.getLogger('myvnc')
        
        # Load server configuration first to get config paths
        self.server_config = self._load_server_config()
        
        # Try to load configuration from environment variables first
        self.client_id = os.environ.get('ENTRA_CLIENT_ID')
        self.client_secret = os.environ.get('ENTRA_CLIENT_SECRET')
        self.tenant_id = os.environ.get('ENTRA_TENANT_ID')
        self.redirect_uri = os.environ.get('ENTRA_REDIRECT_URI', 'http://localhost:8080/auth/callback')
        
        # If any of the required credentials are missing, try to load from config file
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            self._load_config_from_file()
        
        # Validate required configuration
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            self.logger.error("Microsoft Entra ID configuration missing. Set ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, and ENTRA_TENANT_ID environment variables.")
        
        # Set up endpoint URLs
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.authorize_endpoint = f"{self.authority}/oauth2/v2.0/authorize"
        self.token_endpoint = f"{self.authority}/oauth2/v2.0/token"
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"
        
        # Define scopes
        self.scopes = [
            "User.Read",
            "offline_access"
        ]
        
        # Session tracking
        self.sessions = {}
    
    def _load_server_config(self):
        """Load server configuration to get config file paths"""
        config_path = Path(__file__).parent.parent.parent / "config" / "default_server_config.json"
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                print(f"Server config file not found: {config_path}")
        except Exception as e:
            print(f"Error loading server config: {str(e)}")
        
        # Return empty config if not found
        return {}
        
    def _load_config_from_file(self):
        """Load Entra ID configuration from the config file"""
        try:
            # Get the path from server config or use the default
            config_path_str = self.server_config.get('entra_config_path', "config/auth/entra_config.json")
            
            # Handle both absolute and relative paths
            config_path = Path(config_path_str)
            if not config_path.is_absolute():
                # Resolve relative path from the application root
                config_path = Path(__file__).parent.parent.parent / config_path_str
            
            print(f"Looking for Entra ID config file at: {config_path}")
            
            # Check if the file exists
            if not config_path.exists():
                print(f"Warning: Entra ID config file not found: {config_path}")
                return
            
            # Load the config file
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Set the configuration values if not already set from environment variables
            if not self.client_id and 'client_id' in config:
                self.client_id = config['client_id']
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_CLIENT_ID'] = self.client_id
                
            if not self.client_secret and 'client_secret' in config:
                self.client_secret = config['client_secret']
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_CLIENT_SECRET'] = self.client_secret
                
            if not self.tenant_id and 'tenant_id' in config:
                self.tenant_id = config['tenant_id']
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_TENANT_ID'] = self.tenant_id
                
            if 'redirect_uri' in config:
                self.redirect_uri = config['redirect_uri']
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_REDIRECT_URI'] = self.redirect_uri
                
            if 'scopes' in config and config['scopes']:
                self.scopes = config['scopes']
                
            print(f"Successfully loaded Entra ID configuration from {config_path}")
        except Exception as e:
            print(f"Error loading Entra ID config from file: {str(e)}")
    
    def get_authorization_url(self):
        """Generate the authorization URL for Entra ID login"""
        if not all([self.client_id, self.tenant_id]):
            return None, "Microsoft Entra ID not configured"
        
        # Generate state parameter to prevent CSRF
        state = str(uuid.uuid4())
        
        # Build authorization URL parameters
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(self.scopes),
            'state': state,
            'prompt': 'select_account',
            'response_mode': 'query'
        }
        
        # Return the full authorization URL
        auth_url = f"{self.authorize_endpoint}?{urlencode(params)}"
        return auth_url, state
    
    def get_token(self, auth_code):
        """Exchange authorization code for access token"""
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            return None, "Microsoft Entra ID not configured"
        
        # Prepare token request
        token_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(self.scopes)
        }
        
        try:
            # Make token request
            response = requests.post(self.token_endpoint, data=token_data)
            response.raise_for_status()
            
            # Parse token response
            token_info = response.json()
            return token_info, None
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Token request failed: {str(e)}")
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('error_description', str(e))
                except:
                    error_message = str(e)
            else:
                error_message = "Failed to connect to Microsoft Entra ID"
            
            return None, error_message
    
    def get_user_info(self, access_token):
        """Get user information from Microsoft Graph API"""
        if not access_token:
            return None, "Access token required"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            # Request user profile information
            response = requests.get(f"{self.graph_endpoint}/me", headers=headers)
            response.raise_for_status()
            
            # Parse user data
            user_data = response.json()
            
            # Extract relevant user information
            user_info = {
                'id': user_data.get('id'),
                'username': user_data.get('userPrincipalName'),
                'display_name': user_data.get('displayName'),
                'email': user_data.get('mail', user_data.get('userPrincipalName')),
                'first_name': user_data.get('givenName'),
                'last_name': user_data.get('surname')
            }
            
            return user_info, None
            
        except requests.exceptions.RequestException as e:
            logging.error(f"User info request failed: {str(e)}")
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('error', {}).get('message', str(e))
                except:
                    error_message = str(e)
            else:
                error_message = "Failed to retrieve user information"
            
            return None, error_message
    
    def create_session(self, user_info, token_info):
        """Create a new user session"""
        if not user_info or not token_info:
            return None
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Store session data
        session_data = {
            'user': user_info,
            'access_token': token_info.get('access_token'),
            'refresh_token': token_info.get('refresh_token'),
            'expires_at': time.time() + token_info.get('expires_in', 3600),
            'created_at': time.time()
        }
        
        # Save session
        self.sessions[session_id] = session_data
        
        return session_id
    
    def validate_session(self, session_id):
        """Validate a user session"""
        if not session_id or session_id not in self.sessions:
            return False, None
        
        session = self.sessions[session_id]
        
        # Check if session has expired
        if time.time() > session['expires_at']:
            # Try to refresh the token
            refresh_successful, new_token_info = self._refresh_token(session['refresh_token'])
            
            if not refresh_successful:
                # Remove expired session
                self.sessions.pop(session_id, None)
                return False, None
            
            # Update session with new token information
            session['access_token'] = new_token_info.get('access_token')
            session['refresh_token'] = new_token_info.get('refresh_token', session['refresh_token'])
            session['expires_at'] = time.time() + new_token_info.get('expires_in', 3600)
            self.sessions[session_id] = session
        
        return True, session['user']
    
    def end_session(self, session_id):
        """End a user session"""
        if session_id in self.sessions:
            self.sessions.pop(session_id, None)
            return True
        return False
    
    def _refresh_token(self, refresh_token):
        """Refresh an expired access token"""
        if not refresh_token or not all([self.client_id, self.client_secret, self.tenant_id]):
            return False, None
        
        # Prepare refresh token request
        token_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'scope': ' '.join(self.scopes)
        }
        
        try:
            # Make token refresh request
            response = requests.post(self.token_endpoint, data=token_data)
            response.raise_for_status()
            
            # Parse token response
            token_info = response.json()
            return True, token_info
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Token refresh failed: {str(e)}")
            return False, None 