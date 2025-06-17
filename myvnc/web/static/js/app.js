// Global variables
let vncConfig = {};
let lsfConfig = {};

// Server config cache (to reuse between checks)
let serverConfig = {};

// Track whether current user is privileged manager
let isManagerUser = false;

// DOM Elements
let tabs = document.querySelectorAll('.tab-button');
let tabContents = document.querySelectorAll('.tab-content');
let refreshButton = document.getElementById('refresh-button');
let managerRefreshButton = document.getElementById('manager-refresh-button');
let createVNCForm = document.getElementById('create-vnc-form');
let vncTableBody = document.getElementById('vnc-table-body');
let managerTableBody = document.getElementById('manager-table-body');
let noVNCMessage = document.getElementById('no-vnc-message');
let managerNoVNCMessage = document.getElementById('manager-no-vnc-message');
const messageBox = document.getElementById('message-box');
const messageText = document.getElementById('message-text');
const messageClose = document.getElementById('message-close');

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    console.log('Application initialization started');
    
    // Initialize tabs
    tabs = document.querySelectorAll('.tab-button');
    tabContents = document.querySelectorAll('.tab-content');
    refreshButton = document.getElementById('refresh-button');
    managerRefreshButton = document.getElementById('manager-refresh-button');
    createVNCForm = document.getElementById('create-vnc-form');
    vncTableBody = document.getElementById('vnc-table-body');
    managerTableBody = document.getElementById('manager-table-body');
    noVNCMessage = document.getElementById('no-vnc-message');
    managerNoVNCMessage = document.getElementById('manager-no-vnc-message');
    
    // Immediately hide the debug tab by default (fail-safe approach)
    const debugTab = document.getElementById('debug-tab');
    if (debugTab) {
        debugTab.style.display = 'none'; // Always hide by default
        console.log('Debug tab hidden by default');
    }
    
    // Hide corresponding content tab as well
    const debugContent = document.getElementById('debug');
    if (debugContent) {
        debugContent.style.display = 'none';
        console.log('Debug content tab hidden by default');
    }
    
    // Initialize tabs functionality
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.getAttribute('data-tab');
            
            // Only allow switching to debug tab if debug mode is enabled
            if (tabId === 'debug' && debugTab.style.display === 'none') {
                console.log('Prevented switch to debug tab - debug mode not enabled');
                return; // Prevent switching to debug tab
            }
            
            changeTab(tabId);
        });
    });
    
    // Set up other event listeners
    if (refreshButton) {
        refreshButton.addEventListener('click', () => {
            refreshButton.classList.add('rotating');
            refreshButton.classList.add('refreshing');
            const originalText = '<i class="fas fa-sync-alt"></i> Refresh';
            refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refreshing...';
            
            refreshVNCList().finally(() => {
                setTimeout(() => {
                    refreshButton.classList.remove('rotating');
                    refreshButton.classList.remove('refreshing');
                    refreshButton.innerHTML = originalText;
                }, 500);
            });
        });
    }
    
    // Manager refresh button handler
    if (managerRefreshButton) {
        managerRefreshButton.addEventListener('click', () => {
            managerRefreshButton.classList.add('rotating');
            managerRefreshButton.classList.add('refreshing');
            const originalText = '<i class="fas fa-sync-alt"></i> Refresh';
            managerRefreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refreshing...';

            refreshManagerList().finally(() => {
                setTimeout(() => {
                    managerRefreshButton.classList.remove('rotating');
                    managerRefreshButton.classList.remove('refreshing');
                    managerRefreshButton.innerHTML = originalText;
                }, 500);
            });
        });
    }
    
    // Memory slider event listener
    const memorySlider = document.getElementById('lsf-memory');
    const memoryValue = document.getElementById('memory-value');
    
    if (memorySlider && memoryValue) {
        // Initialize with default value
        memoryValue.textContent = memorySlider.value;
        
        // Update the value display when slider changes
        memorySlider.addEventListener('input', function() {
            memoryValue.textContent = this.value;
        });
    }
    
    if (createVNCForm) {
        createVNCForm.addEventListener('submit', createVNCSession);
    }
    
    if (messageClose) {
        messageClose.addEventListener('click', hideMessage);
    }
    
    // Initialize collapsible sections
    initializeCollapsibleSections();
    
    // Initialize the application in a defined sequence
    initializeApplication();
    
    // Initial load of debug info when debug tab is clicked
    if (debugTab) {
        debugTab.addEventListener('click', loadDebugInfo);
    }
    
    // Enable sortable tables
    enableTableSorting('vnc-table');
    enableTableSorting('manager-table');
});

// Initialize Application
async function initializeApplication() {
    console.log('==== INITIALIZING APPLICATION ====');
    try {
        // Check if the VNC Manager tab is active (this will be true on initial page load)
        const isVncManagerActive = document.getElementById('vnc-manager').classList.contains('active');
        
        // If the VNC Manager tab is active, immediately refresh the VNC list
        if (isVncManagerActive) {
            console.log('VNC Manager tab is active, prioritizing VNC list refresh...');
            // Start refreshing VNC list immediately (don't await to allow other initialization to proceed)
            const refreshPromise = refreshVNCList();
            
            // Continue with other initialization in parallel
            await checkDebugMode();
            
            // Second redundant check after a short delay
            setTimeout(async () => {
                console.log('Performing redundant debug mode check...');
                await checkDebugMode();
            }, 1000);
            
            // Load configuration data
            console.log('Loading configuration data...');
            await Promise.all([
                loadVNCConfig(),
                loadLSFConfig()
            ]);
            
            // Setup memory slider functionality if present
            const memorySlider = document.getElementById('lsf-memory');
            if (memorySlider) {
                memorySlider.addEventListener('input', handleMemorySliderInput);
                memorySlider.addEventListener('change', handleMemorySliderChange);
            }
            
            // Wait for the VNC list refresh to complete if it hasn't already
            await refreshPromise;
        } else {
            // Standard initialization sequence if the VNC Manager tab is not active
            await checkDebugMode();
            
            setTimeout(async () => {
                console.log('Performing redundant debug mode check...');
                await checkDebugMode();
            }, 1000);
            
            // Load configuration data
            console.log('Loading configuration data...');
            await Promise.all([
                loadVNCConfig(),
                loadLSFConfig()
            ]);
            
            // Setup memory slider functionality if present
            const memorySlider = document.getElementById('lsf-memory');
            if (memorySlider) {
                memorySlider.addEventListener('input', handleMemorySliderInput);
                memorySlider.addEventListener('change', handleMemorySliderChange);
            }
            
            // Initial load of VNC sessions list
            await refreshVNCList();
        }
        
        // Register interval to periodically refresh lists
        console.log('Setting up periodic refresh interval');
        setInterval(() => {
            refreshVNCList();
            if (isManagerUser) {
                refreshManagerList();
            }
        }, 30000);
        
        console.log('==== APPLICATION INITIALIZATION COMPLETE ====');
    } catch (error) {
        console.error('Error during application initialization:', error);
    }
}

// New function to check if debug mode is enabled on the server
async function checkDebugMode() {
    try {
        // Try the server config endpoint first
        let debugEnabled = await checkDebugModeFromServerConfig();
        
        // If that didn't work, try the app_info endpoint as fallback
        if (debugEnabled === null) {
            debugEnabled = await checkDebugModeFromAppInfo();
        }
        
        // Apply the debug mode setting
        applyDebugMode(debugEnabled);
    } catch (error) {
        console.error('Error checking debug mode:', error);
        // Hide debug tab by default if there's an error
        hideDebugTab();
    }
}

// Check debug mode from server config
async function checkDebugModeFromServerConfig() {
    try {
        console.log('Fetching server config to check debug mode...');
        const response = await fetch('/api/server/config');
        
        if (!response.ok) {
            console.error('Failed to fetch server config:', response.status);
            return null;
        }
        
        const responseText = await response.text();
        console.log('Raw server config response:', responseText);
        
        const config = JSON.parse(responseText);
        console.log('Server debug mode from config API:', config.debug);
        // Cache for later use
        serverConfig = config;
        
        // Return boolean debug value
        return !!config.debug;
    } catch (error) {
        console.error('Error checking debug mode from server config:', error);
        return null;
    }
}

// Check debug mode from app info
async function checkDebugModeFromAppInfo() {
    try {
        console.log('Fetching app info to check debug mode (fallback)...');
        const response = await fetch('/api/debug/app_info');
        
        if (!response.ok) {
            console.error('Failed to fetch app info:', response.status);
            return null;
        }
        
        const responseText = await response.text();
        console.log('Raw app info response:', responseText);
        
        const data = JSON.parse(responseText);
        console.log('App info data:', data);
        
        // Try different ways the debug flag might be exposed
        const debugMode = data.app_info?.debug_mode;
        const serverDebug = data.app_info?.server_config?.debug;
        
        console.log('Debug mode from app_info API:', debugMode ?? serverDebug);
        
        // Return boolean debug value (try both possible locations)
        return !!(debugMode ?? serverDebug);
    } catch (error) {
        console.error('Error checking debug mode from app info:', error);
        return null;
    }
}

