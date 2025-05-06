# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
import os
import sys
import uuid
import time
import json
from typing import Dict, Optional, Tuple, List
from pathlib import Path
from urllib.parse import urlencode
import logging
import traceback

# Try to import requests, use mock if not available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    print("Requests module not available, HTTP functionality will be limited")
    REQUESTS_AVAILABLE = False
    # Create a mock requests module
    class MockResponse:
        def __init__(self, status_code=200, text="", json_data=None):
            self.status_code = status_code
            self.text = text
            self._json = json_data or {}
        def json(self):
            return self._json
    
    class MockRequests:
        def get(self, *args, **kwargs):
            print(f"Mock requests: GET {args[0]}")
            return MockResponse(404, "Not found")
        def post(self, *args, **kwargs):
            print(f"Mock requests: POST {args[0]}")
            return MockResponse(404, "Not found")
    
    requests = MockRequests()

# Try to import LDAP, use mock if not available
try:
    import ldap
    LDAP_AVAILABLE = True
except ImportError:
    LDAP_AVAILABLE = False
    # Create a mock for LDAP errors
    class MockLDAP:
        class INVALID_CREDENTIALS(Exception): pass
        class SERVER_DOWN(Exception): pass
        class LDAPError(Exception): pass
        OPT_REFERRALS = 0
        SCOPE_SUBTREE = 0
        def initialize(self, *args): return self
        def set_option(self, *args): pass
        def simple_bind_s(self, *args): raise self.INVALID_CREDENTIALS("LDAP mock")
        def search_s(self, *args): return []
        def unbind(self): pass
    ldap = MockLDAP()

# Try to import MSAL, use mock implementation if not available
try:
    import msal
except ImportError:
    print("MSAL not available, using mock implementation")
    from .mock_msal import ConfidentialClientApplication
    # Create a mock msal module
    class MockMSAL:
        ConfidentialClientApplication = ConfidentialClientApplication
    msal = MockMSAL

# Import the central load_server_config function from the new module
from myvnc.utils.config_loader import load_server_config

