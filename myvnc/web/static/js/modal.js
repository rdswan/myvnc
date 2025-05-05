/**
 * Simple modal functionality for settings
 */

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Modal.js loaded');
    
    // Get modal elements
    const settingsModal = document.getElementById('settings-modal');
    const closeButton = document.getElementById('settings-close');
    const cancelButton = document.getElementById('settings-cancel');
    
    // Close modal function 
    function closeModal() {
        console.log('Closing modal');
        if (settingsModal) {
            settingsModal.classList.remove('active');
        } else {
            console.error('Modal element not found');
        }
    }
    
    // Add event listeners for close and cancel buttons
    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
        console.log('Close button event listener added');
    }
    
    if (cancelButton) {
        cancelButton.addEventListener('click', closeModal);
        console.log('Cancel button event listener added');
    } else {
        console.warn('Cancel button not found');
    }
    
    // Close modal when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target === settingsModal) {
            closeModal();
        }
    });
    
    // Close modal with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && settingsModal && settingsModal.classList.contains('active')) {
            closeModal();
        }
    });
    
    // Make closeModal function available globally
    window.closeSettingsModal = closeModal;
    
    console.log('Modal.js initialization complete');
}); 