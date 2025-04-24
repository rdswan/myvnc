// Global variables
let vncConfig = {};
let lsfConfig = {};

// DOM Elements
const tabs = document.querySelectorAll('.tab-button');
const tabContents = document.querySelectorAll('.tab-content');
const refreshButton = document.getElementById('refresh-button');
const createVNCForm = document.getElementById('create-vnc-form');
const vncTableBody = document.getElementById('vnc-table-body');
const noVNCMessage = document.getElementById('no-vnc-message');
const messageBox = document.getElementById('message-box');
const messageText = document.getElementById('message-text');
const messageClose = document.getElementById('message-close');

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tabs
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.getAttribute('data-tab');
            changeTab(tabId);
        });
    });
    
    // Set up event listeners
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
    
    createVNCForm.addEventListener('submit', createVNCSession);
    messageClose.addEventListener('click', hideMessage);
    
    // Load configurations
    loadVNCConfig();
    loadLSFConfig();
    
    // Load initial VNC list
    refreshVNCList();
    
    // Initial load of debug info when debug tab is clicked
    document.getElementById('debug-tab').addEventListener('click', loadDebugInfo);
});

// Tab functionality
function changeTab(tabId) {
    // Deactivate all tabs
    tabs.forEach(tab => tab.classList.remove('active'));
    tabContents.forEach(content => content.classList.remove('active'));
    
    // Activate selected tab
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    document.getElementById(tabId).classList.add('active');
    
    // Add animation class to fade in content
    const activeContent = document.getElementById(tabId);
    activeContent.classList.add('fade-in');
    setTimeout(() => activeContent.classList.remove('fade-in'), 300);
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
        const response = await fetch(`/api/${endpoint}`, options);
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'An error occurred');
        }
        
        return result;
    } catch (error) {
        console.error('API Error:', error);
        // Don't show API errors for list requests, as they might be expected
        if (!endpoint.includes('vnc/list')) {
            showMessage(error.message || 'API request failed. Please try again later.', 'error');
        }
        throw error;
    }
}

// Load VNC Configuration
async function loadVNCConfig() {
    try {
        vncConfig = await apiRequest('config/vnc');
        
        // Populate form fields
        populateSelect('vnc-site', vncConfig.sites, vncConfig.defaults.site);
        populateSelect('vnc-resolution', vncConfig.resolutions, vncConfig.defaults.resolution);
        populateSelect('vnc-window-manager', vncConfig.window_managers, vncConfig.defaults.window_manager);
        
        // Set default name placeholder
        const randomId = generateRandomId();
        document.getElementById('vnc-name').placeholder = `${vncConfig.defaults.name_prefix}_${randomId}`;
    } catch (error) {
        console.error('Failed to load VNC configuration:', error);
    }
}

