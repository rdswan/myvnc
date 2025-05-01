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
import traceback
from pathlib import Path

# Try to import ldap package first (traditional python-ldap)
LDAP_TYPE = None
LDAP_AVAILABLE = False
LDAP_ERROR_DETAILS = ""

try:
    import ldap
    LDAP_TYPE = "python-ldap"
    LDAP_AVAILABLE = True
    print("Using python-ldap module for LDAP authentication")
except ImportError:
    LDAP_ERROR_DETAILS = f"python-ldap import error: {traceback.format_exc()}"
    # Try ldap3 package instead (newer LDAP library)
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL, SUBTREE, SIMPLE
        from ldap3.core.exceptions import LDAPException, LDAPBindError, LDAPInvalidCredentialsResult, LDAPSocketOpenError
        LDAP_TYPE = "ldap3"
        LDAP_AVAILABLE = True
        print("Using ldap3 module for LDAP authentication")
    except ImportError:
        LDAP_ERROR_DETAILS += f"\nldap3 import error: {traceback.format_exc()}"
        print("LDAP modules not available, LDAP authentication will be disabled")
        print(f"Import error details: {LDAP_ERROR_DETAILS}")
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
        # Initialize logger
        self.logger = logging.getLogger('myvnc')
        
        # Log LDAP availability
        if LDAP_AVAILABLE:
            self.logger.info(f"LDAP support is available using {LDAP_TYPE} library")
        else:
            self.logger.error(f"LDAP support is NOT available. Details: {LDAP_ERROR_DETAILS}")
        
        # Load server configuration first to get config paths
        self.server_config = self._load_server_config()
        
        # Load LDAP-specific configuration
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
        
        # Log LDAP configuration (masking sensitive data)
        self.logger.info(f"LDAP Server: {self.ldap_server}")
        self.logger.info(f"LDAP Domain: {self.ldap_domain}")
        self.logger.info(f"LDAP Base DN: {self.ldap_base_dn}")
        self.logger.info(f"LDAP User Filter: {self.ldap_user_filter}")
        self.logger.info(f"LDAP Admin Bind DN: {'[set]' if self.ldap_admin_binddn else '[not set]'}")
        
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
                self.logger.warning(f"Server config file not found: {config_path}")
        except Exception as e:
            self.logger.error(f"Error loading server config: {str(e)}")
        
        # Return empty config if not found
        return {}
    
    def _load_config(self):
        """Load LDAP configuration from JSON file"""
        # Get the path from server config or use the default
        config_path_str = self.server_config.get('ldap_config', "config/auth/ldap_config.json")
        
        # Handle both absolute and relative paths
        config_path = Path(config_path_str)
        if not config_path.is_absolute():
            # Resolve relative path from the application root
            config_path = Path(__file__).parent.parent.parent / config_path_str
        
        self.logger.info(f"Looking for LDAP config file at: {config_path}")
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                self.logger.info(f"Successfully loaded LDAP configuration from {config_path}")
                return config
            else:
                self.logger.warning(f"LDAP config file not found: {config_path}")
        except Exception as e:
            self.logger.error(f"Error loading LDAP config: {str(e)}")
        
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
            error_msg = f"LDAP authentication is not available. Details: {LDAP_ERROR_DETAILS}"
            self.logger.error(error_msg)
            return False, error_msg, None
        
        # Determine which LDAP library to use
        if LDAP_TYPE == "ldap3":
            return self._authenticate_ldap3(username, password)
        else:
            return self._authenticate_python_ldap(username, password)
    
    def _authenticate_ldap3(self, username, password):
        """Authenticate using ldap3 library"""
        try:
            # Determine user DN format
            if '@' not in username and ',' not in username:
                user_dn = f"{username}@{self.ldap_domain}"
            else:
                user_dn = username
                
            self.logger.info(f"Attempting to authenticate user with ldap3: {user_dn}")
            
            # Create server object
            server = Server(self.ldap_server, get_info=ALL)
            
            # Connect and bind
            conn = Connection(
                server, 
                user=user_dn, 
                password=password, 
                authentication=SIMPLE, 
                read_only=True
            )
            
            bind_result = conn.bind()
            
            if not bind_result:
                self.logger.warning(f"Authentication failed for {user_dn}: {conn.result}")
                return False, f"Authentication failed: {conn.result.get('description', 'Invalid credentials')}", None
            
            # Get user info
            self.logger.info(f"Authentication successful for {user_dn}, fetching user details")
            user_info = self._get_user_info_ldap3(conn, username, user_dn)
            
            # Close connection
            conn.unbind()
            
            if not user_info:
                return False, "User found but unable to retrieve details", None
                
            return True, "Authentication successful", user_info
            
        except LDAPBindError as e:
            self.logger.warning(f"LDAP bind error for {username}: {str(e)}")
            return False, "Invalid username or password", None
        except LDAPInvalidCredentialsResult as e:
            self.logger.warning(f"Invalid credentials for {username}: {str(e)}")
            return False, "Invalid username or password", None
        except LDAPSocketOpenError as e:
            self.logger.error(f"LDAP server connection failed: {str(e)}")
            return False, f"LDAP server is not available: {str(e)}", None
        except LDAPException as e:
            self.logger.error(f"LDAP error authenticating {username}: {str(e)}")
            return False, f"LDAP error: {str(e)}", None
        except Exception as e:
            self.logger.error(f"Unexpected error during LDAP authentication: {str(e)}")
            self.logger.error(traceback.format_exc())
            return False, f"Authentication error: {str(e)}", None
    
    def _get_user_info_ldap3(self, conn, username, user_dn):
        """Get user info using ldap3 library"""
        try:
            # Prepare search filter
            search_filter = self.ldap_user_filter.replace('%s', username)
            
            self.logger.info(f"Searching for user with filter: {search_filter}")
            
            # Define attributes to retrieve
            attributes = [
                self.ldap_attr_username,
                self.ldap_attr_display_name,
                self.ldap_attr_email,
                self.ldap_attr_groups
            ]
            
            # Search for user
            conn.search(
                self.ldap_base_dn,
                search_filter,
                search_scope=SUBTREE,
                attributes=attributes
            )
            
            if len(conn.entries) == 0:
                self.logger.warning(f"No LDAP user found matching filter: {search_filter}")
                return None
                
            # Process results
            entry = conn.entries[0]
            
            # Extract user information
            user_info = {
                'username': self._get_ldap3_attribute(entry, self.ldap_attr_username, username),
                'display_name': self._get_ldap3_attribute(entry, self.ldap_attr_display_name, username),
                'email': self._get_ldap3_attribute(entry, self.ldap_attr_email, f"{username}@{self.ldap_domain}"),
                'groups': [],
                'dn': entry.entry_dn
            }
            
            # Extract group memberships if available
            if hasattr(entry, self.ldap_attr_groups):
                for group_dn in getattr(entry, self.ldap_attr_groups).values:
                    # Extract CN from the DN - typical format is CN=GroupName,OU=Groups,DC=domain,DC=com
                    if group_dn.startswith('CN='):
                        cn_part = group_dn.split(',')[0]
                        group_name = cn_part[3:]  # Remove 'CN=' prefix
                        user_info['groups'].append(group_name)
            
            self.logger.info(f"Found user: {user_info['username']}, Groups: {user_info['groups']}")
            return user_info
            
        except Exception as e:
            self.logger.error(f"Error retrieving user info: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None
    
    def _get_ldap3_attribute(self, entry, attr_name, default_value):
        """Helper to get attributes from ldap3 entry"""
        if hasattr(entry, attr_name) and getattr(entry, attr_name).values:
            try:
                return getattr(entry, attr_name).values[0]
            except Exception:
                return default_value
        return default_value
    
    def _authenticate_python_ldap(self, username, password):
        """Authenticate using python-ldap library"""
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
            user_info = self._get_user_info_python_ldap(conn, username, user_dn)
            
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
            self.logger.error(traceback.format_exc())
            return False, f"Authentication error: {str(e)}", None
    
    def _get_user_info_python_ldap(self, conn, username, user_dn):
        """Get user information using python-ldap library"""
        try:
            # Original implementation unchanged
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
    
    def run_diagnostics(self):
        """Run diagnostics to help troubleshoot LDAP connectivity issues"""
        results = {
            "ldap_available": LDAP_AVAILABLE,
            "ldap_type": LDAP_TYPE,
            "ldap_server": self.ldap_server,
            "ldap_domain": self.ldap_domain, 
            "ldap_base_dn": self.ldap_base_dn,
            "can_connect": False,
            "errors": [],
            "warnings": []
        }
        
        if not LDAP_AVAILABLE:
            results["errors"].append(f"LDAP support is not available: {LDAP_ERROR_DETAILS}")
            self.logger.error(f"LDAP diagnostic failure: {LDAP_ERROR_DETAILS}")
            return results
            
        # Try to connect to the LDAP server without binding
        try:
            self.logger.info(f"Testing connection to LDAP server: {self.ldap_server}")
            
            if LDAP_TYPE == "ldap3":
                # Using ldap3
                from ldap3 import Server, Connection
                server = Server(self.ldap_server)
                # Try anonymous connection
                conn = Connection(server)
                result = conn.open()
                if result:
                    results["can_connect"] = True
                    self.logger.info(f"Successfully connected to LDAP server: {self.ldap_server}")
                else:
                    self.logger.error(f"Failed to connect to LDAP server: {conn.last_error}")
                    results["errors"].append(f"Connection failed: {conn.last_error}")
            else:
                # Using python-ldap
                conn = ldap.initialize(self.ldap_server)
                # Just testing if initialization works
                results["can_connect"] = True
                self.logger.info(f"Successfully initialized LDAP connection to: {self.ldap_server}")
                
            # Check if base DN is valid (if we can connect)
            if results["can_connect"]:
                try:
                    self.logger.info(f"Testing if base DN is valid: {self.ldap_base_dn}")
                    if LDAP_TYPE == "ldap3":
                        # Using ldap3
                        search_result = conn.search(self.ldap_base_dn, '(objectClass=*)', search_scope='base')
                        if not search_result:
                            results["warnings"].append(f"Base DN may not be valid: {self.ldap_base_dn}")
                            self.logger.warning(f"Base DN search failed: {conn.result}")
                        else:
                            self.logger.info(f"Base DN is valid: {self.ldap_base_dn}")
                    else:
                        # Using python-ldap
                        conn.search_s(self.ldap_base_dn, ldap.SCOPE_BASE, '(objectClass=*)')
                        self.logger.info(f"Base DN is valid: {self.ldap_base_dn}")
                except Exception as e:
                    results["warnings"].append(f"Base DN may not be valid: {str(e)}")
                    self.logger.warning(f"Error checking base DN: {str(e)}")
        except Exception as e:
            results["errors"].append(f"Connection error: {str(e)}")
            self.logger.error(f"LDAP diagnostic error: {str(e)}")
            self.logger.error(traceback.format_exc())
            
        # Log diagnostic results
        self.logger.info(f"LDAP Diagnostics complete: Available={results['ldap_available']}, Type={results['ldap_type']}, Can Connect={results['can_connect']}")
        if results["errors"]:
            self.logger.error(f"LDAP Diagnostic errors: {', '.join(results['errors'])}")
        if results["warnings"]:
            self.logger.warning(f"LDAP Diagnostic warnings: {', '.join(results['warnings'])}")
            
        return results 