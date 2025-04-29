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

class EntraManager:
    """Manages Microsoft Entra ID authentication for VNC Manager"""
    
    def __init__(self):
        """Initialize the Entra ID manager with credentials from environment variables"""
        # Get configuration from environment variables
        self.client_id = os.environ.get('ENTRA_CLIENT_ID')
        self.client_secret = os.environ.get('ENTRA_CLIENT_SECRET')
        self.tenant_id = os.environ.get('ENTRA_TENANT_ID')
        self.redirect_uri = os.environ.get('ENTRA_REDIRECT_URI', 'http://localhost:8080/auth/callback')
        
        # Validate required configuration
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            logging.error("Microsoft Entra ID configuration missing. Set ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, and ENTRA_TENANT_ID environment variables.")
        
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