// Apply debug mode to UI
function applyDebugMode(debugEnabled) {
    console.log('Applying debug mode to UI:', debugEnabled);
    
    const debugTab = document.getElementById('debug-tab');
    const debugContent = document.getElementById('debug');
    
    if (debugTab && debugContent) {
        if (debugEnabled === true) {
            console.log('Debug mode is ON - showing debug tab');
            debugTab.style.display = 'block';
            
            // If debug tab is currently active, show its content
            if (debugTab.classList.contains('active')) {
                debugContent.style.display = 'block';
            }
        } else {
            console.log('Debug mode is OFF - hiding debug tab');
            hideDebugTab();
            
            // If debug tab was active, switch to another tab
            if (debugTab.classList.contains('active')) {
                const defaultTab = document.querySelector('.tab-button:not(#debug-tab)');
                if (defaultTab) {
                    changeTab(defaultTab.getAttribute('data-tab'));
                }
            }
        }
    } else {
        console.error('Could not find debug tab elements');
    }
}

// Helper to hide debug tab
function hideDebugTab() {
    const debugTab = document.getElementById('debug-tab');
    const debugContent = document.getElementById('debug');
    
    if (debugTab) {
        debugTab.style.display = 'none';
        console.log('Debug tab hidden');
    }
    
    if (debugContent) {
        debugContent.style.display = 'none';
        console.log('Debug content hidden');
    }
}

// Test function that can be called from browser console
async function testUserSettings() {
    console.log('==== TESTING USER SETTINGS ====');
    try {
        // First try to get the settings directly from the API
        console.log('Directly fetching user settings from API...');
        const response = await fetch('/api/user/settings');
        console.log('API response status:', response.status);
        
        const responseText = await response.text();
        console.log('Raw API response:', responseText);
        
        try {
            const data = JSON.parse(responseText);
            console.log('Parsed settings data:', data);
            
            if (data && data.success && data.settings) {
                console.log('Settings found:', data.settings);
                
                if (data.settings.vnc_settings) {
                    console.log('VNC settings:', data.settings.vnc_settings);
                } else {
                    console.warn('No VNC settings found in user settings object');
                }
            } else {
                console.warn('No settings found in response');
            }
        } catch (e) {
            console.error('Failed to parse settings JSON:', e);
        }
        
        // Now check the select elements to see what they contain
        const siteSelect = document.getElementById('vnc-site');
        const resolutionSelect = document.getElementById('vnc-resolution');
        const windowManagerSelect = document.getElementById('vnc-window-manager');
        
        console.log('Current form values:');
        console.log('Site:', siteSelect ? siteSelect.value : 'Not found');
        console.log('Resolution:', resolutionSelect ? resolutionSelect.value : 'Not found');
        console.log('Window Manager:', windowManagerSelect ? windowManagerSelect.value : 'Not found');
        
        // Now try loading with our function
        console.log('Loading via loadUserSettings function...');
        const userSettings = await loadUserSettings();
        console.log('User settings from function:', userSettings);
        
        // Force applying the settings
        if (userSettings && userSettings.vnc_settings) {
            console.log('Forcing application of settings...');
            
            if (siteSelect && userSettings.vnc_settings.site) {
                console.log(`Setting site to ${userSettings.vnc_settings.site}`);
                siteSelect.value = userSettings.vnc_settings.site;
            }
            
            if (resolutionSelect && userSettings.vnc_settings.resolution) {
                console.log(`Setting resolution to ${userSettings.vnc_settings.resolution}`);
                resolutionSelect.value = userSettings.vnc_settings.resolution;
            }
            
            if (windowManagerSelect && userSettings.vnc_settings.window_manager) {
                console.log(`Setting window manager to ${userSettings.vnc_settings.window_manager}`);
                windowManagerSelect.value = userSettings.vnc_settings.window_manager;
            }
            
            console.log('Settings application complete');
        } else {
            console.warn('No settings to apply');
        }
    } catch (error) {
        console.error('Test error:', error);
    }
    console.log('==== TEST COMPLETE ====');
}

// Export the test function to the window object so it can be called from the console
window.testUserSettings = testUserSettings;

// Load VNC Configuration
async function loadVNCConfig() {
    console.log('==== LOADING VNC CONFIGURATION ====');
    try {
        // First try to load user settings directly (most important)
        let userVncSettings = null;
        
        try {
            console.log('Fetching user settings first...');
            const userSettingsResponse = await fetch('/api/user/settings');
            const userSettingsText = await userSettingsResponse.text();
            console.log('Raw user settings response:', userSettingsText);
            
            if (userSettingsText && userSettingsText.trim()) {
                const userSettingsData = JSON.parse(userSettingsText);
                console.log('User settings response parsed:', userSettingsData);
                
                if (userSettingsData.success && userSettingsData.settings && userSettingsData.settings.vnc_settings) {
                    userVncSettings = userSettingsData.settings.vnc_settings;
                    console.log('Found user VNC settings:', userVncSettings);
                } else {
                    console.log('No user VNC settings found');
                }
            } else {
                console.log('Empty response from user settings API');
            }
        } catch (e) {
            console.warn('Error fetching user settings:', e);
        }
        
        // Load server VNC default configuration 
        console.log('Fetching server VNC configuration...');
        const vncResponse = await fetch('/api/config/vnc');
        const vncText = await vncResponse.text();
        console.log('Raw VNC config response:', vncText);
        
        vncConfig = JSON.parse(vncText);
        console.log('Server VNC config loaded:', vncConfig);
        
        // Get references to form selects before populating
        const siteSelect = document.getElementById('vnc-site');
        const resolutionSelect = document.getElementById('vnc-resolution');
        const windowManagerSelect = document.getElementById('vnc-window-manager');
        
        if (!siteSelect || !resolutionSelect || !windowManagerSelect) {
            console.error('Could not find all select elements!', {
                siteSelect: !!siteSelect,
                resolutionSelect: !!resolutionSelect,
                windowManagerSelect: !!windowManagerSelect
            });
            return;
        }
        
        // Clear and populate dropdowns with options
        clearAndPopulateDropdown(siteSelect, vncConfig.sites);
        clearAndPopulateDropdown(resolutionSelect, vncConfig.resolutions);
        clearAndPopulateDropdown(windowManagerSelect, vncConfig.window_managers);
        
        // Now set the selected values - prioritize user settings if available
        if (userVncSettings) {
            console.log('Setting dropdown values from user settings');
            
            // After populating the dropdowns, wait longer to ensure the DOM has fully updated
            // Increased from 50ms to 200ms to ensure DOM is ready
            setTimeout(() => {
                // Set site
                if (userVncSettings.site) {
                    console.log(`Setting site dropdown to: ${userVncSettings.site}`);
                    setDropdownValue(siteSelect, userVncSettings.site);
                    // Force the value directly after setting it through the function
                    if (siteSelect.value !== userVncSettings.site) {
                        console.log(`Direct force setting site to: ${userVncSettings.site}`);
                        siteSelect.value = userVncSettings.site;
                    }
                }
                
                // Set resolution
                if (userVncSettings.resolution) {
                    console.log(`Setting resolution dropdown to: ${userVncSettings.resolution}`);
                    setDropdownValue(resolutionSelect, userVncSettings.resolution);
                    // Force the value directly after setting it through the function
                    if (resolutionSelect.value !== userVncSettings.resolution) {
                        console.log(`Direct force setting resolution to: ${userVncSettings.resolution}`);
                        resolutionSelect.value = userVncSettings.resolution;
                    }
                }
                
                // Set window manager
                if (userVncSettings.window_manager) {
                    console.log(`Setting window manager dropdown to: ${userVncSettings.window_manager}`);
                    setDropdownValue(windowManagerSelect, userVncSettings.window_manager);
                    // Force the value directly after setting it through the function
                    if (windowManagerSelect.value !== userVncSettings.window_manager) {
                        console.log(`Direct force setting window manager to: ${userVncSettings.window_manager}`);
                        windowManagerSelect.value = userVncSettings.window_manager;
                    }
                }
                
                // VERIFICATION: Double-check the selected values
                console.log('VERIFICATION - Current dropdown values after setting:');
                console.log(`Site: ${siteSelect.value}`);
                console.log(`Resolution: ${resolutionSelect.value}`);
                console.log(`Window Manager: ${windowManagerSelect.value}`);
                
                // Add additional verification logging to check if any items were not found in dropdowns
                if (userVncSettings.site && siteSelect.value !== userVncSettings.site) {
                    console.warn(`Failed to set site to ${userVncSettings.site}. Options available:`, 
                        Array.from(siteSelect.options).map(o => o.value));
                }
                if (userVncSettings.resolution && resolutionSelect.value !== userVncSettings.resolution) {
                    console.warn(`Failed to set resolution to ${userVncSettings.resolution}. Options available:`, 
                        Array.from(resolutionSelect.options).map(o => o.value));
                }
                if (userVncSettings.window_manager && windowManagerSelect.value !== userVncSettings.window_manager) {
                    console.warn(`Failed to set window manager to ${userVncSettings.window_manager}. Options available:`, 
                        Array.from(windowManagerSelect.options).map(o => o.value));
                }
            }, 200); // Increased timeout from 50ms to 200ms
        } else {
            // Fall back to server defaults
            console.log('Setting dropdown values from server defaults');
            
            // Also use the increased setTimeout for consistency
            setTimeout(() => {
                setDropdownValue(siteSelect, vncConfig.defaults.site);
                setDropdownValue(resolutionSelect, vncConfig.defaults.resolution);
                setDropdownValue(windowManagerSelect, vncConfig.defaults.window_manager);
                
                // VERIFICATION for defaults as well
                console.log('VERIFICATION - Default dropdown values after setting:');
                console.log(`Site: ${siteSelect.value}`);
                console.log(`Resolution: ${resolutionSelect.value}`);
                console.log(`Window Manager: ${windowManagerSelect.value}`);
            }, 200); // Increased timeout from 50ms to 200ms
        }
        
        // Set default name placeholder
        const randomId = generateRandomId();
        const nameInput = document.getElementById('vnc-name');
        if (nameInput) {
            nameInput.placeholder = `${vncConfig.defaults.name_prefix}_${randomId}`;
        }
        
        console.log('VNC configuration loading complete');
    } catch (error) {
        console.error('Failed to load VNC configuration:', error);
        showMessage('Could not load VNC configuration. Please try again later.', 'error');
    }
}

