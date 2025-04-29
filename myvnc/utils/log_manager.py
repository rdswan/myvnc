import os
import sys
import logging
import atexit
import subprocess
import datetime
from pathlib import Path

# Global logger instance
logger = None
# Global log file path
current_log_file = None
# Global log file handle
log_file_handle = None
# Original stdout and stderr
original_stdout = sys.stdout
original_stderr = sys.stderr

class LoggingTee:
    """
    Class to capture stdout/stderr and redirect to both console and log file
    """
    def __init__(self, file_handler, original_stream):
        self.file_handler = file_handler
        self.original_stream = original_stream
    
    def write(self, message):
        # Write to original stream (console)
        self.original_stream.write(message)
        
        # Also write to log file
        self.file_handler.write(message)
        self.file_handler.flush()  # Ensure immediate writing to disk
    
    def flush(self):
        try:
            self.original_stream.flush()
        except BrokenPipeError:
            # Handle broken pipe error - this can happen when the parent process terminates
            pass
        except Exception as e:
            # Log other exceptions but don't crash
            print(f"Error flushing original stream: {str(e)}")
        
        try:
            # Check if the file handler is closed before flushing
            if not self.file_handler.closed:
                self.file_handler.flush()
        except Exception as e:
            # Log other exceptions but don't crash
            print(f"Error flushing file handler: {str(e)}")
        
    def isatty(self):
        # Needed for compatibility with interactive prompts
        return self.original_stream.isatty() 

def register_subprocess_handler():
    """Register a custom subprocess handler to capture output from subprocesses"""
    old_popen = subprocess.Popen
    
    def new_popen(*args, **kwargs):
        # Log the command that's about to be executed
        cmd_str = ' '.join(str(arg) for arg in args[0]) if args and isinstance(args[0], (list, tuple)) else str(args[0])
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
        print(f"{timestamp} - myvnc - INFO - COMMAND: {cmd_str}")
        if logger:
            logger.info(f"EXECUTING COMMAND: {cmd_str}")
        
        # Make sure stdout and stderr are captured
        if 'stdout' not in kwargs:
            kwargs['stdout'] = subprocess.PIPE
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
            
        # Create the process
        process = old_popen(*args, **kwargs)
        
        # Get the original communicate method
        old_communicate = process.communicate
        
        # Override communicate to log output
        def new_communicate(*args, **kwargs):
            output, error = old_communicate(*args, **kwargs)
            
            # Format timestamp consistently
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
            
            if output:
                try:
                    output_str = output.decode('utf-8')
                    print(f"{timestamp} - myvnc - INFO - COMMAND OUTPUT: {cmd_str}\n{output_str}")
                    if logger:
                        logger.info(f"COMMAND OUTPUT from '{cmd_str}':")
                        for line in output_str.splitlines():
                            logger.info(f"  {line}")
                except Exception as e:
                    print(f"Error logging subprocess output: {str(e)}")
            
            if error:
                try:
                    error_str = error.decode('utf-8')
                    print(f"{timestamp} - myvnc - ERROR - COMMAND ERROR: {cmd_str}\n{error_str}")
                    if logger:
                        logger.error(f"COMMAND ERROR from '{cmd_str}':")
                        for line in error_str.splitlines():
                            logger.error(f"  {line}")
                except Exception as e:
                    print(f"Error logging subprocess error: {str(e)}")
                    
            return output, error
            
        process.communicate = new_communicate
        return process
        
    # Replace the global Popen with our version
    subprocess.Popen = new_popen

def setup_logging(config=None):
    """
    Set up logging based on configuration
    
    Args:
        config: Server configuration dictionary with logging settings
    """
    global logger, current_log_file, original_stdout, original_stderr, log_file_handle
    
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
    
    # Create a log file
    try:
        # Default logdir is '/tmp'
        logdir = '/tmp'
        
        # If config has a logdir, use that instead
        if config and isinstance(config, dict) and 'logdir' in config and config['logdir']:
            logdir = config['logdir']
            print(f"DEBUG: Using logdir from config: {logdir}")
        else:
            print(f"DEBUG: Using default logdir: {logdir}")
        
        # Create log directory if it doesn't exist
        logdir_path = Path(logdir)
        
        # Ensure log directory exists
        logdir_path.mkdir(exist_ok=True, parents=True)
        
        # Create log file with PID instead of timestamp
        pid = os.getpid()
        log_file = logdir_path / f'myvnc_{pid}.log'
        current_log_file = log_file
        
        full_path = log_file.absolute()
        print(f"DEBUG: Creating log file at: {full_path}")
        
        # Add file handler for logging
        file_handler = logging.FileHandler(str(full_path))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Open the log file for stdout/stderr redirection
        log_file_handle = open(str(full_path), 'a')
        
        # Redirect stdout and stderr to both console and log file
        sys.stdout = LoggingTee(log_file_handle, original_stdout)
        sys.stderr = LoggingTee(log_file_handle, original_stderr)
        
        # Register close function to avoid file handle leaks
        atexit.register(lambda: log_file_handle.close() if log_file_handle and not log_file_handle.closed else None)
        
        # Register subprocess handler to capture output from subprocesses
        register_subprocess_handler()
        
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
        # If logger is not set up yet, create a basic console logger with config
        try:
            # Import here to avoid circular imports
            from myvnc.web.server import load_server_config
            config = load_server_config()
            logger = setup_logging(config=config)
        except ImportError:
            # If we can't import the server module, use default config
            logger = setup_logging()
    return logger

def get_current_log_file():
    """Get the current log file path"""
    global current_log_file
    return current_log_file

def log_command_output(command, stdout, stderr=None, success=True):
    """
    Log command output to the log file
    
    Args:
        command: Command that was executed
        stdout: Standard output from the command
        stderr: Standard error from the command (optional)
        success: Whether the command was successful
    """
    logger = get_logger()
    
    if logger:
        logger.info(f"Command executed: {command}")
        
        if stdout:
            stdout_str = stdout if isinstance(stdout, str) else stdout.decode('utf-8') if isinstance(stdout, bytes) else str(stdout)
            for line in stdout_str.splitlines():
                if line.strip():
                    logger.info(f"Command output: {line}")
        
        if stderr:
            stderr_str = stderr if isinstance(stderr, str) else stderr.decode('utf-8') if isinstance(stderr, bytes) else str(stderr)
            for line in stderr_str.splitlines():
                if line.strip():
                    logger.warning(f"Command error: {line}")
        
        if not success:
            logger.error(f"Command failed: {command}")
    else:
        print(f"Warning: Logger not initialized when logging command output for: {command}") 