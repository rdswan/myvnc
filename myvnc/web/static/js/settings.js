/**
 * User settings functionality for MyVNC
 */

// Global variables
let vncSettingsOptions = {};
let currentUserSettings = {};
let defaultSettings = {};
let settingsModal; // Use let instead of const for DOM elements to allow reassignment

// Initialize settings when document is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing settings module');
    
    // Initialize DOM element references
    settingsModal = document.getElementById('settings-modal');
    const closeButton = document.getElementById('settings-close');
    const saveButton = document.getElementById('settings-save');
    const resetButton = document.getElementById('settings-reset');
    const saveStatus = document.getElementById('save-status');
    
    // Form elements
    const resolutionSelect = document.getElementById('settings-resolution');
    const windowManagerSelect = document.getElementById('settings-window-manager');
    const siteSelect = document.getElementById('settings-site');
    
    if (!closeButton) {
        console.warn('settings-close button not found, checking for close-settings-modal');
        const altCloseButton = document.getElementById('close-settings-modal');
        if (altCloseButton) {
            console.log('Found alternative close button, attaching event listener');
            altCloseButton.addEventListener('click', closeSettingsModal);
        }
    }
    
    const saveButtonEl = saveButton || document.getElementById('save-settings');
    if (saveButtonEl) {
        console.log('Found save button, attaching event listener');
        saveButtonEl.addEventListener('click', saveUserSettings);
    } else {
        console.error('Save button not found!');
    }
    
    const resetButtonEl = resetButton || document.getElementById('settings-reset');
    if (resetButtonEl) {
        console.log('Found reset button, attaching event listener');
        resetButtonEl.addEventListener('click', resetToDefaults);
    } else {
        console.warn('Reset button not found');
    }
    
    // Add Cancel button event listener
    const cancelButton = document.getElementById('settings-cancel');
    if (cancelButton) {
        console.log('Found Cancel button, attaching event listener');
        cancelButton.addEventListener('click', function() {
            console.log('Cancel button clicked');
            closeSettingsModal();
        });
    } else {
        console.error('Cancel button not found!');
    }
    
    // Add event listeners for close button
    if (closeButton) {
        closeButton.addEventListener('click', closeSettingsModal);
    }
    
    // Close modal when clicking outside of it
    window.addEventListener('click', function(event) {
        if (event.target === settingsModal) {
            closeSettingsModal();
        }
    });
    
    // If escape key is pressed, close the modal
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && settingsModal && settingsModal.classList.contains('active')) {
            closeSettingsModal();
        }
    });
    
    // Load settings options after user authentication is checked
    document.addEventListener('userAuthenticated', loadSettingsOptions);
});

/**
 * Load settings options for the settings modal
 */
async function loadSettingsOptions() {
    try {
        console.log('Loading settings options');
        
        // Load VNC configuration
        const vncResponse = await fetch('/api/config/vnc');
        const vncConfig = await vncResponse.json();
        
        // Save options for later use
        vncSettingsOptions = {
            resolutions: vncConfig.resolutions || [],
            windowManagers: vncConfig.window_managers || [],
            sites: vncConfig.sites || []
        };
        
        // Save default settings
        defaultSettings = {
            vnc_settings: vncConfig.defaults || {}
        };
        
        console.log('Settings options loaded:', { vncSettingsOptions, defaultSettings });
        
        // Load user settings
        loadUserSettings();
        
    } catch (error) {
        console.error('Error loading settings options:', error);
    }
}

/**
 * Load user settings from server
 */
async function loadUserSettings() {
    try {
        console.log('Loading user settings');
        
        const response = await fetch('/api/user/settings');
        
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            currentUserSettings = data.settings || {};
            console.log('User settings loaded:', currentUserSettings);
        } else {
            console.warn('No settings found, using defaults');
            currentUserSettings = {};
        }
        
    } catch (error) {
        console.error('Error loading user settings:', error);
        currentUserSettings = {};
    }
}

/**
 * Open the settings modal and populate form fields
 */
function openSettingsModal() {
    // First ensure we have the latest settings
    loadSettingsOptions().then(() => {
        console.log('Opening settings modal');
        
        // Merge default settings with user settings
        const mergedSettings = {
            vnc_settings: { ...defaultSettings.vnc_settings }
        };
        
        // Apply user settings if they exist
        if (currentUserSettings.vnc_settings) {
            Object.assign(mergedSettings.vnc_settings, currentUserSettings.vnc_settings);
        }
        
        // Populate form fields
        populateSettingsForm(mergedSettings);
        
        // Show modal
        settingsModal.classList.add('active');
    });
}

/**
 * Close the settings modal
 */
function closeSettingsModal() {
    console.log('closeSettingsModal called');
    
    if (!settingsModal) {
        console.error('settingsModal element not found');
        // Try to get it again
        settingsModal = document.getElementById('settings-modal');
        if (!settingsModal) {
            console.error('Still could not find settings modal element');
            return;
        }
    }
    
    console.log('Hiding settings modal');
    // Hide the modal
    settingsModal.classList.remove('active');
    
    // Find the save status element if not available in global scope
    const saveStatusEl = document.getElementById('save-status');
    if (saveStatusEl) {
        // Clear save status
        saveStatusEl.textContent = '';
        saveStatusEl.className = 'save-status';
    }
    
    console.log('Settings modal closed');
    
    // Discard any unsaved changes by repopulating form with current settings
    // This ensures next time the modal is opened, it shows the original values
    const mergedSettings = {
        vnc_settings: { ...defaultSettings.vnc_settings }
    };
    
    // Apply saved user settings (if any)
    if (currentUserSettings.vnc_settings) {
        Object.assign(mergedSettings.vnc_settings, currentUserSettings.vnc_settings);
    }
    
    // Re-populate form with original values for next time
    setTimeout(() => {
        populateSettingsForm(mergedSettings);
    }, 300); // Small delay to ensure the modal is hidden first
}

