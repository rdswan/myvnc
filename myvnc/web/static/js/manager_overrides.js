// Manager Overrides functionality
console.log('manager_overrides.js loaded successfully');

let currentOverride = null; // Track if we're editing an existing override
let allConfigs = { vnc: null, lsf: null }; // Cache all configuration options
let overridesInitialized = false; // Track if we've already initialized

// Initialize manager overrides when Manager Mode tab is shown
function initManagerOverrides() {
    console.log('Initializing manager overrides, already initialized:', overridesInitialized);
    
    // Only initialize once
    if (overridesInitialized) {
        console.log('Manager overrides already initialized, skipping');
        return;
    }
    
    // Set up event listeners
    const addOverrideButton = document.getElementById('add-override-button');
    const refreshOverridesButton = document.getElementById('refresh-overrides-button');
    
    console.log('Add Override Button:', addOverrideButton);
    console.log('Refresh Overrides Button:', refreshOverridesButton);
    
    if (addOverrideButton) {
        // Remove any existing listeners first
        addOverrideButton.replaceWith(addOverrideButton.cloneNode(true));
        const newAddButton = document.getElementById('add-override-button');
        
        newAddButton.addEventListener('click', (e) => {
            console.log('Add Override button clicked!');
            e.preventDefault();
            openOverrideModal();
        });
        console.log('Add Override button listener attached');
    } else {
        console.error('Add Override button not found!');
    }
    
    if (refreshOverridesButton) {
        // Remove any existing listeners first
        refreshOverridesButton.replaceWith(refreshOverridesButton.cloneNode(true));
        const newRefreshButton = document.getElementById('refresh-overrides-button');
        
        newRefreshButton.addEventListener('click', (e) => {
            console.log('Refresh Overrides button clicked!');
            e.preventDefault();
            loadManagerOverrides();
        });
        console.log('Refresh Overrides button listener attached');
    } else {
        console.error('Refresh Overrides button not found!');
    }
    
    // Load all configurations for the modal
    loadAllConfigurations();
    
    // Load existing overrides only if the User Overrides sub-tab is active
    const userOverridesTab = document.getElementById('user-overrides');
    if (userOverridesTab && userOverridesTab.classList.contains('active')) {
        loadManagerOverrides();
    }
    
    overridesInitialized = true;
    console.log('Manager overrides initialization complete');
}

// Load all available configurations (not just enabled ones)
async function loadAllConfigurations() {
    console.log('loadAllConfigurations called');
    try {
        console.log('Fetching VNC and LSF configs...');
        
        // Load VNC and LSF configs
        const [vncResponse, lsfResponse] = await Promise.all([
            fetch('/api/config/vnc'),
            fetch('/api/config/lsf')
        ]);
        
        console.log('VNC response status:', vncResponse.status);
        console.log('LSF response status:', lsfResponse.status);
        
        if (!vncResponse.ok) {
            throw new Error(`VNC config fetch failed: ${vncResponse.status}`);
        }
        if (!lsfResponse.ok) {
            throw new Error(`LSF config fetch failed: ${lsfResponse.status}`);
        }
        
        allConfigs.vnc = await vncResponse.json();
        allConfigs.lsf = await lsfResponse.json();
        
        console.log('VNC config loaded:', allConfigs.vnc);
        console.log('LSF config loaded:', allConfigs.lsf);
        
        // Store the enabled defaults for pre-selection
        allConfigs.enabledDefaults = {
            cores: allConfigs.lsf.enabled_cores || allConfigs.lsf.core_options,
            memory: allConfigs.lsf.enabled_memory || allConfigs.lsf.memory_options_gb || allConfigs.lsf.memory_options,
            window_managers: allConfigs.vnc.enabled_window_managers || allConfigs.vnc.window_managers,
            queues: allConfigs.lsf.enabled_queues || allConfigs.lsf.queues,
            os_options: allConfigs.lsf.enabled_os_options || allConfigs.lsf.os_options
        };
        
        console.log('Enabled defaults:', allConfigs.enabledDefaults);
        console.log('All configurations loaded successfully');
        
        return true;
    } catch (error) {
        console.error('Error loading configurations:', error);
        console.error('Error stack:', error.stack);
        showMessage('Failed to load configurations: ' + error.message, 'error');
        return false;
    }
}

