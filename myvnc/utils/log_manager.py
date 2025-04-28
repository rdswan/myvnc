import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Global logger instance
logger = None
# Global log file path
current_log_file = None

def setup_logging(config=None):
    """
    Set up logging based on configuration
    
    Args:
        config: Server configuration dictionary with logging settings
    """
    global logger, current_log_file
    
    # Always create a fresh logger - don't reuse
    logger = logging.getLogger('myvnc')
    logger.setLevel(logging.DEBUG)
    
    # Clear any existing handlers
    if logger.handlers:
        logger.handlers.clear()
    
    # Set format for log messages
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Debug prints
    print(f"DEBUG: Config type received in setup_logging: {type(config)}")
    print(f"DEBUG: Config content received in setup_logging: {config}")
    
    # Create a log file regardless of config
    try:
        # Default logdir is 'logs' relative to the project root
        project_root = Path(__file__).parent.parent.parent
        logdir = 'logs'
        
        # If config has a logdir, use that instead
        if config and isinstance(config, dict) and 'logdir' in config and config['logdir']:
            logdir = config['logdir']
            print(f"DEBUG: Using logdir from config: {logdir}")
        else:
            print(f"DEBUG: Using default logdir: {logdir}")
        
        # Create log directory if it doesn't exist
        logdir_path = Path(logdir)
        if not logdir_path.is_absolute():
            # If it's a relative path, make it relative to the project root
            logdir_path = project_root / logdir
        
        # Ensure log directory exists
        logdir_path.mkdir(exist_ok=True, parents=True)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = logdir_path / f'myvnc_{timestamp}.log'
        current_log_file = log_file
        
        full_path = log_file.absolute()
        print(f"DEBUG: Creating log file at: {full_path}")
        
        # Add file handler
        file_handler = logging.FileHandler(str(full_path))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Log to both console and file
        console_msg = f"Logging to file: {full_path}"
        print(f"INFO: {console_msg}")
        logger.info(console_msg)
    except Exception as e:
        # If we can't set up file logging, log to console
        error_msg = f"Error setting up file logging: {str(e)}"
        print(f"ERROR: {error_msg}")
        if logger:
            logger.error(error_msg)
    
    return logger

def get_logger():
    """Get the global logger instance"""
    global logger
    if logger is None:
        # If logger is not set up yet, create a basic console logger
        logger = setup_logging()
    return logger

def get_current_log_file():
    """Get the current log file path"""
    global current_log_file
    return current_log_file 