// Load LSF Configuration
async function loadLSFConfig() {
    try {
        lsfConfig = await apiRequest('config/lsf');
        
        // Populate select fields
        populateSelect('lsf-queue', lsfConfig.queues, lsfConfig.defaults.queue);
        populateSelect('lsf-cores', lsfConfig.core_options, lsfConfig.defaults.num_cores);
        
        // Set memory slider default value (directly using GB values)
        const memorySlider = document.getElementById('lsf-memory');
        const memoryValue = document.getElementById('memory-value');
        if (memorySlider && memoryValue) {
            // Get default memory in GB
            const defaultMemoryGB = lsfConfig.defaults.memory_gb || 16;
            // Round to nearest step value
            const stepSize = parseInt(memorySlider.step) || 4;
            const roundedValue = Math.max(2, Math.round(defaultMemoryGB / stepSize) * stepSize);
            
            // Set the slider value
            memorySlider.value = roundedValue;
            memoryValue.textContent = roundedValue;
        }
    } catch (error) {
        console.error('Failed to load LSF configuration:', error);
    }
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
        const jobs = await apiRequest('vnc/list');
        
        // Clear table
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
                <td>${job.num_cores || '-'} cores, ${job.memory_gb || '-'} GB</td>
                <td title="VNC Connection: ${connectionInfo}">${job.host || 'N/A'}</td>
                <td>:${job.display || 'N/A'}</td>
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

// Connect to VNC
function connectToVNC(job) {
    // Format a proper VNC connection message with host and port information
    let connectionString = job.host || 'unknown host';
    
    if (job.port) {
        connectionString = `${job.host}:${job.port}`;
        showMessage(`Connecting to VNC session on ${connectionString}. Use a VNC client to connect.`, 'info');
    } else {
        showMessage(`VNC connection details unavailable for ${job.name || 'session'} on ${connectionString}.`, 'warning');
    }
    
    // In a production environment, you might:
    // 1. Redirect to a built-in web VNC client
    // 2. Launch a VNC client via a custom protocol handler
    // 3. Show detailed connection instructions for external VNC clients
    
    // Example of how you might implement #1:
    // if (job.port) {
    //     window.open(`/vnc/client?host=${job.host}&port=${job.port}`, '_blank');
    // }
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
        // Get form data and convert to object
        const formData = new FormData(createVNCForm);
        const data = {};
        
        // Only include non-empty values
        for (const [key, value] of formData.entries()) {
            // Skip empty session names to ensure they're not sent at all
            if (key === 'name' && (!value || value.trim() === '')) {
                continue;
            }
            
            // Include all other fields and non-empty session names
            if (key !== 'memory_gb') { // Skip memory_gb since we'll use the default from server
                data[key] = value;
            }
        }
        
        console.log('Submitting data:', data);
        
        const result = await apiRequest('vnc/create', 'POST', data);
        showMessage(`VNC session created successfully. Job ID: ${result.job_id}`, 'success');
        
        // Reset form
        createVNCForm.reset();
        
        // Switch to manager tab and refresh
        changeTab('vnc-manager');
        refreshVNCList();
    } catch (error) {
        console.error('Failed to create VNC session:', error);
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
            
            // Single refresh with a small delay to allow server to process kill
            setTimeout(() => refreshVNCList(), 250);
            
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
    select.innerHTML = '';
    
    options.forEach(option => {
        const optionElement = document.createElement('option');
        optionElement.value = option;
        optionElement.textContent = option;
        
        if (option === defaultValue) {
            optionElement.selected = true;
        }
        
        select.appendChild(optionElement);
    });
}

// Show Message
function showMessage(message, type = 'info') {
    messageText.textContent = message;
    messageBox.className = `message-box ${type}`;
    messageBox.classList.remove('hidden');
    
    // Auto-hide after 5 seconds
    setTimeout(hideMessage, 5000);
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
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }
        
        .status-running {
            background-color: rgba(30, 185, 128, 0.15);
            color: #1EB980; /* TT Light Green */
        }
        
        .status-pending {
            background-color: rgba(24, 196, 234, 0.15);
            color: #18C4EA; /* TT Light Blue */
        }
        
        .status-error {
            background-color: rgba(240, 79, 94, 0.15);
            color: #F04F5E; /* TT Light Red */
        }
        
        .status-done {
            background-color: rgba(51, 51, 61, 0.15);
            color: #33333D; /* TT Blue Grey */
        }
        
        .actions-cell {
            display: flex;
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
    `;
    
    document.head.appendChild(style);
});

/**
 * Load debug information from the server
 */
async function loadDebugInfo() {
    console.log('Loading debug information...');
    try {
        // Show loading indicator
        document.getElementById('debug-environment').innerHTML = '<p class="loading-message">Loading environment information...</p>';
        
        // Fetch environment data
        const data = await apiRequest('debug/environment');
        console.log('Debug data received:', data);
        
        // Display environment information
        displayEnvironmentInfo(data.environment);
    } catch (error) {
        console.error('Failed to load debug information:', error);
        document.getElementById('debug-environment').innerHTML = '<p class="error">Failed to load environment information.</p>';
    }
}

/**
 * Display environment information
 * @param {Object} environment - Environment information
 */
function displayEnvironmentInfo(environment) {
    const container = document.getElementById('debug-environment');
    
    if (!environment || Object.keys(environment).length === 0) {
        container.innerHTML = '<p>No environment information available.</p>';
        return;
    }
    
    let html = '';
    
    // Display each environment variable
    for (const [key, value] of Object.entries(environment)) {
        html += `
            <div class="env-item">
                <div class="env-key">${key}:</div>
                <div class="env-value">${value}</div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// Function to load debug data
function loadDebugData() {
    fetch('/api/debug')
        .then(response => response.json())
        .then(data => {
            displayDebugData(data);
        })
        .catch(error => {
            console.error('Error loading debug data:', error);
            document.getElementById('debug-content').innerHTML = 
                `<div class="alert alert-danger">Error loading debug data: ${error.message}</div>`;
        });
}

// Function to display debug data in a nice format
function displayDebugData(data) {
    const debugContentElement = document.getElementById('debug-content');
    
    // Create HTML content for debug data
    let html = '<div class="debug-section">';
    
    // Environment section
    html += '<h3>Environment Information</h3>';
    html += '<table class="table table-sm table-striped">';
    html += '<thead><tr><th>Name</th><th>Value</th></tr></thead><tbody>';
    
    for (const [key, value] of Object.entries(data.environment)) {
        html += `<tr><td>${key}</td><td>${value}</td></tr>`;
    }
    
    html += '</tbody></table>';
    
    // Configuration section
    html += '<h3>Configuration</h3>';
    html += '<div class="accordion" id="configAccordion">';
    
    let configIdx = 0;
    for (const [configType, configData] of Object.entries(data.config)) {
        configIdx++;
        const headerId = `heading${configIdx}`;
        const collapseId = `collapse${configIdx}`;
        
        html += '<div class="accordion-item">';
        html += `<h2 class="accordion-header" id="${headerId}">`;
        html += `<button class="accordion-button collapsed" type="button" 
                      data-bs-toggle="collapse" data-bs-target="#${collapseId}" 
                      aria-expanded="false" aria-controls="${collapseId}">
                    ${configType}
                 </button>`;
        html += '</h2>';
        html += `<div id="${collapseId}" class="accordion-collapse collapse" 
                     aria-labelledby="${headerId}" data-bs-parent="#configAccordion">`;
        html += '<div class="accordion-body">';
        html += `<pre>${JSON.stringify(configData, null, 2)}</pre>`;
        html += '</div></div></div>';
    }
    
    html += '</div>'; // Close accordion
    html += '</div>'; // Close debug-section
    
    debugContentElement.innerHTML = html;
}

// Event listener for debug tab
document.getElementById('debug-tab').addEventListener('click', function() {
    // Load debug data when debug tab is clicked
    loadDebugData();
}); 