class AuthManager:
    """
    Manages authentication with Active Directory using LDAP or Microsoft Entra ID using MSAL
    """
    
    def __init__(self):
        """Initialize the auth manager"""
        # Initialize logger
        self.logger = logging.getLogger('myvnc')
        
        # Load server configuration - use central function instead of internal method
        self.server_config = load_server_config()
        self.auth_method = self.server_config.get("authentication", "").lower()
        self.auth_enabled = self.auth_method in ["entra", "ldap"]
        
        # Import specialized auth managers
        from .entra_manager import EntraManager
        from .ldap_manager import LDAPManager
        
        # Initialize the specific auth manager based on configuration
        self.entra_manager = EntraManager() if self.auth_method == "entra" else None
        self.ldap_manager = LDAPManager() if self.auth_method == "ldap" else None
        
        # Only set up auth if enabled
        if not self.auth_enabled:
            print("Authentication is disabled in server configuration")
            return
            
        # LDAP settings
        self.ad_server = os.environ.get('AD_SERVER', 'ldap://localhost:389')
        self.ad_domain = os.environ.get('AD_DOMAIN', 'example.com')
        self.ad_base_dn = os.environ.get('AD_BASE_DN', 'dc=example,dc=com')
        
        # Microsoft Entra ID settings - try to load from environment variables first
        self.tenant_id = os.environ.get('ENTRA_TENANT_ID', '')
        self.client_id = os.environ.get('ENTRA_CLIENT_ID', '')
        self.client_secret = os.environ.get('ENTRA_CLIENT_SECRET', '')
        # Will be fully set from config file - don't use default value
        self.redirect_uri = None
        
        # If Entra auth is enabled, always load from config file to ensure redirect_uri is set
        if self.auth_method == 'entra':
            self.logger.info("Entra authentication is enabled, loading configuration from file")
            self._load_entra_config_from_file()
            
            # Update from environment variables again (might have been set by EntraManager)
            self.tenant_id = os.environ.get('ENTRA_TENANT_ID', self.tenant_id)
            self.client_id = os.environ.get('ENTRA_CLIENT_ID', self.client_id)
            self.client_secret = os.environ.get('ENTRA_CLIENT_SECRET', self.client_secret)
            
            # Log the final configuration state
            self.logger.info(f"Final Entra configuration state: client_id={self.client_id}, tenant_id={self.tenant_id}, redirect_uri={self.redirect_uri}")
        
        self.scopes = ['https://graph.microsoft.com/.default']
        
        # Initialize MSAL app if using Entra ID
        if self.auth_method == 'entra' and self.tenant_id and self.client_id:
            self.msal_app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret
            )
        else:
            self.msal_app = None
        
        # Session management
        self.sessions = {}
        
        # Use data directory from config, falling back to default
        self.session_dir = self.server_config.get("datadir", "myvnc/data")
        self.session_file = os.path.join(self.session_dir, 'sessions.json')
        
        # Load session expiry from config - default to 30 days (1 month) if not specified
        self.session_expiry_days = 30  # Default value: 30 days (1 month)
        
        # Try to get session expiry from server config first
        if "session_expiry_days" in self.server_config:
            self.session_expiry_days = int(self.server_config.get("session_expiry_days", 30))
            self.logger.info(f"Using session expiry from server config: {self.session_expiry_days} days")
        
        # If LDAP auth is enabled, check LDAP config for session expiry
        if self.auth_method == 'ldap' and self.ldap_manager and hasattr(self.ldap_manager, 'config'):
            ldap_expiry_days = self.ldap_manager.config.get("session_expiry_days")
            if ldap_expiry_days is not None:
                self.session_expiry_days = int(ldap_expiry_days)
                self.logger.info(f"Using session expiry from LDAP config: {self.session_expiry_days} days")
        
        # Calculate session expiry in seconds
        self.session_expiry = self.session_expiry_days * 24 * 60 * 60
        self.logger.info(f"Session expiry time set to {self.session_expiry_days} days ({self.session_expiry} seconds)")
        
        # Create the data directory if it doesn't exist
        if not os.path.exists(self.session_dir):
            os.makedirs(self.session_dir)
        
        # Load existing sessions
        self.load_sessions()
    
    def _load_entra_config_from_file(self):
        """Load Entra ID configuration from the config file"""
        try:
            # Get the path from server config - this should be the absolute path
            config_path_str = self.server_config.get('entra_config')
            self.logger.info(f"DEBUG: Server config provides entra_config path: {config_path_str}")
            
            if not config_path_str:
                # Fallback to default path
                config_path_str = "config/auth/entra_config.json"
                # Resolve relative path from the application root
                config_path = Path(__file__).parent.parent.parent / config_path_str
                self.logger.info(f"DEBUG: Using default relative path: {config_path}")
            else:
                # Use the absolute path directly from server config
                config_path = Path(config_path_str)
                self.logger.info(f"DEBUG: Using absolute path from server config: {config_path}")
            
            self.logger.info(f"DEBUG: Checking if file exists at: {config_path}")
            
            # Check if the file exists
            if not config_path.exists():
                self.logger.error(f"Entra ID config file not found: {config_path}")
                return
            
            self.logger.info(f"DEBUG: File exists, loading config from: {config_path}")
            
            # Load the config file
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            self.logger.info(f"DEBUG: Successfully loaded config JSON with keys: {list(config.keys())}")
            
            # Set the configuration values if not already set from environment variables
            if not self.client_id and 'client_id' in config:
                self.client_id = config['client_id']
                self.logger.info(f"Using client_id from config: {self.client_id}")
                os.environ['ENTRA_CLIENT_ID'] = self.client_id
                
            if not self.client_secret and 'client_secret' in config:
                self.client_secret = config['client_secret']
                self.logger.info("Loaded client_secret from config")
                os.environ['ENTRA_CLIENT_SECRET'] = self.client_secret
                
            if not self.tenant_id and 'tenant_id' in config:
                self.tenant_id = config['tenant_id']
                self.logger.info(f"Using tenant_id from config: {self.tenant_id}")
                os.environ['ENTRA_TENANT_ID'] = self.tenant_id
                
            # ALWAYS use the redirect_uri from config file
            if 'redirect_uri' in config:
                self.redirect_uri = config['redirect_uri']
                self.logger.info(f"Using redirect_uri from config: {self.redirect_uri}")
                os.environ['ENTRA_REDIRECT_URI'] = self.redirect_uri
            else:
                self.logger.error("No redirect_uri found in Entra config file!")
                
            if 'scopes' in config and config['scopes']:
                self.scopes = config['scopes']
                self.logger.info(f"DEBUG: Using scopes from config: {self.scopes}")
                
            self.logger.info(f"Successfully loaded Entra ID configuration from {config_path}")
        except Exception as e:
            self.logger.error(f"Error loading Entra ID config from file: {str(e)}")
            self.logger.error(f"Exception details: {traceback.format_exc()}")
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate a user with Active Directory or Microsoft Entra ID
        
        Args:
            username: Username (without domain)
            password: Password
            
        Returns:
            Tuple of (success, message, session_id)
        """
        if not self.auth_enabled:
            return False, "Authentication is disabled", None
            
        if self.auth_method == 'entra':
            return self._authenticate_entra_id(username, password)
        elif self.auth_method == 'ldap':
            return self._authenticate_ldap(username, password)
        else:
            return False, f"Unsupported authentication method: {self.auth_method}", None
    
    def _authenticate_entra_id(self, username: str, password: str) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate a user with Microsoft Entra ID
        
        Args:
            username: Username (usually email)
            password: Password
            
        Returns:
            Tuple of (success, message, session_id)
        """
        try:
            # Use Resource Owner Password Credentials (ROPC) flow
            # Note: ROPC is not recommended for production scenarios
            # For production, use interactive authentication flow with redirect
            result = self.msal_app.acquire_token_by_username_password(
                username=username,
                password=password,
                scopes=self.scopes
            )
            
            if "error" in result:
                return False, f"Authentication error: {result.get('error_description', 'Unknown error')}", None
            
            # Get user info from Microsoft Graph
            graph_data = self._get_user_info_from_graph(result['access_token'])
            if not graph_data:
                return False, "Failed to retrieve user information", None
            
            # Extract user details
            display_name = graph_data.get('displayName', username)
            email = graph_data.get('mail', username)
            
            # Get group memberships
            groups = self._get_user_groups_from_graph(result['access_token'])
            
            # Create session
            session_id = self.create_session(username, display_name, email, groups)
            
            return True, "Authentication successful", session_id
            
        except Exception as e:
            error_msg = f"Entra ID authentication error: {str(e)}"
            print(error_msg, file=sys.stderr)
            return False, error_msg, None
    
    def _authenticate_ldap(self, username: str, password: str) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate user against LDAP
        
        Args:
            username: Username to authenticate
            password: Password to authenticate
            
        Returns:
            Tuple of (success, message, session_id)
        """
        if not self.ldap_manager:
            return False, "LDAP authentication is not configured", None
            
        self.logger.info(f"Authenticating user {username} with LDAP")
        
        try:
            # Use LDAP manager to authenticate
            success, message, session_id = self.ldap_manager.authenticate(username, password)
            
            if not success:
                self.logger.warning(f"LDAP authentication failed for {username}: {message}")
                return False, message, None
                
            self.logger.info(f"LDAP authentication successful for {username}")
                
            # Make sure we got a valid session ID
            if not session_id:
                self.logger.error(f"LDAP authentication successful but no session ID returned")
                # Try to create a session here as a fallback
                try:
                    # Create a minimal user info to create a session
                    user_info = {
                        'username': username,
                        'display_name': username,
                        'email': f"{username}@unknown.com",
                        'groups': []
                    }
                    session_id = self.create_session(username, user_info.get('display_name'), user_info.get('email'), user_info.get('groups', []))
                    self.logger.info(f"Created fallback session ID: {session_id}")
                    return True, "Authentication successful (fallback session created)", session_id
                except Exception as e:
                    self.logger.error(f"Failed to create fallback session: {str(e)}")
                    return False, "Authentication successful but session creation failed", None
            
            # Extra check to make sure session ID is a string
            if not isinstance(session_id, str):
                self.logger.error(f"LDAP authentication returned invalid session ID type: {type(session_id)}")
                return False, "Invalid session ID from LDAP authentication", None
            
            # Clone the session from LDAP manager to auth manager's session store
            # This ensures sessions are shared between the two managers
            ldap_session = self.ldap_manager.sessions.get(session_id)
            if ldap_session:
                # Copy the session data to our local sessions dictionary
                self.sessions[session_id] = ldap_session.copy()
                self.logger.info(f"Copied LDAP session to auth_manager sessions: {session_id[:8]}...")
                
                # Ensure the session has an expiry time
                if 'expiry' not in self.sessions[session_id]:
                    self.sessions[session_id]['expiry'] = time.time() + self.session_expiry
                    self.logger.info(f"Added missing expiry to cloned session")
                
                # Save sessions to disk
                self.save_sessions()
            else:
                self.logger.warning(f"Could not find session {session_id[:8]}... in LDAP manager sessions")
            
            return True, "Authentication successful", session_id
                
        except Exception as e:
            error_msg = f"LDAP authentication error: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            return False, error_msg, None
    
    def _get_user_info_from_graph(self, access_token):
        """Get user information from Microsoft Graph API"""
        # Check if this is a mock token (for testing)
        if access_token and access_token.startswith('mock_access_token_'):
            # Extract username from the mock token
            username = access_token.split('mock_access_token_')[1]
            # Return mock user data
            return {
                'displayName': f'{username.capitalize()} User',
                'userPrincipalName': f'{username}@tenstorrent.com',
                'mail': f'{username}@tenstorrent.com',
                'id': f'mock-user-id-{username}'
            }
            
        # Real implementation for production
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(
                'https://graph.microsoft.com/v1.0/me',
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"Error fetching user info: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"Exception fetching user info: {str(e)}")
            return None
    
    def _get_user_groups_from_graph(self, access_token):
        """Get user group memberships from Microsoft Graph API"""
        # Check if this is a mock token (for testing)
        if access_token and access_token.startswith('mock_access_token_'):
            # Return mock group data based on username
            username = access_token.split('mock_access_token_')[1]
            mock_groups = ['TT-All-Users']
            
            # Add role-specific groups based on username pattern
            if username.startswith('admin'):
                mock_groups.append('TT-Admins')
            if username.startswith('dev'):
                mock_groups.append('TT-Developers')
                
            return mock_groups
            
        # Real implementation for production
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(
                'https://graph.microsoft.com/v1.0/me/memberOf',
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return [group.get('displayName', '') for group in data.get('value', [])]
            else:
                self.logger.error(f"Error fetching user groups: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            self.logger.error(f"Exception fetching user groups: {str(e)}")
            return []
    
    def handle_auth_code(self, code: str) -> Tuple[bool, str, Optional[str]]:
        """
        Handle authorization code from Microsoft Entra ID redirect
        
        Args:
            code: Authorization code
            
        Returns:
            Tuple of (success, message, session_id)
        """
        if not self.msal_app:
            return False, "Microsoft Entra ID authentication is not configured", None
        
        try:
            if not self.redirect_uri:
                self.logger.error("Missing redirect_uri in handle_auth_code")
                return False, "Missing redirect_uri configuration", None
                
            self.logger.info(f"Acquiring token with redirect_uri: {self.redirect_uri}")
            
            result = self.msal_app.acquire_token_by_authorization_code(
                code=code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            if "error" in result:
                return False, f"Authentication error: {result.get('error_description', 'Unknown error')}", None
                
            # Get user info from Microsoft Graph
            graph_data = self._get_user_info_from_graph(result['access_token'])
            if not graph_data:
                return False, "Failed to retrieve user information", None
                
            # Extract user details
            username = graph_data.get('userPrincipalName', '').split('@')[0]
            display_name = graph_data.get('displayName', '')
            email = graph_data.get('mail', '')
            
            # Get group memberships
            groups = self._get_user_groups_from_graph(result['access_token'])
            
            # Create session - returns session_id string
            session_id = self.create_session(username, display_name, email, groups)
            
            return True, "Authentication successful", session_id
            
        except Exception as e:
            error_msg = f"Entra ID authentication error: {str(e)}"
            print(error_msg, file=sys.stderr)
            return False, error_msg, None
    
    def validate_session(self, session_id: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate a user session
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            Tuple of (success, message, session)
        """
        self.logger.debug(f"Validating session: {session_id[:8] if isinstance(session_id, str) and len(session_id) > 8 else session_id}")
        
        # Additional debug: Log session ID type
        self.logger.debug(f"Session ID type: {type(session_id)}")
        
        # Ensure session_id is a string
        if not isinstance(session_id, str):
            self.logger.warning(f"Session ID is not a string: {type(session_id)}")
            # Try to convert to string
            try:
                session_id = str(session_id)
                self.logger.debug(f"Converted session ID to string: {session_id[:8] if len(session_id) > 8 else session_id}")
            except Exception as e:
                self.logger.error(f"Failed to convert session ID to string: {e}")
                return False, "Invalid session ID format", None
        
        # Check if the session exists in our local cache
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            # Debug log session details
            self.logger.debug(f"Found session for user: {session.get('username', 'unknown')}")
            self.logger.debug(f"Session details: {session}")
            
            # Check for session expiry
            if 'expiry' in session:
                current_time = time.time()
                expiry_time = session['expiry']
                time_left = expiry_time - current_time
                
                # Log expiry information
                self.logger.debug(f"Session expiry check: current={current_time}, expiry={expiry_time}, time left={time_left:.2f}s")
                
                if current_time > expiry_time:
                    self.logger.warning(f"Session {session_id[:8]}... has expired")
                    # Remove expired session
                    self.sessions.pop(session_id)
                    return False, "Session has expired", None
            else:
                # If no expiry set, add one now (8 hours from now)
                session['expiry'] = time.time() + self.session_expiry
                self.logger.debug(f"Added missing expiry to session: {session['expiry']}")
            
            # Update last access time
            session['last_access'] = time.time()
            
            return True, "Session is valid", session
        
        # If using LDAP, check with LDAP manager
        if self.auth_method == 'ldap' and self.ldap_manager:
            self.logger.debug("Session not found in auth_manager, checking LDAP manager")
            success, message, session = self.ldap_manager.validate_session(session_id)
            
            # Additional debug: Log LDAP validation result
            self.logger.debug(f"LDAP validate_session result: success={success}, message={message}")
            if session:
                self.logger.debug(f"LDAP session: {session}")
            
            if success and session:
                # Cache the session locally
                self.sessions[session_id] = session
                
                # Ensure it has expiry time
                if 'expiry' not in session:
                    session['expiry'] = time.time() + self.session_expiry
                    self.logger.debug(f"Added expiry to LDAP session: {session['expiry']}")
                
                # Save sessions to persist
                self.save_sessions()
                
                return True, message, session
        
        self.logger.warning(f"Session not found: {session_id[:8]}...")
        return False, "Invalid or expired session", None

    def logout(self, session_id: str) -> Tuple[bool, str]:
        """
        Logout a user by invalidating their session
        
        Args:
            session_id: Session ID to invalidate
            
        Returns:
            Tuple of (success, message)
        """
        # Check local sessions
        if session_id in self.sessions:
            self.sessions.pop(session_id)
            self.save_sessions()
            return True, "Logged out successfully"
        
        # Check LDAP manager if using LDAP
        if self.auth_method == 'ldap' and self.ldap_manager:
            success, message = self.ldap_manager.end_session(session_id)
            if success:
                return True, message
        
        return False, "Session not found"

    def get_auth_url(self) -> str:
        """
        Get the authorization URL for Microsoft Entra ID authentication
        
        Returns:
            Authorization URL string
        """
        if self.auth_method != 'entra' or not self.msal_app:
            self.logger.error("Unable to get auth URL: auth_method is not entra or msal_app is not initialized")
            return ""
            
        # Generate a request state with a random value
        request_state = str(uuid.uuid4())
        
        # Cache the state for validation during the callback
        # This is a simplistic approach - for production, you would want a more robust solution
        self.auth_states = getattr(self, 'auth_states', {})
        self.auth_states[request_state] = {'created_at': time.time()}
        
        # Check if redirect_uri is configured
        if not self.redirect_uri:
            self.logger.error("Missing redirect_uri in get_auth_url")
            
            # If not set, try to load it from the config file directly
            try:
                config_path_str = self.server_config.get('entra_config')
                if config_path_str:
                    config_path = Path(config_path_str)
                    self.logger.info(f"Attempting to load redirect_uri directly from: {config_path}")
                    
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                            
                        if 'redirect_uri' in config:
                            self.redirect_uri = config['redirect_uri']
                            self.logger.info(f"Loaded redirect_uri directly from config: {self.redirect_uri}")
                            os.environ['ENTRA_REDIRECT_URI'] = self.redirect_uri
            except Exception as e:
                self.logger.error(f"Error attempting to load redirect_uri directly: {str(e)}")
            
            if not self.redirect_uri:
                self.logger.error("Still missing redirect_uri after direct load attempt")
                return ""
        
        self.logger.info(f"Generating auth URL with redirect_uri: {self.redirect_uri}")
        
        # Generate the authorization URL
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": request_state,
            "prompt": "select_account"
        }
        
        auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/authorize?{urlencode(auth_params)}"
        self.logger.info(f"Generated auth URL: {auth_url}")
        return auth_url
    
    def create_session(self, username: str, display_name: str, email: str, groups: List[str]) -> str:
        """
        Create a new session for a user
        
        Args:
            username: Username
            display_name: User's display name
            email: User's email
            groups: List of group memberships
            
        Returns:
            Session ID string
        """
        # Generate a unique session ID
        session_id = str(uuid.uuid4())
        # Set expiry time based on the session_expiry value
        expiry = time.time() + self.session_expiry
        
        # Create session object
        session = {
            'session_id': session_id,
            'username': username,
            'display_name': display_name,
            'email': email,
            'groups': groups,
            'created': time.time(),
            'expiry': expiry,
            'last_access': time.time()
        }
        
        # Store session
        self.sessions[session_id] = session
        
        # Save sessions to persist across server restarts
        self.save_sessions()
        
        self.logger.info(f"Created new session for user {username}: {session_id[:8]}...")
        
        return session_id
    
    def save_sessions(self):
        """Save sessions to a file"""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.sessions, f)
        except Exception as e:
            print(f"Error saving sessions: {str(e)}")
    
    def load_sessions(self):
        """Load sessions from a file"""
        self.sessions = {}  # Initialize with empty dict
        
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    loaded_sessions = json.load(f)
                    
                # Validate the loaded sessions to ensure they're properly formatted
                for session_id, session_data in loaded_sessions.items():
                    # Ensure session has the required fields
                    if isinstance(session_data, dict) and 'username' in session_data:
                        self.sessions[session_id] = session_data
                        
                self.logger.info(f"Loaded {len(self.sessions)} sessions from {self.session_file}")
            except Exception as e:
                self.logger.error(f"Error loading sessions: {str(e)}")
