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
import base64
import requests
from urllib.parse import quote, urlencode
from pathlib import Path
from myvnc.utils.config_loader import load_server_config
import traceback

class EntraManager:
    """Manages Microsoft Entra ID authentication for VNC Manager"""
    
    def __init__(self):
        """Initialize the Entra ID manager with credentials from environment variables or config file"""
        # Initialize logger
        self.logger = logging.getLogger('myvnc')
        
        # Load server configuration first to get config paths - use central function
        self.server_config = load_server_config()
        
        # Try to load configuration from environment variables first
        self.client_id = os.environ.get('ENTRA_CLIENT_ID')
        self.client_secret = os.environ.get('ENTRA_CLIENT_SECRET')
        self.tenant_id = os.environ.get('ENTRA_TENANT_ID')
        # Will be fully set from config file - don't use default value
        self.redirect_uri = None
        
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
    
# _load_server_config method removed - using central load_server_config function instead
        
    def _load_config_from_file(self):
        """Load Entra ID configuration from the config file"""
        try:
            # Get the path from server config - this should be the absolute path
            config_path_str = self.server_config.get('entra_config')
            self.logger.info(f"DEBUG EntraManager: Server config provides entra_config path: {config_path_str}")
            
            if not config_path_str:
                # Fallback to default path
                config_path_str = "config/auth/entra_config.json"
                # Resolve relative path from the application root
                config_path = Path(__file__).parent.parent.parent / config_path_str
                self.logger.info(f"DEBUG EntraManager: Using default relative path: {config_path}")
            else:
                # Use the absolute path directly from server config
                config_path = Path(config_path_str)
                self.logger.info(f"DEBUG EntraManager: Using absolute path from server config: {config_path}")
            
            self.logger.info(f"DEBUG EntraManager: Checking if file exists at: {config_path}")
            
            # Check if the file exists
            if not config_path.exists():
                self.logger.error(f"Entra ID config file not found: {config_path}")
                return
            
            self.logger.info(f"DEBUG EntraManager: File exists, loading config from: {config_path}")
            
            # Load the config file
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            self.logger.info(f"DEBUG EntraManager: Successfully loaded config JSON with keys: {list(config.keys())}")
            
            # Set the configuration values if not already set from environment variables
            if not self.client_id and 'client_id' in config:
                self.client_id = config['client_id']
                self.logger.info(f"Using client_id from config: {self.client_id}")
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_CLIENT_ID'] = self.client_id
                
            if not self.client_secret and 'client_secret' in config:
                self.client_secret = config['client_secret']
                self.logger.info("Loaded client_secret from config")
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_CLIENT_SECRET'] = self.client_secret
                
            if not self.tenant_id and 'tenant_id' in config:
                self.tenant_id = config['tenant_id']
                self.logger.info(f"Using tenant_id from config: {self.tenant_id}")
                # Set as environment variable to be accessible to other components
                os.environ['ENTRA_TENANT_ID'] = self.tenant_id
                
            # ALWAYS use the redirect_uri from config file
            if 'redirect_uri' in config:
                self.redirect_uri = config['redirect_uri']
                self.logger.info(f"Using redirect_uri from config: {self.redirect_uri}")
                # Set as environment variable 
                os.environ['ENTRA_REDIRECT_URI'] = self.redirect_uri
            else:
                self.logger.error("No redirect_uri found in Entra config file!")
                
            if 'scopes' in config and config['scopes']:
                self.scopes = config['scopes']
                self.logger.info(f"DEBUG EntraManager: Using scopes from config: {self.scopes}")
                
            self.logger.info(f"Successfully loaded Entra ID configuration from {config_path}")
        except Exception as e:
            self.logger.error(f"Error loading Entra ID config from file: {str(e)}")
            self.logger.error(f"Exception details: {traceback.format_exc()}")
    
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

    # App-only Graph lookups survive per-request EntraManager construction.
    _graph_app_token = {"access_token": None, "expires_at": 0.0}
    _account_status_cache = {}
    _graph_lookup_disabled_until = 0.0
    _last_lookup_error = None
    _ACCOUNT_STATUS_TTL = 300
    _GRAPH_PERMISSION_RETRY = 600
    _ACCOUNT_READ_ROLES = frozenset({
        "User.Read.All",
        "User.ReadWrite.All",
        "Directory.Read.All",
        "Directory.ReadWrite.All",
    })

    def get_users_account_enabled(self, usernames):
        """Look up Entra accountEnabled for Linux/VNC usernames.

        Uses the client-credentials (app-only) flow so Manager Mode can query
        users other than the signed-in manager. Requires the Entra app to have
        Microsoft Graph application permission User.Read.All (admin consent).

        Args:
            usernames: Iterable of usernames (typically onPremisesSamAccountName
                / mailNickname / UPN prefix).

        Returns:
            dict mapping each username to True, False, or None if unknown.
        """
        unique_names = []
        seen = set()
        for name in usernames or []:
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            unique_names.append(name)

        if not unique_names:
            EntraManager._last_lookup_error = None
            return {}

        if not all([self.client_id, self.client_secret, self.tenant_id]):
            EntraManager._last_lookup_error = "Entra app credentials are not configured"
            self.logger.warning("Skipping Entra accountEnabled lookup: app credentials are not configured")
            return {}

        now = time.time()
        if now < EntraManager._graph_lookup_disabled_until:
            if not EntraManager._last_lookup_error:
                EntraManager._last_lookup_error = (
                    "Microsoft Graph denied the lookup. Grant this app the Microsoft Graph "
                    "application permission User.Read.All and admin consent."
                )
            self.logger.debug("Skipping Entra accountEnabled lookup: previous Graph permission error still in cooldown")
            return {}

        EntraManager._last_lookup_error = None

        status = {name: None for name in unique_names}

        uncached = []
        for name in unique_names:
            cached = EntraManager._account_status_cache.get(name.lower())
            if cached and cached.get("expires_at", 0) > now:
                status[name] = cached.get("enabled")
            else:
                uncached.append(name)

        if not uncached:
            return status

        token = self._get_graph_app_token()
        if not token:
            EntraManager._last_lookup_error = "Could not acquire a Microsoft Graph app token"
            return {} if not any(value is not None for value in status.values()) else status

        if not self._token_can_read_accounts(token):
            self._handle_graph_permission_error("app token has no User.Read.All / Directory.Read.All role")
            return {} if not any(value is not None for value in status.values()) else status

        try:
            found = self._query_graph_account_enabled(token, uncached)
        except Exception as e:
            EntraManager._last_lookup_error = f"Entra accountEnabled lookup failed: {e}"
            self.logger.error(f"Entra accountEnabled lookup failed: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {} if not any(value is not None for value in status.values()) else status

        if time.time() < EntraManager._graph_lookup_disabled_until:
            if not any(value is not None for value in status.values()):
                return {}
            return status

        expires_at = now + EntraManager._ACCOUNT_STATUS_TTL
        for name in uncached:
            enabled = found.get(name.lower())
            status[name] = enabled
            EntraManager._account_status_cache[name.lower()] = {
                "enabled": enabled,
                "expires_at": expires_at,
            }

        disabled_count = sum(1 for value in status.values() if value is False)
        self.logger.info(
            f"Entra accountEnabled lookup: {len(unique_names)} users, "
            f"{len(uncached)} queried, {disabled_count} disabled"
        )
        return status

    def _get_graph_app_token(self):
        """Acquire a Microsoft Graph app-only access token via client credentials."""
        now = time.time()
        cached = EntraManager._graph_app_token
        if cached.get("access_token") and cached.get("expires_at", 0) > now + 60:
            return cached["access_token"]

        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        }

        try:
            response = requests.post(self.token_endpoint, data=token_data, timeout=15)
            if response.status_code != 200:
                self.logger.error(
                    f"Entra client-credentials token request failed: "
                    f"{response.status_code} - {response.text}"
                )
                return None

            token_info = response.json()
            access_token = token_info.get("access_token")
            if not access_token:
                self.logger.error("Entra client-credentials response did not include an access_token")
                return None

            expires_in = int(token_info.get("expires_in", 3600))
            EntraManager._graph_app_token = {
                "access_token": access_token,
                "expires_at": now + expires_in,
            }
            return access_token
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Entra client-credentials token request failed: {str(e)}")
            return None

    def _query_graph_account_enabled(self, access_token, usernames):
        """Query Graph for accountEnabled, keyed by lowercase username."""
        found = {}
        remaining = list(usernames)

        # mailNickname / UPN prefix covers most cloud and synced users.
        batch_requests = []
        for index, name in enumerate(remaining):
            escaped = self._odata_escape(name)
            filter_expr = (
                f"mailNickname eq '{escaped}' or "
                f"startswith(userPrincipalName,'{escaped}@')"
            )
            batch_requests.append({
                "id": str(index),
                "method": "GET",
                "url": self._graph_users_query_url(filter_expr),
            })

        self._run_graph_batches(access_token, batch_requests, remaining, found)
        if time.time() < EntraManager._graph_lookup_disabled_until:
            return found

        missing = [name for name in remaining if name.lower() not in found]
        if missing:
            # Hybrid-synced AD accounts often match onPremisesSamAccountName only.
            sam_requests = []
            for index, name in enumerate(missing):
                escaped = self._odata_escape(name)
                sam_requests.append({
                    "id": str(index),
                    "method": "GET",
                    "headers": {"ConsistencyLevel": "eventual"},
                    "url": self._graph_users_query_url(
                        f"onPremisesSamAccountName eq '{escaped}'",
                        include_count=True,
                    ),
                })
            self._run_graph_batches(access_token, sam_requests, missing, found)

        return found

    def _run_graph_batches(self, access_token, batch_requests, usernames, found):
        """Execute Graph JSON batch requests in chunks of 20 and merge matches."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        for offset in range(0, len(batch_requests), 20):
            chunk = batch_requests[offset:offset + 20]
            try:
                response = requests.post(
                    f"{self.graph_endpoint}/$batch",
                    headers=headers,
                    json={"requests": chunk},
                    timeout=30,
                )
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Graph $batch request failed: {str(e)}")
                continue

            if response.status_code == 403:
                self._handle_graph_permission_error(response.text)
                return
            if response.status_code != 200:
                self.logger.error(
                    f"Graph $batch failed: {response.status_code} - {response.text}"
                )
                continue

            try:
                payload = response.json()
            except ValueError:
                self.logger.error("Graph $batch returned non-JSON body")
                continue

            for item in payload.get("responses", []):
                request_id = item.get("id")
                try:
                    username = usernames[int(request_id)]
                except (TypeError, ValueError, IndexError):
                    continue

                status_code = item.get("status", 0)
                body = item.get("body") or {}
                if status_code == 403:
                    self._handle_graph_permission_error(json.dumps(body))
                    return
                if status_code != 200:
                    self.logger.debug(
                        f"Graph user lookup for {username} returned {status_code}: {body}"
                    )
                    continue

                match = self._best_graph_user_match(username, body.get("value") or [])
                if match is not None:
                    found[username.lower()] = bool(match.get("accountEnabled"))

    def _best_graph_user_match(self, username, users):
        """Pick the Graph user that best matches a VNC/Linux username."""
        if not users:
            return None

        target = username.lower()

        def mail_nickname(user):
            return (user.get("mailNickname") or "").lower()

        def sam_account(user):
            return (user.get("onPremisesSamAccountName") or "").lower()

        def upn_prefix(user):
            upn = user.get("userPrincipalName") or ""
            return upn.split("@", 1)[0].lower()

        for predicate in (mail_nickname, sam_account, upn_prefix):
            for user in users:
                if predicate(user) == target:
                    return user
        return users[0]

    def _graph_users_query_url(self, filter_expr, include_count=False):
        """Build a relative Graph /users query URL with encoded parameters."""
        params = [
            ("$filter", filter_expr),
            ("$select", "accountEnabled,mailNickname,userPrincipalName,onPremisesSamAccountName,displayName"),
            ("$top", "5"),
        ]
        if include_count:
            params.append(("$count", "true"))
        return "/users?" + urlencode(params, quote_via=quote)

    def _token_can_read_accounts(self, access_token):
        """Return True if the app-only token includes a Graph role that can read accountEnabled."""
        try:
            payload = access_token.split(".")[1]
            payload += "=" * ((4 - len(payload) % 4) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            roles = set(claims.get("roles") or [])
            return bool(roles & EntraManager._ACCOUNT_READ_ROLES)
        except Exception:
            # If the token cannot be decoded, try the Graph call and handle 403 there.
            return True

    def _handle_graph_permission_error(self, details):
        """Log a warning when the app lacks User.Read.All."""
        EntraManager._graph_lookup_disabled_until = time.time() + EntraManager._GRAPH_PERMISSION_RETRY
        EntraManager._last_lookup_error = (
            "Microsoft Graph denied the lookup. Grant this app the Microsoft Graph "
            "application permission User.Read.All and admin consent."
        )
        self.logger.warning(
            "Entra accountEnabled lookup was denied by Microsoft Graph. "
            "Grant the app the Microsoft Graph application permission "
            "User.Read.All (admin consent required) so Manager Mode can show "
            f"disabled accounts. Details: {details}"
        )

    @staticmethod
    def _odata_escape(value):
        """Escape a string for use inside an OData single-quoted literal."""
        return str(value).replace("'", "''") 