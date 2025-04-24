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
                    window.location.href = '/login';
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
    const userInfoContainer = document.getElementById('user-info');
    if (userInfoContainer) {
        // Create user info display
        const displayName = userData.display_name || userData.username;
        userInfoContainer.innerHTML = `
            <span class="user-name">${displayName}</span>
            <button id="logout-btn" class="btn btn-sm btn-outline-light">Logout</button>
        `;

        // Add event listener to logout button
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', handleLogout);
        }
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
    
    // Send login request
    fetch('/api/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Redirect to home page on successful login
            window.location.href = '/';
        } else {
            // Display error message
            if (errorContainer) {
                errorContainer.textContent = data.message || 'Login failed. Please try again.';
                errorContainer.style.display = 'block';
            }
        }
    })
    .catch(error => {
        console.error('Login error:', error);
        if (errorContainer) {
            errorContainer.textContent = 'An error occurred during login. Please try again.';
            errorContainer.style.display = 'block';
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