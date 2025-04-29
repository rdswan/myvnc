import os
import sys
import uuid
import time
import json
from typing import Dict, Optional, Tuple, List
from pathlib import Path
from urllib.parse import urlencode

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
    print("LDAP module not available, LDAP authentication will be disabled")
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
    print("Using real MSAL implementation")
except ImportError:
    print("MSAL not available, using mock implementation")
    from .mock_msal import ConfidentialClientApplication
    # Create a mock msal module
    class MockMSAL:
        ConfidentialClientApplication = ConfidentialClientApplication
    msal = MockMSAL

class AuthManager:
    """
    Manages authentication with Active Directory using LDAP or Microsoft Entra ID using MSAL
    """
    
    def __init__(self):
        """Initialize the auth manager"""
        # Load server configuration
        self.server_config = self._load_server_config()
        self.auth_enabled = self.server_config.get("authentication", "").lower() == "entra"
        
        # Only set up auth if enabled
        if not self.auth_enabled:
            print("Authentication is disabled in server configuration")
            return
            
        # LDAP settings
        self.ad_server = os.environ.get('AD_SERVER', 'ldap://localhost:389')
        self.ad_domain = os.environ.get('AD_DOMAIN', 'example.com')
        self.ad_base_dn = os.environ.get('AD_BASE_DN', 'dc=example,dc=com')
        
        # Microsoft Entra ID settings
        self.tenant_id = os.environ.get('ENTRA_TENANT_ID', '')
        self.client_id = os.environ.get('ENTRA_CLIENT_ID', '')
        self.client_secret = os.environ.get('ENTRA_CLIENT_SECRET', '')
        self.redirect_uri = os.environ.get('ENTRA_REDIRECT_URI', 'http://localhost:8000/auth/callback')
        self.scopes = ['https://graph.microsoft.com/.default']
        # Default to 'entra' authentication if environment variables are set
        self.auth_method = os.environ.get('AUTH_METHOD', 'entra' if self.tenant_id and self.client_id else 'ldap')
        
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
        self.session_dir = 'data'
        self.session_file = os.path.join(self.session_dir, 'sessions.json')
        self.session_expiry = 8 * 60 * 60  # 8 hours in seconds
        
        # Create the data directory if it doesn't exist
        if not os.path.exists(self.session_dir):
            os.makedirs(self.session_dir)
        
        # Load existing sessions
        self.load_sessions()
    
    def _load_server_config(self):
        """Load server configuration from JSON file"""
        config_path = Path(__file__).parent.parent.parent / "config" / "default_server_config.json"
        
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Server configuration file not found or invalid at {config_path}")
            return {}
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Authenticate a user with Active Directory or Microsoft Entra ID
        
        Args:
            username: Username (without domain)
            password: Password
            
        Returns:
            Tuple of (success, message, session_data)
        """
        if not self.auth_enabled:
            return False, "Authentication is disabled", None
            
        if self.auth_method == 'entra' and self.msal_app:
            return self._authenticate_entra_id(username, password)
        else:
            return self._authenticate_ldap(username, password)
    
    def _authenticate_entra_id(self, username: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Authenticate a user with Microsoft Entra ID
        
        Args:
            username: Username (usually email)
            password: Password
            
        Returns:
            Tuple of (success, message, session_data)
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
    
    def _authenticate_ldap(self, username: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Authenticate a user with Active Directory using LDAP
        
        Args:
            username: Username (without domain)
            password: Password
            
        Returns:
            Tuple of (success, message, session_data)
        """
        try:
            # Connect to LDAP server
            conn = ldap.initialize(self.ad_server)
            conn.set_option(ldap.OPT_REFERRALS, 0)
            
            # Bind with user credentials
            user_dn = f"{username}@{self.ad_domain}"
            conn.simple_bind_s(user_dn, password)
            
            # Search for user details
            search_filter = f"(sAMAccountName={username})"
            attributes = ['displayName', 'mail', 'memberOf']
            
            result = conn.search_s(
                self.ad_base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                attributes
            )
            
            # Process user data
            if result and len(result) > 0:
                user_data = {}
                ldap_attrs = result[0][1]
                
                # Extract user attributes
                if 'displayName' in ldap_attrs:
                    user_data['display_name'] = ldap_attrs['displayName'][0].decode('utf-8')
                else:
                    user_data['display_name'] = username
                    
                if 'mail' in ldap_attrs:
                    user_data['email'] = ldap_attrs['mail'][0].decode('utf-8')
                
                # Extract group memberships
                user_data['groups'] = []
                if 'memberOf' in ldap_attrs:
                    for group_dn in ldap_attrs['memberOf']:
                        group_dn_str = group_dn.decode('utf-8')
                        # Extract CN from the DN
                        cn_part = next((part for part in group_dn_str.split(',') if part.startswith('CN=')), None)
                        if cn_part:
                            group_name = cn_part.replace('CN=', '')
                            user_data['groups'].append(group_name)
                
                # Create session
                session_id = self.create_session(username, user_data['display_name'], user_data['email'], user_data['groups'])
                return True, "Authentication successful", session_id
            else:
                return False, "User not found in Active Directory", None
                
        except ldap.INVALID_CREDENTIALS:
            return False, "Invalid credentials", None
        except ldap.SERVER_DOWN:
            return False, "LDAP server is unreachable", None
        except ldap.LDAPError as e:
            error_msg = f"LDAP error: {str(e)}"
            print(error_msg, file=sys.stderr)
            return False, error_msg, None
        except Exception as e:
            error_msg = f"Authentication error: {str(e)}"
            print(error_msg, file=sys.stderr)
            return False, error_msg, None
        finally:
            try:
                conn.unbind()
            except:
                pass
    
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
    
    def handle_auth_code(self, code: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Handle authorization code from Microsoft Entra ID redirect
        
        Args:
            code: Authorization code
            
        Returns:
            Tuple of (success, message, session_data)
        """
        if not self.msal_app:
            return False, "Microsoft Entra ID authentication is not configured", None
        
        try:
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
            
            # Create session
            session_id = self.create_session(username, display_name, email, groups)
            
            return True, "Authentication successful", session_id
            
        except Exception as e:
            error_msg = f"Entra ID authentication error: {str(e)}"
            print(error_msg, file=sys.stderr)
            return False, error_msg, None
    
    def get_auth_url(self) -> str:
        """
        Get the Microsoft Entra ID authorization URL for interactive login
        
        Returns:
            Authorization URL
        """
        if not self.msal_app:
            return None
        
        auth_url = self.msal_app.get_authorization_request_url(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
            response_type="code",
            prompt="select_account"
        )
        return auth_url
    
    def validate_session(self, session_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Validate a session ID
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            Tuple of (is_valid, session_data)
        """
        if not self.auth_enabled:
            return False, None
            
        if not session_id or session_id not in self.sessions:
            return False, None
        
        session = self.sessions[session_id]
        
        # Check if session has expired
        current_time = time.time()
        if current_time > session.get('expiry', 0):
            # Remove expired session
            del self.sessions[session_id]
            self.save_sessions()
            return False, None
        
        # Extend session expiry time
        session['expiry'] = current_time + self.session_expiry
        self.save_sessions()
        
        return True, session
    
    def logout(self, session_id: str) -> bool:
        """
        Invalidate a session (logout)
        
        Args:
            session_id: Session ID to invalidate
            
        Returns:
            True if session was found and removed, False otherwise
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save_sessions()
            return True
        return False
    
    def create_session(self, username: str, display_name: str, email: str, groups: List[str]) -> Dict:
        """
        Create a new session for a user
        
        Args:
            username: Username
            display_name: User's display name
            email: User's email
            groups: List of group memberships
            
        Returns:
            Session data including session_id
        """
        session_id = str(uuid.uuid4())
        expiry = time.time() + self.session_expiry
        
        session = {
            'session_id': session_id,
            'username': username,
            'display_name': display_name,
            'email': email,
            'groups': groups,
            'created': time.time(),
            'expiry': expiry
        }
        
        self.sessions[session_id] = session
        self.save_sessions()
        
        return session
    
    def save_sessions(self):
        """Save sessions to a file"""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.sessions, f)
        except Exception as e:
            print(f"Error saving sessions: {str(e)}")
    
    def load_sessions(self):
        """Load sessions from a file"""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    self.sessions = json.load(f)
            except Exception as e:
                print(f"Error loading sessions: {str(e)}")
                self.sessions = {} 
