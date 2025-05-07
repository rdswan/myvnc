# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
import os
import sys
import logging
import atexit
import subprocess
import datetime
from pathlib import Path
import json
import shlex

# Global logger instance
logger = None
# Global log file path
current_log_file = None
# Global log file handle
log_file_handle = None
# Original stdout and stderr
original_stdout = sys.stdout
original_stderr = sys.stderr
# Flag to track if subprocess handler has been registered
subprocess_handler_registered = False

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
    global subprocess_handler_registered
    
    # Only register the handler once
    if subprocess_handler_registered:
        return
    
    # Mark as registered immediately to prevent race conditions
    subprocess_handler_registered = True
    
    old_popen = subprocess.Popen
    
    def new_popen(*args, **kwargs):
        # Get the command that's about to be executed
        cmd_str = ' '.join(str(arg) for arg in args[0]) if args and isinstance(args[0], (list, tuple)) else str(args[0])
        
        # Create a properly quoted command string for logging
        quoted_cmd_str = cmd_str
        if args and isinstance(args[0], (list, tuple)):
            cmd_list = args[0]
            # Simple and reliable quoting for logging
            quoted_args = []
            for arg in cmd_list:
                arg_str = str(arg)
                if ' ' in arg_str or ';' in arg_str or '=' in arg_str or '[' in arg_str or ']' in arg_str:
                    quoted_args.append(f'"{arg_str}"')
                else:
                    quoted_args.append(arg_str)
            quoted_cmd_str = ' '.join(quoted_args)
        
        # For logging, filter out sudo information if present
        log_cmd_str = quoted_cmd_str
        
        # Check if the command begins with sudo and is modifying an LSF command
        if log_cmd_str.startswith('sudo -u') and any(lsf_cmd in log_cmd_str for lsf_cmd in ['/bjobs', '/bsub', '/bkill']):
            # Extract the LSF command part
            try:
                # Find the LSF command part after sudo, extract just the command name without path
                parts = log_cmd_str.split()
                for i, part in enumerate(parts):
                    if '/bjobs' in part:
                        log_cmd_str = 'bjobs ' + ' '.join(parts[i+1:])
                        break
                    elif '/bsub' in part:
                        log_cmd_str = 'bsub ' + ' '.join(parts[i+1:])
                        break
                    elif '/bkill' in part:
                        log_cmd_str = 'bkill ' + ' '.join(parts[i+1:])
                        break
            except:
                # If parsing fails, keep the original command
                pass
            
            # Log the original command for INFO level
            if logger:
                logger.debug(f"DEBUG: Full command: {cmd_str}")
                logger.info(f"EXECUTING COMMAND: {log_cmd_str}")
        else:
            # Log the command that's about to be executed (no modification needed)
            if logger:
                logger.info(f"EXECUTING COMMAND: {log_cmd_str}")
        
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
            
            if output:
                try:
                    # If universal_newlines=True was used, output is already a string
                    if isinstance(output, str):
                        output_str = output
                    else:
                        output_str = output.decode('utf-8')
                        
                    if logger:
                        logger.info(f"COMMAND OUTPUT from '{log_cmd_str}':")
                        for line in output_str.splitlines():
                            logger.info(f"  {line}")
                except Exception as e:
                    logger.error(f"Error logging subprocess output: {str(e)}")
            
            if error:
                try:
                    # If universal_newlines=True was used, error is already a string
                    if isinstance(error, str):
                        error_str = error
                    else:
                        error_str = error.decode('utf-8')
                        
                    if logger:
                        logger.error(f"COMMAND ERROR from '{log_cmd_str}':")
                        for line in error_str.splitlines():
                            logger.error(f"  {line}")
                except Exception as e:
                    logger.error(f"Error logging subprocess error: {str(e)}")
                    
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
    
    # Set the logger level based on the debug configuration
    # Default to DEBUG if no config is provided, otherwise honor the debug flag
    if config and isinstance(config, dict) and 'debug' in config:
        if config['debug']:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
    else:
        # Default to DEBUG if debug flag not specified
        logger.setLevel(logging.DEBUG)
    
    # Clear any existing handlers to avoid duplicate logging
    if logger.handlers:
        logger.handlers.clear()
    
    # Set format for log messages
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    
    # Add console handler if one doesn't already exist
    has_console_handler = False
    has_file_handler = False
    
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            has_console_handler = True
        elif isinstance(handler, logging.FileHandler):
            has_file_handler = True
            
    if not has_console_handler:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        # Always show at least INFO level in console
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
    
    # Create a log file
    try:
        # Default logdir is '/tmp'
        logdir = '/tmp'
        
        # If config has a logdir, use that instead
        if config and isinstance(config, dict) and 'logdir' in config and config['logdir']:
            logdir = config['logdir']
        else:
            logdir = '/tmp'
        
        # Create log directory if it doesn't exist
        logdir_path = Path(logdir)
        
        # Ensure log directory exists
        logdir_path.mkdir(exist_ok=True, parents=True)
        
        # Check for special manage.py PID in environment
        if 'MYVNC_MANAGE_PID' in os.environ:
            manage_pid = os.environ['MYVNC_MANAGE_PID']
            log_file = logdir_path / f'myvnc_{manage_pid}.log'
        else:
            # Create log file with PID instead of timestamp
            pid = os.getpid()
            log_file = logdir_path / f'myvnc_{pid}.log'
        
        current_log_file = log_file
        
        full_path = log_file.absolute()
        
        # Only add file handler if one doesn't already exist for this log file
        if not has_file_handler:
            file_handler = logging.FileHandler(str(full_path))
            file_handler.setFormatter(formatter)
            # Always log at DEBUG level to the file
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
        
            # Open the log file for stdout/stderr redirection
            if log_file_handle is None or log_file_handle.closed:
                log_file_handle = open(str(full_path), 'a')
            
                # Redirect stdout and stderr to both console and log file
                # Only do this if we haven't already
                if sys.stdout is original_stdout:
                    sys.stdout = LoggingTee(log_file_handle, original_stdout)
                if sys.stderr is original_stderr:
                    sys.stderr = LoggingTee(log_file_handle, original_stderr)
            
                # Register close function to avoid file handle leaks
                atexit.register(lambda: log_file_handle.close() if log_file_handle and not log_file_handle.closed else None)
        
        # Register subprocess handler to capture output from subprocesses
        register_subprocess_handler()
        
        # Log to both console and file
        console_msg = f"Logging to file: {full_path}"
        logger.info(console_msg)
        
        # Log debug status
        if config and isinstance(config, dict) and 'debug' in config:
            debug_status = "enabled" if config['debug'] else "disabled"
            logger.info(f"Debug logging is {debug_status}")
        
        # Set up LDAP debug logging if authentication method is LDAP
        if config and isinstance(config, dict) and config.get('authentication', '').lower() == 'ldap':
            # Enable detailed LDAP logs 
            ldap_logger = logging.getLogger('ldap')
            ldap_logger.setLevel(logging.DEBUG)
            
            # Add dedicated LDAP file handler for more details
            ldap_log_file = logdir_path / f'ldap_debug_{pid}.log'
            try:
                ldap_file_handler = logging.FileHandler(str(ldap_log_file))
                ldap_file_handler.setFormatter(formatter)
                ldap_file_handler.setLevel(logging.DEBUG)
                ldap_logger.addHandler(ldap_file_handler)
                logger.info(f"LDAP debug logging enabled at: {ldap_log_file}")
            except Exception as e:
                logger.error(f"Could not set up LDAP debug log file: {str(e)}")
            
            # Also add LDAP logs to the main log
            ldap_logger.addHandler(file_handler)
            
            # Log LDAP availability
            try:
                # Try to determine LDAP status 
                has_ldap = False
                has_ldap3 = False
                
                try:
                    import ldap
                    has_ldap = True
                    logger.info("python-ldap module is available")
                except ImportError:
                    logger.warning("python-ldap module is not available")
                
                try:
                    import ldap3
                    has_ldap3 = True 
                    logger.info("ldap3 module is available")
                except ImportError:
                    logger.warning("ldap3 module is not available")
                
                if not has_ldap and not has_ldap3:
                    logger.error("No LDAP modules are available - authentication will fail")
            except Exception as e:
                logger.error(f"Error checking LDAP module availability: {str(e)}")
            
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
            # Load config directly without importing from server to avoid circular imports
            config = {}
            config_path = Path(__file__).parent.parent.parent / "config" / "server_config.json"
            
            try:
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load server config: {e}")
            
            # Check if there's a running server whose log we should use
            try:
                import psutil
                
                # Look for any process that might be our server
                for proc in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if "python" in cmdline and "main.py" in cmdline:
                            # We found a server process, check if it has a log file
                            log_path = config.get('logdir', '/tmp')
                            potential_log = os.path.join(log_path, f"myvnc_{proc.info['pid']}.log")
                            if os.path.exists(potential_log):
                                # Use the existing log file for this process
                                logger = logging.getLogger('myvnc')
                                # Re-initialize the logger with this file
                                logger.handlers.clear()  # Remove any existing handlers
                                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                                
                                # Create file handler for existing log file
                                file_handler = logging.FileHandler(potential_log)
                                file_handler.setFormatter(formatter)
                                logger.addHandler(file_handler)
                                
                                # Also add console handler
                                console_handler = logging.StreamHandler(sys.stdout)
                                console_handler.setFormatter(formatter)
                                logger.addHandler(console_handler)
                                
                                # Set global variables
                                global current_log_file
                                current_log_file = potential_log
                                
                                # Return the reused logger
                                return logger
                    except Exception:
                        # Ignore errors when checking processes
                        pass
            except ImportError:
                # psutil not available, skip this part
                pass
                
            # If we get here, either there's no running server or we couldn't reuse its log
            logger = setup_logging(config=config)
        except Exception as e:
            # If we have any issues, use default config
            print(f"Warning: Error setting up logger: {e}")
            logger = setup_logging()
    return logger

