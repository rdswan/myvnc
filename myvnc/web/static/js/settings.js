/**
 * User settings functionality for MyVNC
 */

// Global variables
let vncSettingsOptions = {};
let currentUserSettings = {};
let defaultSettings = {};

// DOM elements
const settingsModal = document.getElementById('settings-modal');
const closeButton = document.getElementById('settings-close');
const saveButton = document.getElementById('settings-save');
const resetButton = document.getElementById('settings-reset');
const saveStatus = document.getElementById('save-status');

// Form elements
const resolutionSelect = document.getElementById('settings-resolution');
const windowManagerSelect = document.getElementById('settings-window-manager');
const siteSelect = document.getElementById('settings-site');

// Initialize settings when document is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing settings module');
    
    // Add event listeners
    if (closeButton) {
        closeButton.addEventListener('click', closeSettingsModal);
    }
    
    if (saveButton) {
        saveButton.addEventListener('click', saveUserSettings);
    }
    
    if (resetButton) {
        resetButton.addEventListener('click', resetToDefaults);
    }
    
    // Close modal when clicking outside of it
    window.addEventListener('click', function(event) {
        if (event.target === settingsModal) {
            closeSettingsModal();
        }
    });
    
    // If escape key is pressed, close the modal
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && settingsModal.classList.contains('active')) {
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
    console.log('Closing settings modal');
    settingsModal.classList.remove('active');
    
    // Clear save status
    setSaveStatus('');
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
 * Reset form to system defaults
 */
function resetToDefaults() {
    console.log('Resetting settings to defaults');
    
    // Confirm with user
    if (confirm('Are you sure you want to reset all settings to system defaults?')) {
        // Clear user settings
        currentUserSettings = {};
        
        // Populate form with default settings
        populateSettingsForm({
            vnc_settings: { ...defaultSettings.vnc_settings }
        });
        
        // Save empty settings to server (effectively removing user settings)
        saveUserSettings();
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
        
        // Set saving status
        setSaveStatus('Saving...', '');
        
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
            setSaveStatus('Settings saved successfully!', 'success');
            
            // Update current user settings
            currentUserSettings = settings;
            
            // Reload VNC configuration to update all defaults
            if (typeof loadVNCConfig === 'function') {
                loadVNCConfig();
            }
            
            // Close modal after a delay
            setTimeout(closeSettingsModal, 1500);
        } else {
            console.error('Error saving settings:', data ? data.message : 'Unknown error');
            setSaveStatus(`Error: ${data ? data.message : 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        setSaveStatus(`Error: ${error.message}`, 'error');
    }
}

/**
 * Set save status message
 */
function setSaveStatus(message, type = '') {
    if (!saveStatus) return;
    
    saveStatus.textContent = message;
    saveStatus.className = 'save-status';
    
    if (type) {
        saveStatus.classList.add(type);
    }
}

// Export functions for global use
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal; 