// Helper function to clear and populate a dropdown
function clearAndPopulateDropdown(selectElement, options) {
    if (!selectElement) return;
    
    // Clear existing options
    selectElement.innerHTML = '';
    
    // Add new options
    options.forEach(option => {
        const optionElement = document.createElement('option');
        optionElement.value = option;
        optionElement.textContent = option;
        selectElement.appendChild(optionElement);
    });
}

// Helper function to set dropdown value and ensure it's visible
function setDropdownValue(selectElement, value) {
    if (!selectElement || !value) return;
    
    console.log(`Setting ${selectElement.id} to value: ${value}`);
    
    // Try setting the value directly first
    selectElement.value = value;
    
    // If that didn't work, try to find the option by value
    if (selectElement.value !== value) {
        console.warn(`Direct value setting failed. Current value: ${selectElement.value}, Wanted: ${value}`);
        
        // Check if option exists
        let optionFound = false;
        for (let i = 0; i < selectElement.options.length; i++) {
            const option = selectElement.options[i];
            // Try matching by exact value, lowercase value, or trimmed value
            if (option.value === value || 
                option.value.toLowerCase() === value.toLowerCase() ||
                option.value.trim() === value.trim()) {
                // Select this option by setting selectedIndex
                selectElement.selectedIndex = i;
                optionFound = true;
                console.log(`Set selectedIndex to ${i}`);
                break;
            }
        }
        
        // If option doesn't exist, add it
        if (!optionFound) {
            console.log(`Option ${value} doesn't exist in dropdown, adding it`);
            const option = document.createElement('option');
            option.value = value;
            option.textContent = `${value} (Custom)`;
            selectElement.appendChild(option);
            
            // Try setting the value again (should work now)
            selectElement.value = value;
            
            // Verify that it worked
            if (selectElement.value !== value) {
                console.error(`Failed to set value even after adding it as an option. Current value: ${selectElement.value}`);
            }
        }
    }
    
    // Final verification
    console.log(`Final selected value for ${selectElement.id}: ${selectElement.value}`);
    
    // Fire a change event to make sure any listeners are notified
    const event = new Event('change');
    selectElement.dispatchEvent(event);
}

// Tab functionality
function changeTab(tabId) {
    // Hide all tab contents
    tabContents.forEach(content => {
        content.style.display = 'none';
    });

    // Remove active class from all tabs
    tabs.forEach(tab => {
        tab.classList.remove('active');
    });

    // Show selected tab content
    document.getElementById(tabId).style.display = 'block';

    // Add active class to the selected tab
    const selectedTab = document.querySelector(`.tab-button[data-tab="${tabId}"]`);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    // Trigger appropriate refresh when switching tabs
    if (tabId === 'manager-mode') {
        refreshManagerList();
    } else if (tabId === 'vnc-manager') {
        refreshVNCList();
    } else if (tabId === 'debug-panel') {
        loadDebugInfo();
    }
}

// Helper function to print out the current form settings
function printFormSettings() {
    const siteSelect = document.getElementById('vnc-site');
    const resolutionSelect = document.getElementById('vnc-resolution');
    const windowManagerSelect = document.getElementById('vnc-window-manager');
    
    console.log('==== CURRENT FORM SETTINGS ====');
    console.log(`Site: ${siteSelect ? siteSelect.value : 'Not found'}`);
    console.log(`Resolution: ${resolutionSelect ? resolutionSelect.value : 'Not found'}`);
    console.log(`Window Manager: ${windowManagerSelect ? windowManagerSelect.value : 'Not found'}`);
    
    // Also check if these values are present in the dropdown options
    if (siteSelect) {
        const siteExists = Array.from(siteSelect.options).some(opt => opt.value === siteSelect.value);
        console.log(`Site value exists in options: ${siteExists}`);
    }
    
    if (resolutionSelect) {
        const resolutionExists = Array.from(resolutionSelect.options).some(opt => opt.value === resolutionSelect.value);
        console.log(`Resolution value exists in options: ${resolutionExists}`);
    }
    
    if (windowManagerSelect) {
        const wmExists = Array.from(windowManagerSelect.options).some(opt => opt.value === windowManagerSelect.value);
        console.log(`Window Manager value exists in options: ${wmExists}`);
    }
    console.log('==============================');
}

// API Requests
async function apiRequest(endpoint, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };
    
    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }
    
    try {
        console.log(`Making API request to: /api/${endpoint}`);
        const response = await fetch(`/api/${endpoint}`, options);
        
        // For debugging, log the status code
        console.log(`API response status for ${endpoint}: ${response.status}`);
        
        // For user settings, handle 404 gracefully
        if (endpoint === 'user/settings' && !response.ok) {
            console.warn(`User settings request failed with status: ${response.status}`);
            return { success: false, settings: {} };
        }
        
        // Try to get response as text first
        const responseText = await response.text();
        console.log(`Raw API response for ${endpoint}:`, responseText);
        
        // Try to parse as JSON
        let result;
        try {
            result = responseText ? JSON.parse(responseText) : {};
            console.log(`Parsed API response for ${endpoint}:`, result);
        } catch (parseError) {
            console.error('Error parsing response as JSON:', parseError);
            console.log('Response text:', responseText);
            throw new Error('Invalid JSON response from server');
        }
        
        if (!response.ok) {
            if (result && result.error) {
                throw new Error(result.error);
            } else {
                throw new Error(`Server returned status ${response.status}`);
            }
        }
        
        return result;
    } catch (error) {
        console.error(`API Error for ${endpoint}:`, error);
        // Don't show API errors for list requests or user settings, as they might be expected
        if (!endpoint.includes('vnc/list') && !endpoint.includes('vnc/list_all') && !endpoint.includes('user/settings')) {
            showMessage(error.message || 'API request failed. Please try again later.', 'error');
        }
        throw error;
    }
}

