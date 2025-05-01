/**
 * Authentication utilities for VNC Manager
 */

// Authentication State
let currentUser = null;

document.addEventListener('DOMContentLoaded', function() {
    // Check for Entra ID callback error
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('error') && urlParams.has('error_description')) {
        const errorMsg = urlParams.get('error_description');
        showLoginError(decodeURIComponent(errorMsg));
    }
    
    // Check authentication status on page load (except login page)
    if (!window.location.pathname.startsWith('/login')) {
        checkAuthentication();
    }

    // Handle login form submission
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', handleLoginSubmit);
    }

    // Handle Microsoft Entra ID login button click
    const msLoginBtn = document.getElementById('ms-login-btn');
    if (msLoginBtn) {
        msLoginBtn.addEventListener('click', handleMsLogin);
    }

    // Handle logout button click
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }
});

/**
 * Show login error message
 */
function showLoginError(message) {
    const errorContainer = document.getElementById('login-error');
    if (errorContainer) {
        errorContainer.textContent = message;
        errorContainer.style.display = 'block';
    }
}

/**
 * Check if user is authenticated
 */
function checkAuthentication() {
    console.log('Checking authentication...');
    fetch('/session')
        .then(response => {
            if (!response.ok) {
                throw new Error('Authentication check failed');
            }
            return response.json().catch(error => {
                console.error('Error parsing JSON from /session:', error);
                // Return a default response that won't break the app
                return {
                    authenticated: true,
                    username: 'anonymous',
                    display_name: 'Anonymous User'
                };
            });
        })
        .then(data => {
            console.log('Authentication response:', data);
            if (data.authenticated) {
                // User is authenticated
                currentUser = {
                    username: data.username,
                    display_name: data.display_name,
                    email: data.email,
                    groups: data.groups || []
                };
                updateUserInfo(data);
            } else {
                // User is not authenticated, redirect to login page
                // Only redirect if not on the login page already
                if (!window.location.pathname.startsWith('/login')) {
                    // Check if session expired and add query parameter
                    if (data.reason === 'expired') {
                        console.log('Session expired, redirecting to login page');
                        window.location.href = '/login?error=session_expired';
                    } else {
                        console.log('Not authenticated, redirecting to login page');
                        window.location.href = '/login';
                    }
                }
            }
        })
        .catch(error => {
            console.error('Authentication check failed:', error);
            // Assume anonymous authentication rather than redirecting to login
            // when authentication is likely disabled
            currentUser = {
                username: 'anonymous',
                display_name: 'Anonymous User',
                email: '',
                groups: []
            };
            updateUserInfo(currentUser);
        });
}

/**
 * Update user information in the UI
 */
function updateUserInfo(userData) {
    console.log('Updating UI with user info:', userData);
    const userInfoContainer = document.getElementById('user-info');
    if (!userInfoContainer) return;
    
    // Clear any existing content
    userInfoContainer.innerHTML = '';
    
    // Create user info display
    const displayName = userData.display_name || userData.username;
    
    // Add user name span
    const nameSpan = document.createElement('span');
    nameSpan.className = 'user-name';
    nameSpan.textContent = displayName;
    userInfoContainer.appendChild(nameSpan);
    
    // Only add logout button if NOT anonymous user
    if (userData.username && userData.username !== 'anonymous') {
        console.log('Showing logout button for authenticated user:', userData.username);
        
        // Create small space between name and button
        userInfoContainer.appendChild(document.createTextNode(' '));
        
        // Create logout button
        const logoutBtn = document.createElement('button');
        logoutBtn.id = 'logout-btn';
        logoutBtn.className = 'button small';
        logoutBtn.textContent = 'Logout';
        logoutBtn.addEventListener('click', handleLogout);
        
        userInfoContainer.appendChild(logoutBtn);
    } else {
        console.log('Not showing logout button for anonymous user');
    }
}

/**
 * Handle login form submission
 */
function handleLoginSubmit(event) {
    event.preventDefault();
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorContainer = document.getElementById('login-error');
    
    // Clear previous error message
    if (errorContainer) {
        errorContainer.textContent = '';
        errorContainer.style.display = 'none';
    }
    
    // Validate form
    if (!username || !password) {
        if (errorContainer) {
            errorContainer.textContent = 'Please enter username and password.';
            errorContainer.style.display = 'block';
        }
        return;
    }
    
    console.log('Sending login request for user:', username);
    
    // Show loading indicator if available
    const submitButton = document.querySelector('#login-form button[type="submit"]');
    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Signing in...';
    }
    
    // Send login request
    fetch('/api/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    })
    .then(response => {
        if (!response.ok) {
            console.error('Login request failed with status:', response.status);
            throw new Error(`Login request failed with status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Login response:', data);
        
        if (data.success) {
            // Check if we received a session ID in the response
            if (data.session_id) {
                console.log('Received session ID, redirecting to home page');
                
                // Use a small delay to ensure cookies are set before redirect
                setTimeout(() => {
                    window.location.href = '/';
                }, 100);
            } else {
                console.error('Login successful but no session ID provided');
                if (errorContainer) {
                    errorContainer.textContent = 'Login was successful but no session was created. Please try again.';
                    errorContainer.style.display = 'block';
                }
                // Reset submit button
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = 'Sign In';
                }
            }
        } else {
            console.error('Login failed:', data.message);
            // Display error message
            if (errorContainer) {
                errorContainer.textContent = data.message || 'Login failed. Please try again.';
                errorContainer.style.display = 'block';
            }
            // Reset submit button
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = 'Sign In';
            }
        }
    })
    .catch(error => {
        console.error('Login error:', error);
        if (errorContainer) {
            errorContainer.textContent = 'An error occurred during login. Please try again.';
            errorContainer.style.display = 'block';
        }
        // Reset submit button
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = 'Sign In';
        }
    });
}

/**
 * Handle Microsoft Entra ID login
 */
function handleMsLogin(event) {
    event.preventDefault();
    window.location.href = '/auth/entra';
}

/**
 * Handle logout
 */
function handleLogout(event) {
    if (event) {
        event.preventDefault();
    }
    
    fetch('/api/logout', {
        method: 'POST'
    })
    .then(() => {
        // Redirect to login page after logout
        window.location.href = '/login';
    })
    .catch(error => {
        console.error('Logout error:', error);
        // Redirect to login page even if there's an error
        window.location.href = '/login';
    });
}

// Check if the current user has a specific role
function hasRole(roleName) {
    if (!currentUser || !currentUser.user_data || !currentUser.user_data.groups) {
        return false;
    }
    
    return currentUser.user_data.groups.some(group => 
        group.toLowerCase() === roleName.toLowerCase()
    );
}

// Expose authentication functions and state
window.auth = {
    currentUser,
    checkAuthentication,
    logout: handleLogout,
    hasRole
}; 