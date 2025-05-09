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
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        const dropdowns = document.getElementsByClassName('dropdown-content');
        for (let i = 0; i < dropdowns.length; i++) {
            const openDropdown = dropdowns[i];
            if (openDropdown.classList.contains('show')) {
                openDropdown.classList.remove('show');
            }
        }
    });
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
                
                // Dispatch an event to notify other scripts that the user is authenticated
                const authEvent = new CustomEvent('userAuthenticated', { 
                    detail: { 
                        username: data.username,
                        authenticated: true 
                    } 
                });
                document.dispatchEvent(authEvent);
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
            
            // Dispatch event for anonymous user
            const authEvent = new CustomEvent('userAuthenticated', { 
                detail: { 
                    username: 'anonymous',
                    authenticated: false
                } 
            });
            document.dispatchEvent(authEvent);
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
    
    // Only show user dropdown if not anonymous user
    if (userData.username && userData.username !== 'anonymous') {
        console.log('Showing user dropdown for authenticated user:', userData.username);
        
        // Create user dropdown container
        const userDropdown = document.createElement('div');
        userDropdown.className = 'user-dropdown';
        
        // Add user name span with dropdown icon
        const nameSpan = document.createElement('div');
        nameSpan.className = 'user-name';
        nameSpan.innerHTML = `${displayName} <i class="fas fa-chevron-down"></i>`;
        nameSpan.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            dropdownContent.classList.toggle('show');
            
            // Close dropdown when clicking outside
            const closeDropdownHandler = function(event) {
                if (!nameSpan.contains(event.target) && !dropdownContent.contains(event.target)) {
                    dropdownContent.classList.remove('show');
                    document.removeEventListener('click', closeDropdownHandler);
                }
            };
            
            // Add the event listener only when dropdown is shown
            if (dropdownContent.classList.contains('show')) {
                // Use setTimeout to ensure this event listener is added after the current event is processed
                setTimeout(() => {
                    document.addEventListener('click', closeDropdownHandler);
                }, 0);
            }
        });
        userDropdown.appendChild(nameSpan);
        
        // Create dropdown content
        const dropdownContent = document.createElement('div');
        dropdownContent.className = 'dropdown-content';
        
        // Add settings option
        const settingsLink = document.createElement('a');
        settingsLink.href = '#';
        settingsLink.innerHTML = '<i class="fas fa-cog"></i> Settings';
        settingsLink.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation(); // Prevent event from bubbling up
            
            // Hide dropdown
            dropdownContent.classList.remove('show');
            
            console.log('===== SETTINGS BUTTON CLICKED =====');
            console.log('Settings link clicked - attempting to open settings modal');
            console.log('openSettingsModal in current scope:', typeof openSettingsModal);
            console.log('window.openSettingsModal:', typeof window.openSettingsModal);
            
            // First fetch settings from API, then show modal
            fetch('/api/config/vnc')
                .then(response => response.json())
                .then(vncConfig => {
                    console.log('VNC settings loaded:', vncConfig);
                    
                    // DIRECT APPROACH: Get the modal element and show it
                    const modalElement = document.getElementById('settings-modal');
                    if (modalElement) {
                        console.log('Found settings modal element directly, showing it');
                        
                        // First populate dropdowns
                        const resolutionSelect = document.getElementById('settings-resolution');
                        const windowManagerSelect = document.getElementById('settings-window-manager');
                        const siteSelect = document.getElementById('settings-site');
                        
                        // Populate resolution options
                        if (resolutionSelect) {
                            resolutionSelect.innerHTML = '';
                            vncConfig.resolutions.forEach(resolution => {
                                const option = document.createElement('option');
                                option.value = resolution;
                                option.textContent = resolution;
                                resolutionSelect.appendChild(option);
                            });
                        }
                        
                        // Populate window manager options
                        if (windowManagerSelect) {
                            windowManagerSelect.innerHTML = '';
                            vncConfig.window_managers.forEach(wm => {
                                const option = document.createElement('option');
                                option.value = wm;
                                option.textContent = wm;
                                windowManagerSelect.appendChild(option);
                            });
                        }
                        
                        // Populate site options
                        if (siteSelect) {
                            siteSelect.innerHTML = '';
                            vncConfig.sites.forEach(site => {
                                const option = document.createElement('option');
                                option.value = site;
                                option.textContent = site;
                                siteSelect.appendChild(option);
                            });
                        }
                        
                        // Then load user settings
                        fetch('/api/user/settings')
                            .then(response => response.json())
                            .then(userData => {
                                console.log('User settings loaded:', userData);
                                
                                // Apply user settings if available
                                if (userData.success && userData.settings && userData.settings.vnc_settings) {
                                    const settings = userData.settings.vnc_settings;
                                    
                                    // Set selected values
                                    if (resolutionSelect && settings.resolution) {
                                        for (let i = 0; i < resolutionSelect.options.length; i++) {
                                            if (resolutionSelect.options[i].value === settings.resolution) {
                                                resolutionSelect.selectedIndex = i;
                                                break;
                                            }
                                        }
                                    }
                                    
                                    if (windowManagerSelect && settings.window_manager) {
                                        for (let i = 0; i < windowManagerSelect.options.length; i++) {
                                            if (windowManagerSelect.options[i].value === settings.window_manager) {
                                                windowManagerSelect.selectedIndex = i;
                                                break;
                                            }
                                        }
                                    }
                                    
                                    if (siteSelect && settings.site) {
                                        for (let i = 0; i < siteSelect.options.length; i++) {
                                            if (siteSelect.options[i].value === settings.site) {
                                                siteSelect.selectedIndex = i;
                                                break;
                                            }
                                        }
                                    }
                                } else {
                                    console.log('No user settings found, using defaults');
                                    
                                    // Use default values from VNC config
                                    if (resolutionSelect && vncConfig.defaults && vncConfig.defaults.resolution) {
                                        for (let i = 0; i < resolutionSelect.options.length; i++) {
                                            if (resolutionSelect.options[i].value === vncConfig.defaults.resolution) {
                                                resolutionSelect.selectedIndex = i;
                                                break;
                                            }
                                        }
                                    }
                                    
                                    if (windowManagerSelect && vncConfig.defaults && vncConfig.defaults.window_manager) {
                                        for (let i = 0; i < windowManagerSelect.options.length; i++) {
                                            if (windowManagerSelect.options[i].value === vncConfig.defaults.window_manager) {
                                                windowManagerSelect.selectedIndex = i;
                                                break;
                                            }
                                        }
                                    }
                                    
                                    if (siteSelect && vncConfig.defaults && vncConfig.defaults.site) {
                                        for (let i = 0; i < siteSelect.options.length; i++) {
                                            if (siteSelect.options[i].value === vncConfig.defaults.site) {
                                                siteSelect.selectedIndex = i;
                                                break;
                                            }
                                        }
                                    }
                                }
                                
                                // Finally show the modal
                                modalElement.classList.add('active');
                                modalElement.style.display = 'flex';
                                modalElement.style.opacity = '1';
                                modalElement.style.visibility = 'visible';
                                console.log('Modal should now be visible with populated dropdowns');
                            })
                            .catch(error => {
                                console.error('Error loading user settings:', error);
                                // Show modal anyway
                                modalElement.classList.add('active');
                                modalElement.style.display = 'flex';
                                modalElement.style.opacity = '1';
                                modalElement.style.visibility = 'visible';
                            });
                    } else {
                        console.error('Could not find settings-modal element in the DOM');
                        // Fallback to the standard approach
                        showSettingsModal();
                    }
                })
                .catch(error => {
                    console.error('Error loading VNC config:', error);
                    // Fallback to the standard approach
                    showSettingsModal();
                });
        });
        dropdownContent.appendChild(settingsLink);
        
        // Add logout option
        const logoutLink = document.createElement('a');
        logoutLink.href = '#';
        logoutLink.innerHTML = '<i class="fas fa-sign-out-alt"></i> Logout';
        logoutLink.addEventListener('click', function(e) {
            e.preventDefault();
            handleLogout();
        });
        dropdownContent.appendChild(logoutLink);
        
        // Add dropdown content to user dropdown
        userDropdown.appendChild(dropdownContent);
        
        // Add user dropdown to container
        userInfoContainer.appendChild(userDropdown);
    } else {
        console.log('Showing anonymous user info');
        
        // Add simple user name for anonymous user
        const nameSpan = document.createElement('span');
        nameSpan.className = 'user-name';
        nameSpan.textContent = displayName;
        userInfoContainer.appendChild(nameSpan);
    }
}

/**
 * Show the settings modal
 */
function showSettingsModal() {
    console.log('showSettingsModal called');
    
    // Most direct approach first - just get the modal and show it
    const modal = document.getElementById('settings-modal');
    if (modal) {
        console.log('Found settings modal, current class:', modal.className);
        console.log('Adding active class directly');
        modal.classList.add('active');
        console.log('New class after adding active:', modal.className);
        
        // Set inline styles to force visibility if needed
        modal.style.display = 'flex';
        modal.style.opacity = '1';
        modal.style.visibility = 'visible';
        
        console.log('Applied inline styles to force visibility');
        
        return;
    }
    
    // If we couldn't find the modal element, try the other approaches
    console.log('openSettingsModal in current scope:', typeof openSettingsModal);
    console.log('window.openSettingsModal:', typeof window.openSettingsModal);
    
    // First try window-scoped function
    if (typeof window.openSettingsModal === 'function') {
        console.log('Calling window.openSettingsModal');
        window.openSettingsModal();
    }
    // Then try direct function reference
    else if (typeof openSettingsModal === 'function') {
        console.log('Calling openSettingsModal directly');
        openSettingsModal();
    }
    // Fallback implementation if the function is not found
    else {
        console.error('Settings modal function not found - all approaches failed');
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