// Load LSF Configuration
async function loadLSFConfig() {
    try {
        lsfConfig = await apiRequest('config/lsf');
        console.log("LSF config received:", lsfConfig);
        
        // Populate select fields
        populateSelect('lsf-queue', lsfConfig.queues, lsfConfig.defaults.queue);
        populateSelect('lsf-cores', lsfConfig.core_options, lsfConfig.defaults.num_cores);
        
        // Populate OS options if available
        if (lsfConfig.os_options && Array.isArray(lsfConfig.os_options)) {
            const osElement = document.getElementById('lsf-os');
            if (osElement) {
                // Clear existing options
                osElement.innerHTML = '';
                
                // Get default OS from config
                const defaultOs = lsfConfig.defaults.os || "Any";
                let foundDefault = false;
                
                // Add each OS option
                lsfConfig.os_options.forEach(os => {
                    const optionElement = document.createElement('option');
                    optionElement.value = os.name;
                    optionElement.textContent = os.name;
                    
                    if (os.name === defaultOs) {
                        optionElement.selected = true;
                        foundDefault = true;
                    }
                    
                    osElement.appendChild(optionElement);
                });
                
                // If default not found, add it
                if (!foundDefault && defaultOs) {
                    const optionElement = document.createElement('option');
                    optionElement.value = defaultOs;
                    optionElement.textContent = defaultOs + ' (Default)';
                    optionElement.selected = true;
                    osElement.appendChild(optionElement);
                }
            }
        }
        
        // Set memory slider based on memory options from config
        const memorySlider = document.getElementById('lsf-memory');
        const memoryValue = document.getElementById('memory-value');
        
        // Get memory options from config (could be memory_options or memory_options_gb)
        const memoryOptionsData = lsfConfig.memory_options_gb || lsfConfig.memory_options;
        
        if (memorySlider && memoryValue && memoryOptionsData) {
            // Sort memory options to ensure they're in ascending order
            const memoryOptions = [...memoryOptionsData].sort((a, b) => a - b);
            
            // Only update if we have memory options
            if (memoryOptions.length > 0) {
                // Update slider attributes
                memorySlider.min = memoryOptions[0];
                memorySlider.max = memoryOptions[memoryOptions.length - 1];
                
                // Get default memory in GB from config
                const defaultMemoryGB = lsfConfig.defaults.memory_gb;
                console.log("Default memory from config:", defaultMemoryGB);
                
                // Get slider labels for min and max display
                const sliderLabels = document.querySelector('.slider-labels');
                if (sliderLabels) {
                    const labelSpans = sliderLabels.querySelectorAll('span');
                    if (labelSpans.length >= 2) {
                        labelSpans[0].textContent = `${memoryOptions[0]}GB`;
                        labelSpans[1].textContent = `${memoryOptions[memoryOptions.length - 1]}GB`;
                    }
                }
                
                // Find the closest memory option to default
                let closestOption = memoryOptions[0];
                let minDiff = Math.abs(defaultMemoryGB - memoryOptions[0]);
                
                for (let i = 1; i < memoryOptions.length; i++) {
                    const diff = Math.abs(defaultMemoryGB - memoryOptions[i]);
                    if (diff < minDiff) {
                        minDiff = diff;
                        closestOption = memoryOptions[i];
                    }
                }
                
                // Set the slider to the closest option
                memorySlider.value = closestOption;
                memoryValue.textContent = closestOption;
                
                // Ensure the step attribute is properly set
                const step = memoryOptions.length > 1 ? memoryOptions[1] - memoryOptions[0] : 1;
                memorySlider.step = step;
                
                console.log("Memory slider initialization:", {
                    min: memorySlider.min,
                    max: memorySlider.max,
                    value: memorySlider.value,
                    step: memorySlider.step,
                    defaultMemoryGB,
                    closestOption,
                    memoryOptions
                });
                
                // Store memory options as a data attribute for later use
                memorySlider.dataset.memoryOptions = JSON.stringify(memoryOptions);
                
                // Clear existing event listeners (to avoid duplicates)
                memorySlider.removeEventListener('input', handleMemorySliderInput);
                memorySlider.removeEventListener('change', handleMemorySliderChange);
                
                // Add input event listener to snap to valid options during sliding
                memorySlider.addEventListener('input', handleMemorySliderInput);
                
                // Add change event to snap to valid value when done sliding
                memorySlider.addEventListener('change', handleMemorySliderChange);
            }
        }
    } catch (error) {
        console.error('Failed to load LSF configuration:', error);
    }
}

// Handler for memory slider input events
function handleMemorySliderInput() {
    try {
        const options = JSON.parse(this.dataset.memoryOptions);
        const currentValue = parseInt(this.value);
        const memoryValue = document.getElementById('memory-value');
        
        // Find the closest memory option
        let closestOption = findClosestMemoryOption(options, currentValue);
        
        // Update display value with the closest option
        if (memoryValue) {
            memoryValue.textContent = closestOption;
        }
    } catch (e) {
        console.error('Error handling memory slider input:', e);
    }
}

// Handler for memory slider change events
function handleMemorySliderChange() {
    try {
        const options = JSON.parse(this.dataset.memoryOptions);
        const currentValue = parseInt(this.value);
        const memoryValue = document.getElementById('memory-value');
        
        // Find the closest memory option
        let closestOption = findClosestMemoryOption(options, currentValue);
        
        // Update the actual slider value to snap to the valid option
        this.value = closestOption;
        if (memoryValue) {
            memoryValue.textContent = closestOption;
        }
    } catch (e) {
        console.error('Error handling memory slider change:', e);
    }
}

// Helper function to find closest memory option
function findClosestMemoryOption(options, currentValue) {
    if (!options || !options.length) return currentValue;
    
    let closestOption = options[0];
    let minDiff = Math.abs(currentValue - options[0]);
    
    for (let i = 1; i < options.length; i++) {
        const diff = Math.abs(currentValue - options[i]);
        if (diff < minDiff) {
            minDiff = diff;
            closestOption = options[i];
        }
    }
    
    return closestOption;
}

// Refresh VNC List
async function refreshVNCList(withRetries = false) {
    // Track if this function was directly called (not via click handler)
    const directCall = !refreshButton.classList.contains('refreshing');
    let originalText = null;
    
    // Only modify the button if this is a direct call
    if (directCall) {
        originalText = refreshButton.innerHTML;
        refreshButton.classList.add('rotating');
        refreshButton.classList.add('refreshing');
        refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refreshing...';
    }
    
    try {
        // The table already has a loading indicator from HTML
        const jobs = await apiRequest('vnc/list');
        
        // Always clear table (removes loading indicator too)
        vncTableBody.innerHTML = '';
        
        if (jobs.length === 0) {
            noVNCMessage.style.display = 'block';
            document.querySelector('.table-container').style.display = 'none';
            return;
        }
        
        noVNCMessage.style.display = 'none';
        document.querySelector('.table-container').style.display = 'block';
        
        // Populate table
        jobs.forEach(job => {
            const row = document.createElement('tr');
            
            // Status badge class based on status
            let statusClass = 'status-pending';
            if (job.status === 'DONE') statusClass = 'status-done';
            if (job.status === 'RUN') statusClass = 'status-running';
            if (job.status === 'EXIT') statusClass = 'status-error';
            
            // Connection information (display port if available)
            const connectionInfo = job.port ? 
                `${job.host}:${job.port}` : 
                (job.host || 'N/A');
            
            // Create cells
            row.innerHTML = `
                <td>${job.job_id}</td>
                <td>${job.name === "VNC Session" ? "" : job.name}</td>
                <td>${job.user}</td>
                <td>${job.status === "RUN" ? 
                    `<span class="status-badge ${statusClass}">${job.status}</span>` : 
                    `<span class="status-badge ${statusClass}">${job.status}</span>`}
                </td>
                <td>${job.queue}</td>
                <td>${job.resources_unknown ? 'Unknown' : `${job.num_cores || '-'} cores, ${job.memory_gb || '-'} GB`}</td>
                <td title="VNC Connection: ${connectionInfo}">${job.host || 'N/A'}</td>
                <td>:${job.display || 'N/A'}</td>
                <td>${job.runtime_display || 'N/A'}</td>
                <td class="actions-cell">
                    <button class="button secondary connect-button" data-job-id="${job.job_id}" title="Connect to VNC (${connectionInfo})">
                        <i class="fas fa-plug"></i> Connect
                    </button>
                    <button class="button danger kill-button" data-job-id="${job.job_id}" title="Kill VNC Session">
                        <i class="fas fa-times"></i> Kill
                    </button>
                </td>
            `;
            
            // Add to table
            vncTableBody.appendChild(row);
        });
        
        // Ensure sorting functionality attached (re-attaching safe)
        enableTableSorting('vnc-table');
        
        // Add event listeners to buttons
        document.querySelectorAll('.kill-button').forEach(button => {
            button.addEventListener('click', () => {
                const jobId = button.getAttribute('data-job-id');
                killVNCSession(jobId);
            });
        });
        
        document.querySelectorAll('.connect-button').forEach(button => {
            button.addEventListener('click', () => {
                const jobId = button.getAttribute('data-job-id');
                // Find job info
                const job = jobs.find(j => j.job_id === jobId);
                if (job) {
                    connectToVNC(job);
                }
            });
        });
    } catch (error) {
        console.error('Failed to refresh VNC list:', error);
        // Show no VNC message and hide table on error
        noVNCMessage.style.display = 'block';
        document.querySelector('.table-container').style.display = 'none';
        
        // Update the message to indicate that we can't access the LSF system
        const messageElement = document.querySelector('.empty-state p');
        if (messageElement) {
            messageElement.textContent = 'Unable to access VNC sessions. LSF system may be unavailable.';
        }
    } finally {
        // Only reset the button if we set it in this function
        if (directCall) {
            setTimeout(() => {
                refreshButton.classList.remove('rotating');
                refreshButton.classList.remove('refreshing');
                refreshButton.innerHTML = originalText || '<i class="fas fa-sync-alt"></i> Refresh';
            }, 500);
        }
    }
}

