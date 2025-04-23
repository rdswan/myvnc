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
        refreshVNCList().finally(() => {
            setTimeout(() => refreshButton.classList.remove('rotating'), 500);
        });
    });
    
    createVNCForm.addEventListener('submit', createVNCSession);
    messageClose.addEventListener('click', hideMessage);
    
    // Load configurations
    loadVNCConfig();
    loadLSFConfig();
    
    // Load initial VNC list
    refreshVNCList();
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
        showMessage(error.message, 'error');
        console.error('API Error:', error);
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
        
        // Populate form fields
        populateSelect('lsf-queue', lsfConfig.queues, lsfConfig.defaults.queue);
        populateSelect('lsf-cores', lsfConfig.core_options, lsfConfig.defaults.num_cores);
        populateSelect('lsf-memory', lsfConfig.memory_options, lsfConfig.defaults.memory_mb);
    } catch (error) {
        console.error('Failed to load LSF configuration:', error);
    }
}

// Refresh VNC List
async function refreshVNCList() {
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
            
            // Create cells
            row.innerHTML = `
                <td>${job.job_id}</td>
                <td>${job.name}</td>
                <td>${job.user}</td>
                <td><span class="status-badge ${statusClass}">${job.status}</span></td>
                <td>${job.queue}</td>
                <td class="actions-cell">
                    <button class="button secondary connect-button" data-job-id="${job.job_id}" title="Connect to VNC">
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
    }
}

// Connect to VNC
function connectToVNC(job) {
    // This would typically open a VNC connection
    // For now, we'll just show a message
    showMessage(`Connecting to VNC session: ${job.name}`, 'info');
    
    // In a real implementation, this would redirect to the VNC client or open it in a new window
    // window.open(`/vnc/connect/${job.job_id}`, '_blank');
}

// Create VNC Session
async function createVNCSession(event) {
    event.preventDefault();
    
    // Show loading on button
    const submitButton = createVNCForm.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    submitButton.disabled = true;
    
    // Get form data
    const formData = new FormData(createVNCForm);
    const data = {};
    
    // Use default name if not provided
    if (!formData.get('name') || formData.get('name').trim() === '') {
        data.name = `${vncConfig.defaults.name_prefix}_${generateRandomId()}`;
    }
    
    // Convert form data to object
    for (const [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    try {
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
                <button class="button secondary cancel-button">Cancel</button>
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
            refreshVNCList();
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
            color: var(--text-color);
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
            background-color: rgba(46, 204, 113, 0.15);
            color: #27ae60;
        }
        
        .status-pending {
            background-color: rgba(52, 152, 219, 0.15);
            color: #2980b9;
        }
        
        .status-error {
            background-color: rgba(231, 76, 60, 0.15);
            color: #c0392b;
        }
        
        .status-done {
            background-color: rgba(149, 165, 166, 0.15);
            color: #7f8c8d;
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