// Load and display manager overrides
async function loadManagerOverrides() {
    console.log('Loading manager overrides');
    const tableBody = document.getElementById('overrides-table-body');
    const noOverridesMessage = document.getElementById('no-overrides-message');
    
    // Show loading state
    tableBody.innerHTML = `
        <tr class="loading-row">
            <td colspan="8" class="loading-cell">
                <div class="loading-spinner">
                    <i class="fas fa-spinner fa-spin"></i> Loading overrides...
                </div>
            </td>
        </tr>
    `;
    
    try {
        const response = await fetch('/api/manager/overrides');
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.message || 'Failed to load overrides');
        }
        
        const overrides = data.overrides || [];
        
        if (overrides.length === 0) {
            tableBody.innerHTML = '';
            noOverridesMessage.style.display = 'flex';
        } else {
            noOverridesMessage.style.display = 'none';
            displayOverrides(overrides);
        }
    } catch (error) {
        console.error('Error loading overrides:', error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; padding: 2rem; color: var(--color-danger);">
                    <i class="fas fa-exclamation-triangle"></i> Error loading overrides: ${error.message}
                </td>
            </tr>
        `;
    }
}

// Display overrides in the table
function displayOverrides(overrides) {
    const tableBody = document.getElementById('overrides-table-body');
    
    tableBody.innerHTML = overrides.map(override => `
        <tr>
            <td><strong>${escapeHtml(override.username)}</strong></td>
            <td>${formatArrayOrDefault(override.cores)}</td>
            <td>${formatArrayOrDefault(override.memory)}</td>
            <td>${formatArrayOrDefault(override.window_managers)}</td>
            <td>${formatArrayOrDefault(override.queues)}</td>
            <td>${formatOsOptions(override.os_options)}</td>
            <td>${escapeHtml(override.created_by)}</td>
            <td>
                <button class="button small secondary" onclick="editOverride('${escapeHtml(override.username)}')">
                    <i class="fas fa-edit"></i> Edit
                </button>
                <button class="button small danger" onclick="deleteOverride('${escapeHtml(override.username)}')">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </td>
        </tr>
    `).join('');
}

// Format array for display, or show "Default" if null/empty
function formatArrayOrDefault(arr) {
    if (!arr || arr.length === 0) {
        return '<em style="color: #999;">Global Default</em>';
    }
    return arr.join(', ');
}

// Format OS options for display
function formatOsOptions(osOptions) {
    if (!osOptions || osOptions.length === 0) {
        return '<em style="color: #999;">Global Default</em>';
    }
    // OS options are stored as names, display them directly
    return osOptions.join(', ');
}

// Open the override modal for adding or editing
async function openOverrideModal(username = null) {
    console.log('openOverrideModal called with username:', username);
    
    const modal = document.getElementById('override-modal');
    const modalTitle = document.getElementById('override-modal-title');
    const usernameInput = document.getElementById('override-username');
    
    console.log('Modal element:', modal);
    console.log('Modal title element:', modalTitle);
    console.log('Username input element:', usernameInput);
    
    if (!modal) {
        console.error('Override modal not found!');
        return;
    }
    
    // Make sure configurations are loaded before opening modal
    if (!allConfigs.vnc || !allConfigs.lsf) {
        console.log('Configurations not loaded yet, loading now...');
        const success = await loadAllConfigurations();
        if (!success) {
            console.error('Failed to load configurations');
            showMessage('Failed to load configuration data. Please check console for errors.', 'error');
            return;
        }
    }
    
    console.log('Configurations available:', {
        vnc: !!allConfigs.vnc,
        lsf: !!allConfigs.lsf,
        vncData: allConfigs.vnc,
        lsfData: allConfigs.lsf
    });
    
    // Clear the form
    clearOverrideForm();
    
    // Set modal title and username field
    if (username) {
        // Editing existing override
        if (modalTitle) modalTitle.textContent = 'Edit User Override';
        if (usernameInput) {
            usernameInput.value = username;
            usernameInput.disabled = true;
        }
    } else {
        // Adding new override
        if (modalTitle) modalTitle.textContent = 'Add User Override';
        if (usernameInput) {
            usernameInput.value = '';
            usernameInput.disabled = false;
        }
    }
    
    // Populate the form with all available options FIRST
    populateOverrideForm();
    
    // Then load and select values based on whether editing or creating
    if (username) {
        // Editing - load the existing override data and select those values
        console.log('Loading override data for editing');
        await loadOverrideForEdit(username);
    } else {
        // Adding new - pre-select enabled defaults
        if (allConfigs.enabledDefaults) {
            console.log('Pre-selecting enabled defaults for new override');
            preselectEnabledDefaults();
        }
    }
    
    // Show the modal
    console.log('Showing modal...');
    modal.classList.add('active');
    modal.style.display = 'flex';
    console.log('Modal classes:', modal.className);
    console.log('Modal display style:', modal.style.display);
}

// Close the override modal
function closeOverrideModal() {
    const modal = document.getElementById('override-modal');
    modal.classList.remove('active');
    modal.style.display = 'none';
    currentOverride = null;
}

// Clear the override form
function clearOverrideForm() {
    document.getElementById('override-username').value = '';
    document.getElementById('override-cores').selectedIndex = -1;
    document.getElementById('override-memory').selectedIndex = -1;
    document.getElementById('override-window-managers').selectedIndex = -1;
    document.getElementById('override-queues').selectedIndex = -1;
    document.getElementById('override-os-options').selectedIndex = -1;
}

// Populate the override form with all available options
function populateOverrideForm() {
    console.log('populateOverrideForm called');
    console.log('allConfigs:', allConfigs);
    
    if (!allConfigs.vnc || !allConfigs.lsf) {
        console.error('Configurations not loaded yet');
        showMessage('Error: Configuration data not available. Please refresh and try again.', 'error');
        return;
    }
    
    // Populate cores
    const coresSelect = document.getElementById('override-cores');
    if (coresSelect && allConfigs.lsf.core_options) {
        console.log('Populating cores:', allConfigs.lsf.core_options);
        coresSelect.innerHTML = allConfigs.lsf.core_options.map(core => 
            `<option value="${core}">${core} cores</option>`
        ).join('');
    } else {
        console.error('Cores select not found or no core options');
    }
    
    // Populate memory
    const memorySelect = document.getElementById('override-memory');
    const memoryOptions = allConfigs.lsf.memory_options_gb || allConfigs.lsf.memory_options;
    if (memorySelect && memoryOptions) {
        console.log('Populating memory:', memoryOptions);
        memorySelect.innerHTML = memoryOptions.map(mem => 
            `<option value="${mem}">${mem} GB</option>`
        ).join('');
    } else {
        console.error('Memory select not found or no memory options');
    }
    
    // Populate window managers
    const wmSelect = document.getElementById('override-window-managers');
    if (wmSelect && allConfigs.vnc.window_managers) {
        console.log('Populating window managers:', allConfigs.vnc.window_managers);
        wmSelect.innerHTML = allConfigs.vnc.window_managers.map(wm => 
            `<option value="${wm}">${wm}</option>`
        ).join('');
    } else {
        console.error('Window managers select not found or no WM options');
    }
    
    // Populate queues
    const queuesSelect = document.getElementById('override-queues');
    if (queuesSelect && allConfigs.lsf.queues) {
        console.log('Populating queues:', allConfigs.lsf.queues);
        queuesSelect.innerHTML = allConfigs.lsf.queues.map(queue => 
            `<option value="${queue}">${queue}</option>`
        ).join('');
    } else {
        console.error('Queues select not found or no queue options');
    }
    
    // Populate OS options
    const osSelect = document.getElementById('override-os-options');
    if (osSelect && allConfigs.lsf.os_options) {
        console.log('Populating OS options:', allConfigs.lsf.os_options);
        osSelect.innerHTML = allConfigs.lsf.os_options.map(os => 
            `<option value="${os.name}">${os.name}</option>`
        ).join('');
    } else {
        console.error('OS select not found or no OS options');
    }
    
    console.log('Form population complete');
}

// Load existing override data for editing
async function loadOverrideForEdit(username) {
    try {
        console.log('loadOverrideForEdit called for username:', username);
        const response = await fetch('/api/manager/overrides');
        const data = await response.json();
        
        console.log('Received overrides data:', data);
        
        if (!data.success) {
            throw new Error('Failed to load overrides');
        }
        
        const override = data.overrides.find(o => o.username === username);
        if (!override) {
            throw new Error('Override not found');
        }
        
        console.log('Found override for editing:', override);
        currentOverride = override;
        
        // Set selected values - handle null values (which mean use global defaults)
        if (override.cores !== null) {
            console.log('Setting cores:', override.cores);
            setMultiSelectValues('override-cores', override.cores);
        }
        
        if (override.memory !== null) {
            console.log('Setting memory:', override.memory);
            setMultiSelectValues('override-memory', override.memory);
        }
        
        if (override.window_managers !== null) {
            console.log('Setting window_managers:', override.window_managers);
            setMultiSelectValues('override-window-managers', override.window_managers);
        }
        
        if (override.queues !== null) {
            console.log('Setting queues:', override.queues);
            setMultiSelectValues('override-queues', override.queues);
        }
        
        if (override.os_options !== null) {
            console.log('Setting os_options:', override.os_options);
            setMultiSelectValues('override-os-options', override.os_options);
        }
        
        console.log('Override data loaded and selections set');
        
    } catch (error) {
        console.error('Error loading override for edit:', error);
        showMessage('Failed to load override data', 'error');
    }
}

// Pre-select the currently enabled defaults
function preselectEnabledDefaults() {
    console.log('Preselecting enabled defaults');
    
    if (!allConfigs.enabledDefaults) {
        console.warn('No enabled defaults available');
        return;
    }
    
    // Pre-select enabled cores
    if (allConfigs.enabledDefaults.cores) {
        setMultiSelectValues('override-cores', allConfigs.enabledDefaults.cores);
    }
    
    // Pre-select enabled memory
    if (allConfigs.enabledDefaults.memory) {
        setMultiSelectValues('override-memory', allConfigs.enabledDefaults.memory);
    }
    
    // Pre-select enabled window managers
    if (allConfigs.enabledDefaults.window_managers) {
        setMultiSelectValues('override-window-managers', allConfigs.enabledDefaults.window_managers);
    }
    
    // Pre-select enabled queues
    if (allConfigs.enabledDefaults.queues) {
        setMultiSelectValues('override-queues', allConfigs.enabledDefaults.queues);
    }
    
    // Pre-select enabled OS options
    if (allConfigs.enabledDefaults.os_options) {
        // For OS options, we need to extract the names if they're objects
        const osNames = allConfigs.enabledDefaults.os_options.map(os => 
            typeof os === 'string' ? os : os.name
        );
        setMultiSelectValues('override-os-options', osNames);
    }
    
    console.log('Enabled defaults pre-selected');
}

// Helper to set multi-select values
function setMultiSelectValues(selectId, values) {
    const select = document.getElementById(selectId);
    if (!select) {
        console.warn(`Select element ${selectId} not found`);
        return;
    }
    
    console.log(`Setting values for ${selectId}:`, values);
    
    // Clear all selections
    Array.from(select.options).forEach(option => option.selected = false);
    
    // Set selected values
    if (values && values.length > 0) {
        Array.from(select.options).forEach(option => {
            if (values.includes(parseInt(option.value)) || values.includes(option.value)) {
                option.selected = true;
                console.log(`Selected ${option.value} in ${selectId}`);
            }
        });
    }
}

// Get selected values from multi-select
function getMultiSelectValues(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return null;
    
    const selected = Array.from(select.selectedOptions).map(option => {
        // Try to parse as number, otherwise return as string
        const num = parseInt(option.value);
        return isNaN(num) ? option.value : num;
    });
    
    return selected.length > 0 ? selected : null;
}

// Save or update override
async function saveOverride() {
    const username = document.getElementById('override-username').value.trim();
    
    if (!username) {
        showMessage('Please enter a username', 'error');
        return;
    }
    
    // Get selected values (null means use global defaults)
    const overrides = {
        cores: getMultiSelectValues('override-cores'),
        memory: getMultiSelectValues('override-memory'),
        window_managers: getMultiSelectValues('override-window-managers'),
        queues: getMultiSelectValues('override-queues'),
        os_options: getMultiSelectValues('override-os-options')
    };
    
    console.log('Saving override for username:', username);
    console.log('Override data:', overrides);
    
    const requestBody = {
        username: username,
        overrides: overrides
    };
    
    console.log('Request body:', JSON.stringify(requestBody, null, 2));
    
    try {
        console.log('Sending POST request to /api/manager/overrides');
        const response = await fetch('/api/manager/overrides', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        
        const responseText = await response.text();
        console.log('Response text:', responseText);
        
        let data;
        try {
            data = JSON.parse(responseText);
        } catch (e) {
            console.error('Failed to parse response as JSON:', e);
            throw new Error('Server returned invalid response: ' + responseText.substring(0, 100));
        }
        
        console.log('Parsed response data:', data);
        
        if (!response.ok) {
            throw new Error(data.message || `Server returned error: ${response.status}`);
        }
        
        if (!data.success) {
            throw new Error(data.message || 'Failed to save override');
        }
        
        showMessage(`Override saved successfully for user ${username}`, 'success');
        closeOverrideModal();
        loadManagerOverrides();
        
    } catch (error) {
        console.error('Error saving override:', error);
        console.error('Error stack:', error.stack);
        showMessage(`Failed to save override: ${error.message}`, 'error');
    }
}

// Edit an existing override
function editOverride(username) {
    openOverrideModal(username);
}

// Delete an override
async function deleteOverride(username) {
    // Since confirm is overridden in index.html, just show a message and proceed
    console.log(`Deleting override for user ${username}`);
    
    try {
        const response = await fetch('/api/manager/overrides', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: username
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.message || 'Failed to delete override');
        }
        
        showMessage(`Override deleted successfully for user ${username}`, 'success');
        loadManagerOverrides();
        
    } catch (error) {
        console.error('Error deleting override:', error);
        showMessage(`Failed to delete override: ${error.message}`, 'error');
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Make functions globally accessible for inline onclick handlers
window.openOverrideModal = openOverrideModal;
window.closeOverrideModal = closeOverrideModal;
window.saveOverride = saveOverride;
window.editOverride = editOverride;
window.deleteOverride = deleteOverride;
window.loadManagerOverrides = loadManagerOverrides;
window.initManagerOverrides = initManagerOverrides;

console.log('Manager overrides functions registered to window object');
console.log('openOverrideModal available:', typeof window.openOverrideModal);
console.log('loadManagerOverrides available:', typeof window.loadManagerOverrides);

// Note: initManagerOverrides() is now called from app.js when the Manager Mode tab is activated
// This ensures proper timing and that all DOM elements are available