// Function to copy text to clipboard
function copyToClipboard(text) {
    // Create a temporary input element
    const tempInput = document.createElement('input');
    tempInput.value = text;
    document.body.appendChild(tempInput);
    
    // Select and copy the text
    tempInput.select();
    document.execCommand('copy');
    
    // Remove the temporary element
    document.body.removeChild(tempInput);
    
    // Show feedback
    showMessage(`Copied to clipboard: ${text}`, 'success');
}

// Connect to VNC
function connectToVNC(job) {
    // Check if we have both host and display information
    if (!job.host || !job.display) {
        showMessage(`Connection details unavailable for ${job.name || 'VNC session'}. Host or display number missing.`, 'error');
        return;
    }
    
    // Calculate the VNC port (5900 + display number)
    const vncPort = 5900 + parseInt(job.display);
    
    // Format the connection string using port instead of display
    const connectionString = `${job.host}:${vncPort}`;
    
    // Launch VNC viewer using the vnc:// protocol with port
    console.log(`Connecting to VNC using vnc://${connectionString}`);
    window.location.href = `vnc://${connectionString}`;
}

// Show detailed VNC connection instructions with application-specific info
function showDetailedInstructions(job) {
    const hostname = job.host;
    const displayNum = job.display;
    const connectionString = `${hostname}:${displayNum}`;
    const rfbPort = 5900 + parseInt(displayNum);
    
    const messageContent = `
        <div class="connection-info">
            <h3>VNC Connection Details</h3>
            <div class="connection-detail-item">
                <span class="detail-label">Host:</span>
                <span class="detail-value">${hostname}</span>
                <button class="button mini copy-button" onclick="copyToClipboard('${hostname}')">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
            <div class="connection-detail-item">
                <span class="detail-label">Port:</span>
                <span class="detail-value">${rfbPort}</span>
                <button class="button mini copy-button" onclick="copyToClipboard('${rfbPort}')">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
            <div class="connection-detail-item">
                <span class="detail-label">Display:</span>
                <span class="detail-value">:${displayNum}</span>
            </div>
            
            <div class="connection-methods">
                <h4>Connect using VNC Viewer</h4>
                
                <div class="connection-method">
                    <h5>For RealVNC Viewer:</h5>
                    <ol>
                        <li>Open RealVNC Viewer</li>
                        <li>Enter <code>${hostname}:${rfbPort}</code> in the address bar</li>
                        <li>Click Connect</li>
                    </ol>
                    <div class="connection-actions">
                        <button class="button primary" onclick="window.location.href='realvnc://${hostname}:${rfbPort}'">
                            <i class="fas fa-external-link-alt"></i> Launch RealVNC
                        </button>
                        <button class="button secondary copy-button" onclick="copyToClipboard('${hostname}:${rfbPort}')">
                            <i class="fas fa-copy"></i> Copy address
                        </button>
                    </div>
                </div>
                
                <div class="connection-method">
                    <h5>For TigerVNC Viewer:</h5>
                    <div class="command-box">
                        <code>vncviewer ${connectionString}</code>
                        <button class="button mini copy-button" onclick="copyToClipboard('vncviewer ${connectionString}')">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </div>
                
                <div class="connection-method">
                    <h5>For any VNC Viewer:</h5>
                    <p>Host: <code>${hostname}</code></p>
                    <p>Port: <code>${rfbPort}</code></p>
                </div>
                
                <div class="connection-method">
                    <h5>To use macOS Screen Sharing:</h5>
                    <button class="button secondary" onclick="window.location.href='vnc://${hostname}:${rfbPort}'">
                        <i class="fas fa-desktop"></i> Open in Screen Sharing
                    </button>
                </div>
            </div>
        </div>
    `;
    
    showMessage(messageContent, 'info');
}

// Create VNC Session
async function createVNCSession(event) {
    event.preventDefault();
    
    // Show loading on button
    const submitButton = createVNCForm.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    submitButton.disabled = true;
    
    try {
        // Get form elements directly
        const siteSelect = document.getElementById('vnc-site');
        const resolutionSelect = document.getElementById('vnc-resolution');
        const windowManagerSelect = document.getElementById('vnc-window-manager');
        const nameInput = document.getElementById('vnc-name');
        const coresSelect = document.getElementById('lsf-cores');
        const queueSelect = document.getElementById('lsf-queue');
        const memorySlider = document.getElementById('lsf-memory');
        const osSelect = document.getElementById('lsf-os');
        const hostFilterInput = document.getElementById('lsf-host-filter');
        
        // Log all form element values for debugging
        console.log('Form values at submission:');
        console.log('Site:', siteSelect ? siteSelect.value : 'Not found');
        console.log('Resolution:', resolutionSelect ? resolutionSelect.value : 'Not found');
        console.log('Window Manager:', windowManagerSelect ? windowManagerSelect.value : 'Not found');
        console.log('Name:', nameInput ? nameInput.value : 'Not found');
        console.log('Cores:', coresSelect ? coresSelect.value : 'Not found');
        console.log('Queue:', queueSelect ? queueSelect.value : 'Not found');
        console.log('Memory:', memorySlider ? memorySlider.value : 'Not found');
        console.log('OS:', osSelect ? osSelect.value : 'Not found');
        console.log('Host Filter:', hostFilterInput ? hostFilterInput.value : 'Not found');
        
        // Build the data object manually from form elements
        const data = {};
        
        // Add site if available and valid
        if (siteSelect && siteSelect.value) {
            data.site = siteSelect.value;
        }
        
        // Add resolution if available and valid
        if (resolutionSelect && resolutionSelect.value) {
            data.resolution = resolutionSelect.value;
        }
        
        // Add window manager if available and valid
        if (windowManagerSelect && windowManagerSelect.value) {
            data.window_manager = windowManagerSelect.value;
        }
        
        // Add name if provided (not empty)
        if (nameInput && nameInput.value && nameInput.value.trim() !== '') {
            data.name = nameInput.value.trim();
        }
        
        // Add cores if available
        if (coresSelect && coresSelect.value) {
            data.num_cores = coresSelect.value;
        }
        
        // Add queue if available
        if (queueSelect && queueSelect.value) {
            data.queue = queueSelect.value;
        }
        
        // Add OS if available
        if (osSelect && osSelect.value) {
            data.os = osSelect.value;
        }
        
        // Add host filter if available and not empty
        if (hostFilterInput && hostFilterInput.value && hostFilterInput.value.trim() !== '') {
            data.host_filter = hostFilterInput.value.trim();
        }
        
        // Add memory if available
        if (memorySlider && memorySlider.value) {
            // Get the current value
            const currentValue = parseInt(memorySlider.value);
            
            // If we have memory options stored, ensure we use a valid option
            if (memorySlider.dataset.memoryOptions) {
                try {
                    const options = JSON.parse(memorySlider.dataset.memoryOptions);
                    
                    // Find the closest memory option
                    let closestOption = findClosestMemoryOption(options, currentValue);
                    data.memory_gb = closestOption.toString();
                } catch (e) {
                    console.warn('Error finding closest memory option:', e);
                    data.memory_gb = currentValue.toString();
                }
            } else {
                // Fallback if no memory options are available
                data.memory_gb = currentValue.toString();
            }
        }
        
        console.log('Submitting VNC session with data:', data);
        
        // Request headers and body
        const options = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        };
        
        // Send the request directly
        console.log('Sending request to /api/vnc/create');
        const response = await fetch('/api/vnc/create', options);
        
        // Check response status
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Server returned error:', errorText);
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
        
        // Parse response
        const result = await response.json();
        console.log('Creation response:', result);
        
        // Show success message
        showMessage(`VNC session created successfully. Job ID: ${result.job_id}`, 'success');
        
        // Reset form
        createVNCForm.reset();
        
        // Switch to manager tab and refresh
        changeTab('vnc-manager');
        refreshVNCList();
    } catch (error) {
        console.error('Failed to create VNC session:', error);
        showMessage(`Failed to create VNC session: ${error.message || 'Unknown error'}`, 'error');
    } finally {
        // Restore button state
        submitButton.innerHTML = originalText;
        submitButton.disabled = false;
    }
}

