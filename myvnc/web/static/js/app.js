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
    refreshButton.addEventListener('click', refreshVNCList);
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
        
        // Set default name prefix as placeholder
        document.getElementById('vnc-name').placeholder = `${vncConfig.defaults.name_prefix}_${generateRandomId()}`;
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
            return;
        }
        
        noVNCMessage.style.display = 'none';
        
        // Populate table
        jobs.forEach(job => {
            const row = document.createElement('tr');
            
            // Create cells
            row.innerHTML = `
                <td>${job.job_id}</td>
                <td>${job.name}</td>
                <td>${job.user}</td>
                <td>${job.status}</td>
                <td>${job.queue}</td>
                <td>
                    <button class="button danger kill-button" data-job-id="${job.job_id}">
                        <i class="fas fa-times"></i> Kill
                    </button>
                </td>
            `;
            
            // Add to table
            vncTableBody.appendChild(row);
        });
        
        // Add event listeners to kill buttons
        document.querySelectorAll('.kill-button').forEach(button => {
            button.addEventListener('click', () => {
                const jobId = button.getAttribute('data-job-id');
                killVNCSession(jobId);
            });
        });
    } catch (error) {
        console.error('Failed to refresh VNC list:', error);
    }
}

// Create VNC Session
async function createVNCSession(event) {
    event.preventDefault();
    
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
    }
}

// Kill VNC Session
async function killVNCSession(jobId) {
    if (!confirm(`Are you sure you want to kill VNC session ${jobId}?`)) {
        return;
    }
    
    try {
        await apiRequest(`vnc/kill/${jobId}`, 'POST');
        showMessage(`VNC session ${jobId} killed successfully.`, 'success');
        refreshVNCList();
    } catch (error) {
        console.error(`Failed to kill VNC session ${jobId}:`, error);
    }
}

// Helper function to populate select elements
function populateSelect(elementId, options, defaultValue) {
    const select = document.getElementById(elementId);
    select.innerHTML = '';
    
    options.forEach(option => {
        const optionElement = document.createElement('option');
        optionElement.value = option;
        optionElement.textContent = option;
        
        if (option == defaultValue) {
            optionElement.selected = true;
        }
        
        select.appendChild(optionElement);
    });
}

// Show message
function showMessage(message, type = 'info') {
    messageText.textContent = message;
    messageBox.classList.remove('hidden');
    messageBox.querySelector('.message-content').className = `message-content ${type}`;
    
    // Auto-hide after 5 seconds
    setTimeout(hideMessage, 5000);
}

// Hide message
function hideMessage() {
    messageBox.classList.add('hidden');
}

// Generate random ID for VNC name
function generateRandomId() {
    return Math.floor(Math.random() * 9000 + 1000);
} 