def get_current_log_file():
    """Get the current log file path"""
    global current_log_file
    return current_log_file

def log_command_output(command, stdout, stderr=None, success=True):
    """
    Log command output with standard formatting
    
    Args:
        command: Command string that was executed
        stdout: Standard output from the command
        stderr: Standard error from the command
        success: Whether the command was successful
    """
    logger = get_logger()
    
    # Filter out sudo information if present for LSF commands
    log_command = command
    if isinstance(command, str) and command.startswith('sudo -u') and any(lsf_cmd in command for lsf_cmd in ['/bjobs', '/bsub', '/bkill']):
        # Extract the LSF command part
        try:
            # Find the LSF command part after sudo, extract just the command name without path
            parts = command.split()
            for i, part in enumerate(parts):
                if '/bjobs' in part:
                    log_command = 'bjobs ' + ' '.join(parts[i+1:])
                    break
                elif '/bsub' in part:
                    log_command = 'bsub ' + ' '.join(parts[i+1:])
                    break
                elif '/bkill' in part:
                    log_command = 'bkill ' + ' '.join(parts[i+1:])
                    break
        except:
            # If parsing fails, keep the original command
            pass
        
        # Log the full command as DEBUG
        logger.debug(f"DEBUG: Full command: {command}")
    
    # Log the command that was executed
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"COMMAND {status}: {log_command}")
    
    # Log standard output
    if stdout:
        if isinstance(stdout, bytes):
            stdout = stdout.decode('utf-8')
            
        logger.info(f"COMMAND OUTPUT:")
        for line in stdout.splitlines():
            logger.info(f"  {line}")
    
    # Log standard error if available
    if stderr:
        if isinstance(stderr, bytes):
            stderr = stderr.decode('utf-8')
            
        if success:
            logger.info(f"COMMAND STDERR (non-fatal):")
        else:
            logger.error(f"COMMAND ERROR:")
            
        for line in stderr.splitlines():
            if success:
                logger.info(f"  {line}")
            else:
                logger.error(f"  {line}") 