/**
 * Populate the settings form with the provided settings
 */
function populateSettingsForm(settings) {
    console.log('Populating settings form with:', settings);
    
    // VNC settings
    const vncSettings = settings.vnc_settings || {};
    
    // Populate select options if not already populated
    populateSelectOptions(resolutionSelect, vncSettingsOptions.resolutions);
    populateSelectOptions(windowManagerSelect, vncSettingsOptions.windowManagers);
    populateSelectOptions(siteSelect, vncSettingsOptions.sites);
    
    // Set selected values based on settings
    setSelectValue(resolutionSelect, vncSettings.resolution);
    setSelectValue(windowManagerSelect, vncSettings.window_manager);
    setSelectValue(siteSelect, vncSettings.site);
}

/**
 * Populate a select element with options
 */
function populateSelectOptions(selectElement, options) {
    if (!selectElement || !options || !options.length) return;
    
    // Only populate if empty
    if (selectElement.options.length <= 1) {
        // Clear existing options
        selectElement.innerHTML = '';
        
        // Add options
        options.forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option;
            optionElement.textContent = option;
            selectElement.appendChild(optionElement);
        });
    }
}

/**
 * Set the value of a select element
 */
function setSelectValue(selectElement, value) {
    if (!selectElement || value === undefined || value === null) return;
    
    // Find option with matching value
    for (let i = 0; i < selectElement.options.length; i++) {
        if (selectElement.options[i].value == value) {
            selectElement.selectedIndex = i;
            return;
        }
    }
    
    // If no match found, add the value as an option
    const optionElement = document.createElement('option');
    optionElement.value = value;
    optionElement.textContent = value;
    selectElement.appendChild(optionElement);
    selectElement.value = value;
}

/**
 * Reset form to system defaults without confirmation
 */
function resetToDefaults(event) {
    // Prevent default button behavior
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    console.log('Immediately resetting to defaults without confirmation');
    
    try {
        // Clear user settings
        currentUserSettings = {};
        
        // Populate form with default settings
        populateSettingsForm({
            vnc_settings: { ...defaultSettings.vnc_settings }
        });
        
        // Save empty settings to server
        fetch('/api/user/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ settings: {} })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Settings reset successfully:', data);
            
            // Close modal immediately
            const settingsModal = document.getElementById('settings-modal');
            if (settingsModal) {
                settingsModal.classList.remove('active');
            }
            
            // Reload VNC configuration to update all defaults
            if (typeof loadVNCConfig === 'function') {
                loadVNCConfig();
            }
        })
        .catch(error => {
            console.error('Error resetting settings:', error);
            
            // Close modal anyway
            const settingsModal = document.getElementById('settings-modal');
            if (settingsModal) {
                settingsModal.classList.remove('active');
            }
        });
    } catch (error) {
        console.error('Error in resetToDefaults:', error);
        
        // Close modal anyway
        const settingsModal = document.getElementById('settings-modal');
        if (settingsModal) {
            settingsModal.classList.remove('active');
        }
    }
}

/**
 * Get settings from form
 */
function getFormSettings() {
    const settings = {
        vnc_settings: {
            resolution: resolutionSelect ? resolutionSelect.value : undefined,
            window_manager: windowManagerSelect ? windowManagerSelect.value : undefined,
            site: siteSelect ? siteSelect.value : undefined
        }
    };
    
    // Remove undefined values
    Object.keys(settings.vnc_settings).forEach(key => {
        if (settings.vnc_settings[key] === undefined) {
            delete settings.vnc_settings[key];
        }
    });
    
    return settings;
}

/**
 * Save user settings to server
 */
async function saveUserSettings() {
    try {
        console.log('Saving user settings');
        
        // Get settings from form
        const settings = getFormSettings();
        console.log('Settings to save:', settings);
        
        // Send settings to server
        const response = await fetch('/api/user/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ settings })
        });
        
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
        
        // Get response text first to debug
        const responseText = await response.text();
        console.log('Raw response:', responseText);
        
        // Try to parse as JSON if not empty
        let data;
        if (responseText.trim()) {
            try {
                data = JSON.parse(responseText);
            } catch (e) {
                console.error('Failed to parse response as JSON:', e);
                throw new Error('Server returned invalid JSON response');
            }
        } else {
            data = { success: false, message: 'Server returned empty response' };
        }
        
        if (data && data.success) {
            console.log('Settings saved successfully');
            
            // Update current user settings
            currentUserSettings = settings;
            
            // Reload VNC configuration to update all defaults
            if (typeof loadVNCConfig === 'function') {
                loadVNCConfig();
            }
            
            // Close modal immediately
            closeSettingsModal();
        } else {
            console.error('Error saving settings:', data ? data.message : 'Unknown error');
            
            // Close modal anyway
            closeSettingsModal();
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        
        // Close modal anyway
        closeSettingsModal();
    }
}

/**
 * Set save status message
 */
function setSaveStatus(message, type = '') {
    // Find the save status element if not available in global scope
    const saveStatusEl = document.getElementById('save-status');
    if (!saveStatusEl) {
        console.error('Save status element not found');
        return;
    }
    
    console.log('Setting save status:', message, type);
    saveStatusEl.textContent = message;
    saveStatusEl.className = 'save-status';
    
    if (type) {
        saveStatusEl.classList.add(type);
    }
}

// Export functions for global use
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.resetToDefaults = resetToDefaults;

// Log when settings module is fully loaded
console.log('Settings module loaded - openSettingsModal is available in window scope:', typeof window.openSettingsModal === 'function'); 