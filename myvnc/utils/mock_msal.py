"""
Mock MSAL implementation for testing Entra ID integration
This module provides a minimal mock of the MSAL (Microsoft Authentication Library) 
for testing purposes when the real library cannot be installed.
"""

class ConfidentialClientApplication:
    """
    Mock implementation of MSAL's ConfidentialClientApplication
    """
    
    def __init__(self, client_id, authority=None, client_credential=None, **kwargs):
        """Initialize the client application"""
        self.client_id = client_id
        self.authority = authority
        self.client_credential = client_credential
        self.kwargs = kwargs
        print(f"Mock MSAL: Initialized with client_id={client_id}, authority={authority}")
    
    def acquire_token_by_username_password(self, username, password, scopes=None, **kwargs):
        """
        Mock implementation of username/password auth flow
        In a real application, this would contact Microsoft's servers
        """
        print(f"Mock MSAL: Authentication attempt for {username}")
        
        # For testing, accept any username that ends with @tenstorrent.com and 
        # any password that's at least 8 characters
        if username.endswith('@tenstorrent.com') and len(password) >= 8:
            return {
                'access_token': 'mock_access_token_' + username.split('@')[0],
                'id_token': 'mock_id_token',
                'expires_in': 3600,
                'user_id': username
            }
        else:
            return {
                'error': 'invalid_grant',
                'error_description': 'AADSTS50126: Invalid username or password'
            }
    
    def acquire_token_by_authorization_code(self, code, scopes, redirect_uri=None, **kwargs):
        """
        Mock implementation of authorization code flow
        In a real application, this would exchange the code for tokens
        """
        print(f"Mock MSAL: Authorization code exchange with code={code[:5]}...")
        
        # For testing, accept any code that starts with 'valid'
        if code.startswith('valid'):
            return {
                'access_token': 'mock_access_token_from_code',
                'id_token': 'mock_id_token',
                'expires_in': 3600,
                'user_id': 'user@tenstorrent.com'
            }
        else:
            return {
                'error': 'invalid_grant',
                'error_description': 'AADSTS70002: Invalid authorization code'
            }
    
    def get_authorization_request_url(self, scopes, redirect_uri=None, response_type="code", prompt=None, **kwargs):
        """
        Mock implementation of authorization URL generation
        In a real application, this would generate the URL to redirect users to
        """
        # Generate a mock URL that would normally point to Microsoft's login page
        query_params = f"client_id={self.client_id}&response_type={response_type}&redirect_uri={redirect_uri}"
        return f"https://login.microsoftonline.com/mock/oauth2/v2.0/authorize?{query_params}" 