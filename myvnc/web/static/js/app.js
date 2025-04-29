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
        showMessage('Could not load VNC configuration. Please try again later.', 'error');
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
        // Get form data and convert to object
        const formData = new FormData(createVNCForm);
        const data = {};
        
        // Only include non-empty values
        for (const [key, value] of formData.entries()) {
            // Skip empty session names to ensure they're not sent at all
            if (key === 'name' && (!value || value.trim() === '')) {
                continue;
            }
            
            // Include all fields including memory_gb
            data[key] = value;
        }
        
        // Make sure memory_gb is included from the slider
        const memorySlider = document.getElementById('lsf-memory');
        if (memorySlider) {
            // Get the current value
            const currentValue = parseInt(memorySlider.value);
            
            // If we have memory options stored, ensure we use a valid option
            if (memorySlider.dataset.memoryOptions) {
                const options = JSON.parse(memorySlider.dataset.memoryOptions);
                
                // Find the closest memory option
                let closestOption = options[0];
                let minDiff = Math.abs(currentValue - options[0]);
                
                for (let i = 1; i < options.length; i++) {
                    const diff = Math.abs(currentValue - options[i]);
                    if (diff < minDiff) {
                        minDiff = diff;
                        closestOption = options[i];
                    }
                }
                
                data['memory_gb'] = closestOption.toString();
            } else {
                // Fallback if no memory options are available
                data['memory_gb'] = currentValue.toString();
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

// Calculate job running time
function calculateRunningTime(submitTime) {
    if (!submitTime) {
        return 'N/A';
    }
    
    try {
        // Parse the submit time
        let submitDate;
        
        // Try to parse in standard ISO format
        if (submitTime.includes('-')) {
            // Assuming ISO format 'YYYY-MM-DD HH:MM:SS'
            submitDate = new Date(submitTime);
        } else {
            // For other formats, try a more tolerant parser
            const parts = submitTime.split(/[\s:\/]/);
            if (parts.length >= 5) { // At least year, month, day, hour, minute
                // Different date formats depending on the parts
                const month = isNaN(parts[1]) ? parts[1] : parts[1] - 1; // JS months are 0-based
                submitDate = new Date(
                    parts[0], // year or month name
                    isNaN(parts[0]) ? new Date().getFullYear() : month, // month or year
                    parts[2], // day
                    parts[3], // hour
                    parts[4]  // minute
                );
            } else {
                // Fallback: try the default JS date parser
                submitDate = new Date(submitTime);
            }
        }
        
        // If parsing failed or the date is invalid, return N/A
        if (isNaN(submitDate.getTime())) {
            console.error('Unable to parse date:', submitTime);
            return 'N/A';
        }
        
        const now = new Date();
        
        // Calculate time difference in milliseconds
        const diff = now - submitDate;
        
        // Convert to days, hours, minutes
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        
        // Format the output based on the duration
        if (days > 0) {
            return `${days}d ${hours}h`;
        } else if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else {
            return `${minutes}m`;
        }
    } catch (e) {
        console.error('Error calculating running time:', e);
        return 'N/A';
    }
} 