// Kill VNC Session
async function killVNCSession(jobId) {
    // Create a modal confirmation dialog
    const confirmDialog = document.createElement('div');
    confirmDialog.className = 'confirm-dialog';
    confirmDialog.innerHTML = `
        <div class="confirm-dialog-content">
            <h3>Confirm Action</h3>
            <p>Are you sure you want to kill VNC session ${jobId}?</p>
            <div class="confirm-actions">
                <button class="button primary cancel-button">Cancel</button>
                <button class="button danger confirm-button">Yes, Kill Session</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(confirmDialog);
    
    // Add event listeners
    const cancelButton = confirmDialog.querySelector('.cancel-button');
    const confirmButton = confirmDialog.querySelector('.confirm-button');
    
    cancelButton.addEventListener('click', () => {
        document.body.removeChild(confirmDialog);
    });
    
    confirmButton.addEventListener('click', async () => {
        // Show loading state
        confirmButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Killing...';
        confirmButton.disabled = true;
        
        try {
            await apiRequest(`vnc/kill/${jobId}`, 'POST');
            showMessage(`VNC session ${jobId} killed successfully.`, 'success');
            
            // Reset refresh button if it was in refreshing state
            if (refreshButton.classList.contains('refreshing')) {
                refreshButton.classList.remove('refreshing');
                refreshButton.classList.remove('rotating');
                refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            }
            
            // Use a 5-second delay before refreshing to allow server to fully process the kill
            showMessage(`VNC session ${jobId} killed. Refreshing list in 5 seconds...`, 'info');
            setTimeout(() => refreshVNCList(), 5000);
            
        } catch (error) {
            console.error('Failed to kill VNC session:', error);
        } finally {
            document.body.removeChild(confirmDialog);
        }
    });
}

// Populate Select Options
function populateSelect(elementId, options, defaultValue) {
    const select = document.getElementById(elementId);
    if (!select) {
        console.error(`Element with ID "${elementId}" not found`);
        return;
    }
    
    console.log(`Populating select ${elementId} with options:`, options, `default:`, defaultValue);
    
    // Clear existing options
    select.innerHTML = '';
    
    // Track if we found a match for the default value
    let foundDefault = false;
    
    // Add each option
    options.forEach(option => {
        const optionElement = document.createElement('option');
        
        // Check if the option is an object with value/label properties
        if (option && typeof option === 'object' && option.value !== undefined) {
            optionElement.value = option.value;
            optionElement.textContent = option.label || option.value;
            
            if (option.value === defaultValue) {
                optionElement.selected = true;
                foundDefault = true;
                console.log(`Found matching option for default value "${defaultValue}" in ${elementId}`);
            }
        } else {
            // Simple string option
            optionElement.value = option;
            optionElement.textContent = option;
            
            if (option === defaultValue) {
                optionElement.selected = true;
                foundDefault = true;
                console.log(`Found matching option for default value "${defaultValue}" in ${elementId}`);
            }
        }
        
        select.appendChild(optionElement);
    });
    
    // If no match found for the default value, log a warning
    if (!foundDefault && defaultValue) {
        console.warn(`Default value "${defaultValue}" not found in options for ${elementId}`);
        
        // Add the default value as an option if it's not in the list
        const optionElement = document.createElement('option');
        optionElement.value = defaultValue;
        optionElement.textContent = defaultValue + ' (Custom)';
        optionElement.selected = true;
        select.appendChild(optionElement);
        console.log(`Added custom option for default value "${defaultValue}" to ${elementId}`);
    }
    
    // Log the final selected value
    console.log(`${elementId} final selected value:`, select.value);
}

// Show Message
function showMessage(message, type = 'info') {
    // Set HTML content if it contains HTML tags, otherwise set as text
    if (message.includes('<') && message.includes('>')) {
        messageText.innerHTML = message;
    } else {
        messageText.textContent = message;
    }
    
    messageBox.className = `message-box ${type}`;
    messageBox.classList.remove('hidden');
    
    // Auto-hide after 8 seconds for longer messages
    setTimeout(hideMessage, 8000);
}

// Hide Message
function hideMessage() {
    messageBox.classList.add('hidden');
}

// Generate Random ID for VNC session names
function generateRandomId() {
    return Math.random().toString(36).substring(2, 8);
}

// Add the CSS styles for the confirmation dialog and status badges to the page
document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = `
        .confirm-dialog {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            animation: fadeIn 0.2s ease;
        }
        
        .confirm-dialog-content {
            background-color: white;
            border-radius: var(--border-radius);
            padding: 1.5rem;
            width: 90%;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        .confirm-dialog-content h3 {
            margin-top: 0;
            color: var(--primary-color);
            border: none;
        }
        
        .confirm-actions {
            display: flex;
            justify-content: flex-end;
            gap: 1rem;
            margin-top: 1.5rem;
        }
        
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 2rem;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .status-running {
            background-color: var(--success-color);
            color: white;
        }
        
        .status-pending {
            background-color: var(--warning-color);
            color: #333;
        }
        
        .status-error {
            background-color: var(--danger-color);
            color: white;
        }
        
        .actions-cell {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .rotating {
            animation: rotate 0.8s linear infinite;
        }
        
        @keyframes rotate {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        .fade-in {
            animation: fadeIn 0.3s ease;
        }
        
        /* Debug panel styling */
        .debug-info-list {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
        }
        
        .debug-info-item {
            padding: 0.5rem;
            background-color: rgba(0, 0, 0, 0.03);
            border-radius: 4px;
            line-height: 1.5;
        }
        
        .debug-info-item:hover {
            background-color: rgba(0, 0, 0, 0.05);
        }
        
        .debug-info-item strong {
            color: #6a3de8; /* Purple color that fits the theme */
            margin-right: 0.5rem;
            font-weight: 600;
        }
        
        .debug-section h3 {
            margin-top: 1.5rem;
            margin-bottom: 1rem;
            color: #333;
            border-bottom: 1px solid #eee;
            padding-bottom: 0.5rem;
        }
        
        /* Collapsible section styles */
        .collapsible-section {
            margin-bottom: 1rem;
            border: 1px solid #eee;
            border-radius: 6px;
            overflow: hidden;
        }
        
        .section-header {
            padding: 1rem;
            margin: 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            background-color: #f9f9f9;
            transition: background-color 0.2s ease;
            border-bottom: none;
        }
        
        .section-header:hover {
            background-color: #f0f0f0;
        }
        
        .section-title {
            font-weight: 600;
            color: #333;
        }
        
        .collapse-indicator {
            color: #6a3de8;
            font-size: 0.9rem;
            transition: transform 0.3s ease;
        }
        
        .collapsed .collapse-indicator i.fa-chevron-up {
            transform: rotate(180deg);
        }
        
        .section-content {
            overflow: hidden;
            max-height: 1000px; /* Default max height */
            transition: max-height 0.3s ease-out;
            padding: 0 1rem;
        }
        
        .collapsed .section-content {
            max-height: 0;
            padding-top: 0;
            padding-bottom: 0;
        }
        
        /* Additional styling for the debug panel */
        #debug-panel .form-card {
            padding-top: 0.5rem;
        }
        
        #debug-panel .form-title {
            margin-bottom: 1.5rem;
        }
    `;
    
    document.head.appendChild(style);
});

/**
 * Load Debug Info
 */
function loadDebugInfo() {
    console.log('Loading debug information...');
    
    // Fetch server status first (and hide debug tab if needed)
    checkDebugMode().then(() => {
        // Only proceed with fetching debug info if the tab is still visible
        const debugTab = document.getElementById('debug-tab');
        if (debugTab && debugTab.style.display !== 'none') {
            console.log('Debug tab is visible, fetching debug information...');
            
            // First, fetch application info
            fetchAppInfo();
            
            // Then update debug sections
            refreshAndUpdateDebugSection('system-info', '/api/debug/system_info');
            refreshAndUpdateDebugSection('session-info', '/api/debug/session_info');
            refreshAndUpdateDebugSection('auth-info', '/api/debug/auth_info');
            refreshAndUpdateDebugSection('log-info', '/api/debug/log');
        } else {
            console.log('Debug tab is hidden, skipping debug info fetch');
        }
    });
}

/**
 * Fetch session information from server
 */
function fetchSessionInfo() {
    console.log('Fetching session data using direct fetch...');
    
    // Use a simple fetch call for maximum compatibility
    fetch('/api/debug/session')
        .then(response => {
            console.log('Session response status:', response.status);
            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Session data successfully received:', data);
            displaySessionInfo(data);
        })
        .catch(error => {
            console.error('Failed to load session information:', error);
            document.getElementById('debug-session').innerHTML = `
                <div class="error-message">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>Failed to load session information: ${error.message}</p>
                </div>
            `;
        });
}

/**
 * Fetch environment information from server
 */
function fetchEnvironmentInfo() {
    console.log('Fetching environment data...');
    
    fetch('/api/debug/environment')
        .then(response => {
            console.log('Environment response status:', response.status);
            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }
            return response.text();  // Get as text first to inspect the raw response
        })
        .then(responseText => {
            console.log('Raw environment response:', responseText);
            
            try {
                const data = JSON.parse(responseText);
                console.log('Parsed environment data:', data);
                console.log('Server version:', data.server_version);
                console.log('Python version:', data.python_version);
                console.log('Server time:', data.server_time);
                console.log('Hostname:', data.hostname);
                console.log('Server info object:', data.server_info);
                
                displayEnvironmentInfo(data);
            } catch (error) {
                console.error('Error parsing environment data:', error);
                throw error;
            }
        })
        .catch(error => {
            console.error('Failed to load environment information:', error);
            document.getElementById('debug-environment').innerHTML = `
                <div class="error-message">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>Failed to load environment information: ${error.message}</p>
                </div>
            `;
        });
}

/**
 * Adjust the height of a collapsible section if it's expanded
 */
function adjustCollapsibleSectionHeight(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const section = container.closest('.collapsible-section');
    if (!section) return;
    
    const content = section.querySelector('.section-content');
    if (!content || section.classList.contains('collapsed')) return;
    
    // Re-calculate and set the section content height
    content.style.maxHeight = content.scrollHeight + 'px';
}

/**
 * Display session information in the debug panel
 */
function displaySessionInfo(data) {
    console.log('Displaying session information...');
    
    const sessionContainer = document.getElementById('debug-session');
    
    let html = '<div class="debug-section">';
    
    // Display session information
    html += `
        <h3>Session Information</h3>
        <div class="debug-info-list">
            <div class="debug-info-item"><strong>Session ID:</strong> ${data.session_id || 'N/A'}</div>
            <div class="debug-info-item"><strong>User:</strong> ${data.username || 'Anonymous'}</div>
            <div class="debug-info-item"><strong>Display Name:</strong> ${data.display_name || data.username || 'N/A'}</div>
            <div class="debug-info-item"><strong>Email:</strong> ${data.email || 'N/A'}</div>
            <div class="debug-info-item"><strong>Authentication:</strong> ${data.authenticated ? 'Authenticated' : 'Not Authenticated'}</div>
            <div class="debug-info-item"><strong>Auth Method:</strong> ${data.auth_method || 'None'}</div>
            <div class="debug-info-item"><strong>Login Time:</strong> ${data.login_time || 'N/A'}</div>
            <div class="debug-info-item"><strong>Session Expiry:</strong> <span class="session-expiry ${getExpiryClass(data.expiry_days)}">${data.expiry_info || 'Not Available'}</span></div>
            <div class="debug-info-item"><strong>IP Address:</strong> ${data.ip_address || 'Unknown'}</div>
            <div class="debug-info-item"><strong>User Agent:</strong> ${data.user_agent || 'Unknown'}</div>
        </div>
    `;
    
    // Display user groups if available
    if (data.groups && Array.isArray(data.groups) && data.groups.length > 0) {
        html += `
            <h3>User Groups</h3>
            <div class="groups-list">
                ${data.groups.map(group => `<span class="group-tag">${group}</span>`).join('')}
            </div>
        `;
    }
    
    // Display user permissions if available
    if (data.permissions && Array.isArray(data.permissions) && data.permissions.length > 0) {
        html += `
            <h3>User Permissions</h3>
            <ul class="debug-permissions-list">
                ${data.permissions.map(perm => `<li>${perm}</li>`).join('')}
            </ul>
        `;
    }
    
    html += '</div>';
    
    sessionContainer.innerHTML = html;
    
    // Adjust the collapsible section height
    adjustCollapsibleSectionHeight('debug-session');
}

/**
 * Get CSS class for expiry time display
 */
function getExpiryClass(expiryDays) {
    if (!expiryDays || expiryDays <= 0) return '';
    if (expiryDays < 1) return 'expiry-soon';
    if (expiryDays < 3) return 'expiry-warning';
    if (expiryDays < 7) return 'expiry-normal';
    return 'expiry-long';
}

/**
 * Display environment information in the debug panel
 */
function displayEnvironmentInfo(data) {
    console.log('Displaying environment information...');
    console.log('Server info data received:', data);
    
    const envContainer = document.getElementById('debug-environment');
    
    let html = '<div class="debug-section">';
    
    // Server Information
    html += `
        <h3>Server Information</h3>
        <div class="debug-info-list">
            <div class="debug-info-item"><strong>Server Version:</strong> ${data.server_version || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Python Version:</strong> ${data.python_version || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Server Time:</strong> ${data.server_time || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Hostname:</strong> ${data.hostname || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Platform:</strong> ${data.platform || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Operating System:</strong> ${data.system || 'Unknown'}</div>
        </div>
    `;
    
    // Environment Variables (top 10 most relevant)
    if (data.environment) {
        html += `
            <h3>Environment Variables</h3>
            <div class="debug-info-list">`;
            
        // Important environment variables to show first
        const importantVars = ['USER', 'HOME', 'PATH', 'LSF_LIBDIR', 'LSF_ENVDIR', 'LSF_SERVERDIR', 
                             'DISPLAY', 'SHELL', 'HOSTNAME', 'LANG', 'PWD'];
        
        // Show important variables first
        importantVars.forEach(key => {
            if (data.environment[key]) {
                html += `
                    <div class="debug-info-item"><strong>${key}:</strong> ${data.environment[key]}</div>
                `;
            }
        });
        
        html += `</div>`;
    }
    
    html += '</div>';
    
    envContainer.innerHTML = html;
    
    // Adjust the collapsible section height
    adjustCollapsibleSectionHeight('debug-environment');
}

/**
 * Fetch application information from server
 */
function fetchAppInfo() {
    console.log('Fetching application information...');
    
    // First check if debug tab should be visible
    checkDebugMode().then(() => {
        // Only fetch app info if debug tab is visible
        const debugTab = document.getElementById('debug-tab');
        if (debugTab && debugTab.style.display !== 'none') {
            refreshAndUpdateDebugSection('app-info', '/api/debug/app_info');
        }
    });
}

/**
 * Display application information in the debug panel
 */
function displayAppInfo(data) {
    console.log('Displaying application information...');
    
    const appInfoContainer = document.getElementById('debug-app-info');
    if (!appInfoContainer) {
        console.error('Could not find debug-app-info container');
        return;
    }
    
    const appInfo = data.app_info || {};
    
    let html = '<div class="debug-section">';
    
    // App Information
    html += `
        <h3>Application Information</h3>
        <div class="debug-info-list">
            <div class="debug-info-item"><strong>Status:</strong> ${appInfo.status || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Process ID:</strong> ${appInfo.pid || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Uptime:</strong> ${appInfo.uptime || 'Unknown'}</div>
            <div class="debug-info-item"><strong>URL:</strong> <a href="${appInfo.url || '#'}" target="_blank">${appInfo.url || 'Unknown'}</a></div>
            <div class="debug-info-item"><strong>Host:</strong> ${appInfo.host || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Port:</strong> ${appInfo.port || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Debug Mode:</strong> ${appInfo.debug_mode ? 'Enabled' : 'Disabled'}</div>
        </div>
        
        <h3>Authentication</h3>
        <div class="debug-info-list">
            <div class="debug-info-item"><strong>Authentication:</strong> ${appInfo.auth_enabled ? 'Enabled' : 'Disabled'}</div>
            <div class="debug-info-item"><strong>Auth Method:</strong> ${appInfo.auth_method || 'None'}</div>
            <div class="debug-info-item"><strong>Auth Status:</strong> ${appInfo.auth_status || 'Unknown'}</div>
        </div>
        
        <h3>SSL Configuration</h3>
        <div class="debug-info-list">
            <div class="debug-info-item"><strong>SSL:</strong> ${appInfo.ssl_enabled ? 'Enabled' : 'Disabled'}</div>
            ${appInfo.ssl_enabled ? `
                <div class="debug-info-item"><strong>SSL Certificate:</strong> ${appInfo.ssl_cert || 'Not set'}</div>
                <div class="debug-info-item"><strong>SSL Key:</strong> ${appInfo.ssl_key || 'Not set'}</div>
                ${appInfo.ssl_ca_chain ? `<div class="debug-info-item"><strong>SSL CA Chain:</strong> ${appInfo.ssl_ca_chain}</div>` : ''}
            ` : ''}
        </div>
        
        <h3>Server Paths</h3>
        <div class="debug-info-list">
            <div class="debug-info-item"><strong>Log Directory:</strong> ${appInfo.log_directory || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Data Directory:</strong> ${appInfo.data_directory || 'Unknown'}</div>
            <div class="debug-info-item"><strong>Python Executable:</strong> ${appInfo.python_executable || 'Unknown'}</div>
        </div>
    `;
    
    html += '</div>';
    
    appInfoContainer.innerHTML = html;
    
    // Adjust the collapsible section height
    adjustCollapsibleSectionHeight('debug-app-info');
}

/**
 * Initialize collapsible sections in the debug panel
 */
function initializeCollapsibleSections() {
    const collapsibleSections = document.querySelectorAll('.collapsible-section');
    
    collapsibleSections.forEach(section => {
        const header = section.querySelector('.section-header');
        const content = section.querySelector('.section-content');
        
        if (header && content) {
            // Initialize the state based on the collapsed class
            if (section.classList.contains('collapsed')) {
                content.style.maxHeight = '0px';
            } else {
                content.style.maxHeight = content.scrollHeight + 'px';
            }
            
            // Add click event to toggle section
            header.addEventListener('click', () => {
                // Toggle collapsed class
                section.classList.toggle('collapsed');
                
                // Toggle the collapse indicator icon
                const icon = header.querySelector('.collapse-indicator i');
                if (icon) {
                    icon.classList.toggle('fa-chevron-down');
                    icon.classList.toggle('fa-chevron-up');
                }
                
                // Animate the content height
                if (section.classList.contains('collapsed')) {
                    content.style.maxHeight = '0px';
                } else {
                    // If the section is being expanded, ensure all data is loaded
                    content.style.maxHeight = content.scrollHeight + 'px';
                    
                    // Re-calculate the height after a short delay to account for content loading
                    setTimeout(() => {
                        content.style.maxHeight = content.scrollHeight + 'px';
                    }, 50);
                }
            });
        }
    });
    
    // Re-adjust heights when window is resized
    window.addEventListener('resize', () => {
        collapsibleSections.forEach(section => {
            const content = section.querySelector('.section-content');
            if (content && !section.classList.contains('collapsed')) {
                content.style.maxHeight = content.scrollHeight + 'px';
            }
        });
    });
}

/**
 * Refreshes and updates a debug section with data from the specified API endpoint
 */
function refreshAndUpdateDebugSection(sectionId, apiEndpoint) {
    const sectionElement = document.getElementById(sectionId);
    if (!sectionElement) {
        console.error(`Debug section element '${sectionId}' not found`);
        return;
    }
    
    // Show loading indicator
    sectionElement.innerHTML = `<p class="loading-message">Loading data...</p>`;
    
    // Fetch data from API
    fetch(apiEndpoint)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Format JSON with syntax highlighting
            const formattedData = JSON.stringify(data, null, 2);
            sectionElement.innerHTML = `<pre class="debug-json">${formattedData}</pre>`;
        })
        .catch(error => {
            console.error(`Error fetching ${apiEndpoint}:`, error);
            sectionElement.innerHTML = `<p class="error-message">Error loading data: ${error.message}</p>`;
        });
}

// Listen for user authenticated event to determine manager privilege
document.addEventListener('userAuthenticated', async (e) => {
    try {
        const username = e.detail?.username || null;
        await determineManagerPrivilege(username);
    } catch (err) {
        console.error('Error determining manager privilege:', err);
    }
});

// Determine if current user is in managers list and show/hide the Manager Mode tab accordingly
async function determineManagerPrivilege(username) {
    try {
        // Use cached config if we already fetched it
        if (!serverConfig || Object.keys(serverConfig).length === 0) {
            serverConfig = await apiRequest('server/config');
        }

        const managers = serverConfig.managers || [];
        isManagerUser = username && managers.includes(username);

        const managerTab = document.getElementById('manager-mode-tab');
        const managerContent = document.getElementById('manager-mode');

        if (isManagerUser) {
            if (managerTab) managerTab.style.display = 'inline-block';
            if (managerContent) managerContent.style.display = 'none'; // Remain hidden until clicked
        } else {
            if (managerTab) managerTab.style.display = 'none';
            if (managerContent) managerContent.style.display = 'none';
        }
    } catch (error) {
        console.error('Error fetching server config for manager privilege:', error);
    }
}

// Refresh Manager Mode VNC list (shows all users)
async function refreshManagerList() {
    if (!isManagerUser) {
        return; // Do nothing if not privileged
    }

    // Similar logic to refreshVNCList but using different DOM references and endpoint
    const directCall = !managerRefreshButton || !managerRefreshButton.classList.contains('refreshing');
    let originalText = null;

    if (directCall && managerRefreshButton) {
        originalText = managerRefreshButton.innerHTML;
        managerRefreshButton.classList.add('rotating');
        managerRefreshButton.classList.add('refreshing');
        managerRefreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refreshing...';
    }

    try {
        const jobs = await apiRequest('vnc/list_all');
        // Sort jobs alphabetically by user for default display
        jobs.sort((a, b) => {
            const userA = (a.user || '').toLowerCase();
            const userB = (b.user || '').toLowerCase();
            if (userA < userB) return -1;
            if (userA > userB) return 1;
            return 0;
        });

        managerTableBody.innerHTML = '';

        if (jobs.length === 0) {
            managerNoVNCMessage.style.display = 'block';
            document.querySelector('#manager-mode .table-container').style.display = 'none';
            return;
        }

        managerNoVNCMessage.style.display = 'none';
        document.querySelector('#manager-mode .table-container').style.display = 'block';

        jobs.forEach(job => {
            const row = document.createElement('tr');
            let statusClass = 'status-pending';
            if (job.status === 'DONE') statusClass = 'status-done';
            if (job.status === 'RUN') statusClass = 'status-running';
            if (job.status === 'EXIT') statusClass = 'status-error';

            const connectionInfo = job.port ? `${job.host}:${job.port}` : (job.host || 'N/A');

            row.innerHTML = `
                <td>${job.job_id}</td>
                <td>${job.name === "VNC Session" ? "" : job.name}</td>
                <td>${job.user}</td>
                <td><span class="status-badge ${statusClass}">${job.status}</span></td>
                <td>${job.queue}</td>
                <td>${job.resources_unknown ? 'Unknown' : `${job.num_cores || '-'} cores, ${job.memory_gb || '-'} GB`}</td>
                <td title="VNC Connection: ${connectionInfo}">${job.host || 'N/A'}</td>
                <td>:${job.display || 'N/A'}</td>
                <td>${job.runtime_display || 'N/A'}</td>
                <td class="actions-cell">
                    <button class="button secondary connect-button" data-job-id="${job.job_id}" title="Connect to VNC (${connectionInfo})">
                        <i class="fas fa-plug"></i> Connect
                    </button>
                    <button class="button danger kill-button" data-job-id="${job.job_id}" title="Kill VNC Session">
                        <i class="fas fa-times"></i> Kill
                    </button>
                </td>
            `;

            managerTableBody.appendChild(row);
        });

        // Ensure sorting functionality attached (re-attaching safe)
        enableTableSorting('manager-table');

        // Attach event listeners
        document.querySelectorAll('#manager-mode .kill-button').forEach(button => {
            button.addEventListener('click', () => {
                const jobId = button.getAttribute('data-job-id');
                killVNCSession(jobId);
            });
        });

        document.querySelectorAll('#manager-mode .connect-button').forEach(button => {
            button.addEventListener('click', () => {
                const jobId = button.getAttribute('data-job-id');
                const job = jobs.find(j => j.job_id === jobId);
                if (job) {
                    connectToVNC(job);
                }
            });
        });
    } catch (error) {
        console.error('Failed to refresh Manager Mode VNC list:', error);
        managerNoVNCMessage.style.display = 'block';
        document.querySelector('#manager-mode .table-container').style.display = 'none';
    } finally {
        if (directCall && managerRefreshButton) {
            setTimeout(() => {
                managerRefreshButton.classList.remove('rotating');
                managerRefreshButton.classList.remove('refreshing');
                managerRefreshButton.innerHTML = originalText || '<i class="fas fa-sync-alt"></i> Refresh';
            }, 500);
        }
    }
}

// Enable sortable columns by clicking table headers
function enableTableSorting(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const thElements = table.querySelectorAll('thead th');
    thElements.forEach((th, index) => {
        // Preserve original label
        if (!th.dataset.label) {
            th.dataset.label = th.textContent.trim();
        }

        // Skip if listener already attached
        if (th.dataset.sortableAttached === 'true') return;

        th.dataset.sortableAttached = 'true';
        th.style.cursor = 'pointer';

        th.addEventListener('click', () => {
            const order = th.dataset.order === 'asc' ? 'desc' : 'asc';

            // Reset order for all headers
            thElements.forEach(other => {
                other.dataset.order = '';
                other.innerHTML = other.dataset.label;
            });

            // Set current header order and arrow
            th.dataset.order = order;
            const arrow = order === 'asc' ? ' ▲' : ' ▼';
            th.innerHTML = `${th.dataset.label}${arrow}`;

            // Sort rows
            const tbody = table.tBodies[0];
            const rowsArray = Array.from(tbody.querySelectorAll('tr'));

            rowsArray.sort((rowA, rowB) => {
                const cellA = rowA.children[index].textContent.trim();
                const cellB = rowB.children[index].textContent.trim();

                // Numeric comparison if both are numbers
                const numA = parseFloat(cellA.replace(/[^0-9.-]/g, ''));
                const numB = parseFloat(cellB.replace(/[^0-9.-]/g, ''));
                const bothNumeric = !isNaN(numA) && !isNaN(numB);

                let comparison;
                if (bothNumeric) {
                    comparison = numA - numB;
                } else {
                    comparison = cellA.localeCompare(cellB);
                }

                return order === 'asc' ? comparison : -comparison;
            });

            // Append sorted rows back to tbody
            rowsArray.forEach(row => tbody.appendChild(row));
        });
    });
}