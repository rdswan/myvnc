# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""
LDAP authentication handler for VNC Manager
"""

import os
import sys
import uuid
import time
import json
import logging
from pathlib import Path

# Try to import ldap package
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

class LDAPManager:
    """Manages LDAP authentication for VNC Manager"""
    
    def __init__(self):
        """Initialize the LDAP manager with credentials from environment or config"""
        # Load server configuration
        self.config = self._load_config()
        
        # Get LDAP settings from environment variables or config
        self.ldap_server = os.environ.get('LDAP_SERVER', self.config.get('ldap_server', 'ldap://localhost:389'))
        self.ldap_domain = os.environ.get('LDAP_DOMAIN', self.config.get('ldap_domain', 'example.com'))
        self.ldap_base_dn = os.environ.get('LDAP_BASE_DN', self.config.get('ldap_base_dn', 'dc=example,dc=com'))
        self.ldap_user_filter = os.environ.get('LDAP_USER_FILTER', self.config.get('ldap_user_filter', '(sAMAccountName=%s)'))
        self.ldap_group_filter = os.environ.get('LDAP_GROUP_FILTER', self.config.get('ldap_group_filter', '(&(objectClass=group)(member=%s))'))
        self.ldap_attr_username = os.environ.get('LDAP_ATTR_USERNAME', self.config.get('ldap_attr_username', 'sAMAccountName'))
        self.ldap_attr_display_name = os.environ.get('LDAP_ATTR_DISPLAY_NAME', self.config.get('ldap_attr_display_name', 'displayName'))
        self.ldap_attr_email = os.environ.get('LDAP_ATTR_EMAIL', self.config.get('ldap_attr_email', 'mail'))
        self.ldap_attr_groups = os.environ.get('LDAP_ATTR_GROUPS', self.config.get('ldap_attr_groups', 'memberOf'))
        self.ldap_admin_binddn = os.environ.get('LDAP_ADMIN_BINDDN', self.config.get('ldap_admin_binddn', ''))
        self.ldap_admin_password = os.environ.get('LDAP_ADMIN_PASSWORD', self.config.get('ldap_admin_password', ''))
        
        # Session tracking
        self.sessions = {}
        self.logger = logging.getLogger('myvnc')
    
    def _load_config(self):
        """Load LDAP configuration from JSON file"""
        config_path = Path(__file__).parent.parent.parent / "config" / "auth" / "ldap_config.json"
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading LDAP config: {str(e)}")
        
        # Return empty config if not found
        return {}
    
    def authenticate(self, username, password):
        """
        Authenticate a user with LDAP
        
        Args:
            username: Username (without domain) 
            password: Password
            
        Returns:
            Tuple of (success, message, user_info)
        """
        if not LDAP_AVAILABLE:
            return False, "LDAP authentication is not available", None
        
        try:
            # Initialize LDAP connection
            self.logger.info(f"Connecting to LDAP server at {self.ldap_server}")
            conn = ldap.initialize(self.ldap_server)
            conn.set_option(ldap.OPT_REFERRALS, 0)
            
            # User bind DN format - supports both UPN (user@domain) and DN (cn=user,dc=domain,dc=com) formats
            if '@' not in username and ',' not in username:
                user_dn = f"{username}@{self.ldap_domain}"
            else:
                user_dn = username
                
            # Try to bind with user credentials
            self.logger.info(f"Attempting to authenticate user: {user_dn}")
            conn.simple_bind_s(user_dn, password)
            
            # Get user info with user's account or admin account if available
            user_info = self._get_user_info(conn, username, user_dn)
            
            # Unbind and close connection
            conn.unbind()
            
            if not user_info:
                return False, "User found but unable to retrieve details", None
            
            return True, "Authentication successful", user_info
            
        except ldap.INVALID_CREDENTIALS:
            self.logger.warning(f"Invalid credentials for user: {username}")
            return False, "Invalid username or password", None
        except ldap.SERVER_DOWN:
            self.logger.error(f"LDAP server is down or not reachable: {self.ldap_server}")
            return False, "LDAP server is not available", None
        except ldap.LDAPError as e:
            self.logger.error(f"LDAP error authenticating {username}: {str(e)}")
            return False, f"LDAP error: {str(e)}", None
        except Exception as e:
            self.logger.error(f"Unexpected error during LDAP authentication: {str(e)}")
            return False, f"Authentication error: {str(e)}", None
    
    def _get_user_info(self, conn, username, user_dn):
        """
        Get user information from LDAP
        
        Args:
            conn: LDAP connection
            username: Username to search for
            user_dn: User distinguished name or UPN
            
        Returns:
            Dictionary with user information
        """
        try:
            # Prepare the LDAP search filter
            search_filter = self.ldap_user_filter.replace('%s', username)
            
            # Define the attributes to retrieve
            attributes = [
                self.ldap_attr_username,
                self.ldap_attr_display_name,
                self.ldap_attr_email,
                self.ldap_attr_groups
            ]
            
            # Search for user details
            self.logger.info(f"Searching for user with filter: {search_filter}")
            result = conn.search_s(
                self.ldap_base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                attributes
            )
            
            # Process results
            if not result or len(result) == 0:
                self.logger.warning(f"No LDAP user found matching filter: {search_filter}")
                return None
            
            # Get user entry details
            user_entry = result[0]
            user_dn = user_entry[0]
            user_attrs = user_entry[1]
            
            # Extract user information with fallbacks
            user_info = {
                'username': self._get_ldap_attribute(user_attrs, self.ldap_attr_username, username),
                'display_name': self._get_ldap_attribute(user_attrs, self.ldap_attr_display_name, username),
                'email': self._get_ldap_attribute(user_attrs, self.ldap_attr_email, f"{username}@{self.ldap_domain}"),
                'groups': [],
                'dn': user_dn
            }
            
            # Extract group memberships
            if self.ldap_attr_groups in user_attrs:
                for group_dn in user_attrs[self.ldap_attr_groups]:
                    group_dn_str = group_dn.decode('utf-8')
                    # Extract CN from the DN - typical format is CN=GroupName,OU=Groups,DC=domain,DC=com
                    if group_dn_str.startswith('CN='):
                        cn_part = group_dn_str.split(',')[0]
                        group_name = cn_part[3:]  # Remove 'CN=' prefix
                        user_info['groups'].append(group_name)
            
            self.logger.info(f"Successfully retrieved info for user: {user_info['username']}")
            return user_info
            
        except ldap.LDAPError as e:
            self.logger.error(f"LDAP error getting user info: {str(e)}")
            return None
    
    def _get_ldap_attribute(self, attrs, attr_name, default_value):
        """
        Helper to get an LDAP attribute with proper decoding
        
        Args:
            attrs: Dictionary of attributes
            attr_name: Name of the attribute to get
            default_value: Default value if attribute not found
            
        Returns:
            String value of the attribute
        """
        if attr_name in attrs and attrs[attr_name]:
            try:
                # LDAP attributes are binary, decode to UTF-8
                return attrs[attr_name][0].decode('utf-8')
            except (UnicodeDecodeError, AttributeError, IndexError):
                return default_value
        return default_value
    
    def create_session(self, user_info):
        """
        Create a new session for the authenticated user
        
        Args:
            user_info: Dictionary with user information
            
        Returns:
            Session ID string
        """
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Create session with timestamp
        session = {
            'username': user_info['username'],
            'display_name': user_info['display_name'],
            'email': user_info['email'],
            'groups': user_info.get('groups', []),
            'created_at': time.time(),
            'last_access': time.time()
        }
        
        # Store session
        self.sessions[session_id] = session
        
        return session_id
    
    def validate_session(self, session_id):
        """
        Validate a user session
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            Tuple of (success, session_data or None)
        """
        if not session_id or session_id not in self.sessions:
            return False, "Invalid session", None
        
        # Get session
        session = self.sessions[session_id]
        
        # Update last access time
        session['last_access'] = time.time()
        
        return True, "Session valid", session
    
    def end_session(self, session_id):
        """
        End a user session
        
        Args:
            session_id: Session ID to end
            
        Returns:
            Tuple of (success, message)
        """
        if session_id in self.sessions:
            # Remove session
            self.sessions.pop(session_id)
            return True, "Session ended"
        
        return False, "Session not found" 