# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
"""
SLURM Manager for submitting and monitoring SLURM jobs
"""

import subprocess
import shlex
import re
import sys
import time
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path
import signal


from myvnc.utils.config_manager import ConfigManager
from myvnc.utils.config_loader import load_server_config
from myvnc.utils.log_manager import get_logger


class SLURMError(Exception):
    """Custom exception for SLURM-related errors that preserves the original error message"""
    def __init__(self, message, stderr=None, stdout=None):
        super(SLURMError, self).__init__(message)
        self.stderr = stderr
        self.stdout = stdout
        self.original_message = message


class SLURMManager:
    """Manages interactions with the SLURM job scheduler via command line"""

    _instance = None
    _initialized = False

    def __new__(cls):
        """Ensure only one instance of SLURMManager is created"""
        if cls._instance is None:
            cls._instance = super(SLURMManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize the SLURM manager and check if SLURM is available

        Raises:
            RuntimeError: If SLURM is not available
        """
        if SLURMManager._initialized:
            return

        self.command_history = []
        self.config_manager = ConfigManager()
        self.environment = os.environ.copy()
        self.logger = get_logger()

        server_config = load_server_config()
        default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'setuid_runner')
        self.setuid_binary = server_config.get('setuid_runner', default_path)

        if 'setuid_runner' in server_config:
            self.logger.info(f"Using setuid_runner from config: {self.setuid_binary}")
        else:
            self.logger.info(f"Using default setuid_runner path: {self.setuid_binary}")

        try:
            self._check_slurm_available()
            self._check_setuid_binary()
        except Exception as e:
            print(f"Warning: SLURM initialization error: {str(e)}", file=sys.stderr)

        SLURMManager._initialized = True

    def get_command_history(self, limit=10):
        """Return the last N commands executed with their outputs"""
        return self.command_history[-limit:] if limit else self.command_history

    def _check_slurm_available(self):
        """
        Check if SLURM is available on the system and determine full paths for SLURM commands

        Raises:
            RuntimeError: If SLURM is not available
        """
        self.logger.info("Checking SLURM command availability")

        self.slurm_cmd_paths = {}

        slurm_commands = ['squeue', 'sbatch', 'srun', 'scancel', 'scontrol']

        for cmd in slurm_commands:
            try:
                self.logger.debug(f"Running 'which {cmd}' to find command path")
                result = subprocess.run(['which', cmd], check=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                cmd_path = result.stdout.decode('utf-8').strip()
                self.logger.info(f"Found {cmd} at: {cmd_path}")
                self.slurm_cmd_paths[cmd] = cmd_path
            except subprocess.CalledProcessError as e:
                stderr = e.stderr.decode('utf-8')
                self.logger.error(f"{cmd} not available: {stderr}")

                if cmd == 'squeue':
                    raise RuntimeError(f"SLURM is not available on this system: {stderr}")

        if not all(cmd in self.slurm_cmd_paths for cmd in slurm_commands):
            missing = [cmd for cmd in slurm_commands if cmd not in self.slurm_cmd_paths]
            self.logger.warning(f"Some SLURM commands not found: {', '.join(missing)}")
        else:
            self.logger.info(f"All SLURM commands found successfully: {', '.join(slurm_commands)}")

    def _check_setuid_binary(self):
        """
        Check if the setuid binary exists and has proper permissions

        Raises:
            RuntimeError: If the setuid binary is not properly configured
        """
        if not os.path.exists(self.setuid_binary):
            raise RuntimeError(f"Setuid binary not found at {self.setuid_binary}. Please compile it using 'make' and set permissions with 'sudo make install'.")

        if not os.access(self.setuid_binary, os.X_OK):
            raise RuntimeError(f"Setuid binary at {self.setuid_binary} is not executable.")

        try:
            stat_info = os.stat(self.setuid_binary)
            if not (stat_info.st_mode & 0o4000):
                self.logger.warning(f"Setuid binary at {self.setuid_binary} may not have setuid bit set. Run 'sudo make install' to fix.")
        except Exception as e:
            self.logger.warning(f"Could not check setuid permissions: {e}")

        self.logger.info(f"Setuid binary found at: {self.setuid_binary}")

    def _run_command(self, cmd: List[str], authenticated_user: str = None) -> str:
        """
        Run a command and return its output

        Args:
            cmd: Command to run as a list of arguments
            authenticated_user: Optional authenticated username to run command as

        Returns:
            Command output as a string

        Raises:
            SLURMError: If the command fails
        """
        modified_cmd = cmd.copy()

        slurm_command = cmd[0] if cmd else ""
        if slurm_command in self.slurm_cmd_paths:
            modified_cmd[0] = self.slurm_cmd_paths[slurm_command]

        if authenticated_user:
            modified_cmd = [self.setuid_binary, authenticated_user] + modified_cmd

        cmd_str = ' '.join(str(arg) for arg in cmd)
        modified_cmd_str = ' '.join(str(arg) for arg in modified_cmd)

        self.logger.debug(f"DEBUG: Original command: {cmd_str}")
        self.logger.debug(f"DEBUG: Modified command: {modified_cmd_str}")
        if authenticated_user:
            self.logger.debug(f"DEBUG: Running as authenticated user: {authenticated_user}")

        try:
            result = subprocess.run(modified_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout = result.stdout.decode('utf-8')
            stderr = result.stderr.decode('utf-8')

            if stdout:
                self.logger.info(f"Command output: {stdout}")
            if stderr:
                self.logger.info(f"Command stderr: {stderr}")

            self.command_history.append({
                'command': cmd_str,
                'stdout': stdout,
                'stderr': stderr,
                'success': True,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            return stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8')
            stdout = e.stdout.decode('utf-8') if e.stdout else ''

            is_no_jobs = ('Invalid job id' in stderr or
                          'slurm_load_jobs error' in stderr or
                          'No jobs' in stderr)

            if is_no_jobs:
                self.logger.debug(f"Command completed with no results: {cmd_str}")
                self.logger.debug(f"Command stderr: {stderr}")
            else:
                self.logger.error(f"Command failed: {cmd_str}")
                self.logger.error(f"Command stdout: {stdout}")
                self.logger.error(f"Command stderr: {stderr}")

            self.command_history.append({
                'command': cmd_str,
                'stdout': stdout,
                'stderr': stderr,
                'success': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            raise SLURMError(stderr.strip(), stderr=stderr, stdout=stdout)

    def _write_batch_script(self, script_content: str, script_path: str) -> str:
        """Write a SLURM batch script to disk and return the path.

        Args:
            script_content: The full batch script content
            script_path: Path to write the script to

        Returns:
            The path to the written script
        """
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
        self.logger.info(f"Wrote SLURM batch script to: {script_path}")
        return script_path

    def _get_display_from_file(self, job_id: str, user_home: str) -> Optional[str]:
        """Retrieve the VNC display number from the file written by vncserver_wrapper.

        In the SLURM environment, vncserver_wrapper writes VNC_DISPLAY to a file
        instead of using bpost. This method reads that file.

        Returns the display number as a string (e.g. "6") or None if not available.
        """
        display_file = os.path.join(user_home, '.vnc', f'myvnc_slurm_display.{job_id}')
        try:
            if os.path.exists(display_file):
                with open(display_file, 'r') as f:
                    content = f.read().strip()
                match = re.search(r'VNC_DISPLAY=:(\d+)', content)
                if match:
                    display = match.group(1)
                    self.logger.info(f"Found VNC display for SLURM job {job_id}: :{display}")
                    return display
                elif content.isdigit():
                    self.logger.info(f"Found VNC display for SLURM job {job_id}: :{content}")
                    return content
        except Exception as e:
            self.logger.warning(f"Could not read display file for SLURM job {job_id}: {e}")
        return None

    def submit_vnc_job(self, vnc_config: Dict, slurm_config: Dict, authenticated_user: str = None, fake_no_home: bool = False, server_hostname: str = None) -> str:
        """Submit a VNC job using sbatch

        Args:
            vnc_config: VNC configuration
            slurm_config: SLURM configuration
            authenticated_user: Optional authenticated username to run command as
            fake_no_home: Testing parameter to fake missing home directory
            server_hostname: Server hostname for error messages

        Returns:
            Job ID if successful

        Raises:
            SLURMError if submission fails
        """
        try:
            user = authenticated_user if authenticated_user else os.environ.get('USER', '')
            user_home = os.path.expanduser(f'~{user}')

            vnc_passwd_file = f'/home/{user}/.vnc/passwd'
            passwd_exists = False

            if fake_no_home:
                self.logger.warning(f"Testing mode: pretending VNC password file {vnc_passwd_file} does not exist")
                passwd_exists = False
            else:
                try:
                    self.logger.info(f"Checking for VNC password file: {vnc_passwd_file}")
                    test_cmd = ['test', '-f', vnc_passwd_file]
                    self._run_command(test_cmd, authenticated_user)
                    passwd_exists = True
                    self.logger.info(f"VNC password file exists: {vnc_passwd_file}")
                except Exception as e:
                    self.logger.warning(f"VNC password file check failed: {str(e)}")
                    passwd_exists = False

            if not passwd_exists:
                hostname = server_hostname if server_hostname else "<hostname>"
                error_msg = (
                    f"<strong>VNC Password File Not Found</strong><br><br>"
                    f"Your VNC password file does not exist yet on the system.<br><br>"
                    f"<strong>Why this happens:</strong><br>"
                    f"VNC requires a password file to be created before you can start a VNC session.<br><br>"
                    f"<strong>How to fix this:</strong><br>"
                    f"1. Open a terminal or SSH client<br>"
                    f"2. SSH to the machine:<br><br>"
                    f"<code style='background-color: #f0f0f0; padding: 8px 12px; border-radius: 4px; display: inline-block; font-family: monospace; font-size: 14px;'>"
                    f"ssh {user}@{hostname}"
                    f"</code><br><br>"
                    f"3. Once logged in, run the following commands to create your VNC password:<br><br>"
                    f"<code style='background-color: #f0f0f0; padding: 8px 12px; border-radius: 4px; display: inline-block; font-family: monospace; font-size: 14px;'>"
                    f"mkdir -p ~/.vnc<br>"
                    f"/usr/bin/vncpasswd ~/.vnc/passwd"
                    f"</code><br><br>"
                    f"4. Follow the prompts to enter and confirm your VNC password<br>"
                    f"5. Return here and submit your VNC job again"
                )
                self.logger.error(error_msg)
                raise SLURMError(error_msg)

            job_name = 'myvnc_vncserver'
            num_cores = int(slurm_config.get('cpus_per_task', slurm_config.get('num_cores', 2)))
            memory_gb = int(slurm_config.get('memory_gb', 16))

            display_name = vnc_config.get('name', 'MyVNC Session')
            resolution = vnc_config.get('resolution', '1024x768')
            color_depth = int(vnc_config.get('color_depth', 24))

            partition = slurm_config.get('partition', slurm_config.get('queue', 'interactive'))

            # Build sbatch command
            sbatch_cmd = [
                'sbatch',
                '--partition', partition,
                '--cpus-per-task', str(num_cores),
                '--mem', f'{memory_gb}G',
                '--job-name', job_name,
                '--ntasks', '1',
            ]

            # Add constraint for OS selection (but NOT when using a container)
            container_path = slurm_config.get('container', '')
            using_container = container_path and container_path.strip()

            if using_container:
                original_container_path = container_path
                container_path = os.path.realpath(container_path)
                if original_container_path != container_path:
                    self.logger.info(f"Resolved container path from '{original_container_path}' to '{container_path}'")

            os_constraint = slurm_config.get('constraint', slurm_config.get('os_select', ''))

            arch_constraint = slurm_config.get('arch_constraint', slurm_config.get('arch_select', ''))
            constraints = []
            if not using_container and os_constraint and os_constraint != "any":
                constraints.append(os_constraint)
            if arch_constraint and arch_constraint != "any":
                constraints.append(arch_constraint)

            if constraints:
                sbatch_cmd.extend(['--constraint', '&'.join(constraints)])
                self.logger.info(f"Adding SLURM constraints: {constraints}")

            # Add time limit if specified
            time_limit = slurm_config.get('time_limit', '')
            if time_limit and time_limit.strip():
                sbatch_cmd.extend(['--time', time_limit])

            # Add node/host filter if specified
            host_filter = slurm_config.get('host_filter', slurm_config.get('nodelist', ''))
            if host_filter and host_filter.strip():
                sbatch_cmd.extend(['--nodelist', host_filter])

            # Set working directory
            sbatch_cmd.extend(['--chdir', user_home])
            self.logger.info(f"Setting SLURM working directory: {user_home}")

            # Set output/error log paths
            vnc_log_dir = os.path.join(user_home, '.vnc')
            try:
                os.makedirs(vnc_log_dir, mode=0o755, exist_ok=True)
                self.logger.info(f"Ensured .vnc directory exists: {vnc_log_dir}")
            except Exception as e:
                self.logger.warning(f"Could not create .vnc directory {vnc_log_dir}: {e}")

            stdout_log_path = f'{user_home}/.vnc/myvnc.%j.slurm_stdout.log'
            stderr_log_path = f'{user_home}/.vnc/myvnc.%j.slurm_stderr.log'
            sbatch_cmd.extend(['--output', stdout_log_path])
            sbatch_cmd.extend(['--error', stderr_log_path])

            self.logger.info(f"Setting SLURM stdout log file: {stdout_log_path}")
            self.logger.info(f"Setting SLURM stderr log file: {stderr_log_path}")

            # Build VNC server command
            vncserver_path = vnc_config.get('vncserver_path', '/usr/bin/vncserver')
            vncserver_wrapper_path = vnc_config.get('vncserver_wrapper_path')
            vncserver_executable = vncserver_wrapper_path or vncserver_path
            self.logger.info(f"Using VNC server executable: {vncserver_executable}")

            vncserver_cmd = [
                vncserver_executable,
                '-geometry', resolution,
                '-depth', str(color_depth),
                '-localhost', 'no',
            ]

            if display_name and display_name.strip():
                safe_display_name = display_name.replace(' ', '_')
                vncserver_cmd.extend(['-name', safe_display_name])

            vncserver_cmd.extend(['-PasswordFile', vnc_passwd_file])
            self.logger.info(f"Using VNC password file: {vnc_passwd_file}")

            # Get environment variables
            window_manager = vnc_config.get('window_manager')
            user_uid = None
            xdg_runtime_dir = None
            dbus_session_bus_address = None

            if authenticated_user:
                try:
                    uid_result = subprocess.run(['id', '-u', authenticated_user],
                                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    user_uid = uid_result.stdout.decode('utf-8').strip()
                    xdg_runtime_dir = f"/run/user/{user_uid}"
                    dbus_session_bus_address = f"unix:path={xdg_runtime_dir}/bus"
                    self.logger.info(f"Calculated environment for user {authenticated_user} (UID={user_uid})")
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Failed to get UID for user {authenticated_user}: {e.stderr.decode('utf-8')}")
                except Exception as e:
                    self.logger.error(f"Error getting UID for user {authenticated_user}: {str(e)}")

            # Add xstartup parameter if configured
            use_custom_xstartup = vnc_config.get('use_custom_xstartup', False)
            xstartup_path = vnc_config.get('xstartup_path', '')
            if use_custom_xstartup and xstartup_path and xstartup_path.strip():
                self.logger.info(f"Using custom xstartup script: {xstartup_path}")
                vncserver_cmd.extend(['-xstartup', xstartup_path])

            # Build export statements for environment variables in the batch script
            env_exports = []
            if window_manager and use_custom_xstartup:
                env_exports.append(f'export WINDOW_MANAGER="{window_manager}"')
            if xdg_runtime_dir:
                env_exports.append(f'export XDG_RUNTIME_DIR="{xdg_runtime_dir}"')
            if dbus_session_bus_address:
                env_exports.append(f'export DBUS_SESSION_BUS_ADDRESS="{dbus_session_bus_address}"')

            # Build the batch script
            vncserver_cmd_str = ' '.join(str(arg) for arg in vncserver_cmd)
            display_file = f'{user_home}/.vnc/myvnc_slurm_display.$SLURM_JOB_ID'

            if using_container:
                self.logger.info(f"Wrapping vncserver command with singularity container: {container_path}")
                container_cmd_parts = ['singularity', 'exec', '--cleanenv']

                if authenticated_user:
                    container_cmd_parts.extend(['--env', f'USER={authenticated_user}'])

                if use_custom_xstartup and xstartup_path:
                    container_cmd_parts.extend(['--env', f'WINDOW_MANAGER={window_manager}'])
                    if xdg_runtime_dir:
                        container_cmd_parts.extend(['--env', f'XDG_RUNTIME_DIR={xdg_runtime_dir}'])
                    if dbus_session_bus_address:
                        container_cmd_parts.extend(['--env', f'DBUS_SESSION_BUS_ADDRESS={dbus_session_bus_address}'])

                container_cmd_parts.extend(['--env', f'SLURM_JOB_ID=$SLURM_JOB_ID'])

                # Add cgroup resource limits
                container_cmd_parts.extend(['--cpus', str(num_cores)])
                container_cmd_parts.extend(['--memory-reservation', f'{memory_gb}G'])
                container_cmd_parts.extend(['--memory', f'{memory_gb + 2}G'])
                container_cmd_parts.extend(['--memory-swap', f'{memory_gb * 2}G'])

                # Get bind paths from configuration
                bindpaths_name = slurm_config.get('bindpaths', '')
                if bindpaths_name:
                    bindpaths = self.config_manager.get_bindpaths_by_name(bindpaths_name)
                    if bindpaths:
                        for path in bindpaths:
                            path = path.strip()
                            if path and os.path.exists(path):
                                container_cmd_parts.extend(['--bind', f'{path}:{path}'])

                container_cmd_parts.append(container_path)
                inner_cmd = f'{vncserver_cmd_str} && sleep infinity'
                container_cmd_parts.extend(['/usr/bin/bash', '-c', inner_cmd])
                exec_command = ' '.join(shlex.quote(p) if ' ' in p else p for p in container_cmd_parts)
            else:
                exec_command = f'{vncserver_cmd_str} && sleep infinity'

            env_exports_str = '\n'.join(env_exports)
            script_content = f"""#!/bin/bash
#SBATCH --partition={partition}
#SBATCH --cpus-per-task={num_cores}
#SBATCH --mem={memory_gb}G
#SBATCH --job-name={job_name}
#SBATCH --ntasks=1
#SBATCH --output={stdout_log_path}
#SBATCH --error={stderr_log_path}
#SBATCH --chdir={user_home}
{f'#SBATCH --constraint={chr(38).join(constraints)}' if constraints else ''}
{f'#SBATCH --time={time_limit}' if time_limit and time_limit.strip() else ''}
{f'#SBATCH --nodelist={host_filter}' if host_filter and host_filter.strip() else ''}

# Enable user lingering for systemd user sessions
/usr/bin/loginctl enable-linger {user} 2>/dev/null || true

# Set environment variables
{env_exports_str}

# Write the SLURM job ID for reference
echo "$SLURM_JOB_ID" > {user_home}/.vnc/myvnc_slurm_jobid.$$

# Execute the VNC server
{exec_command}
"""
            # Write batch script to user's .vnc directory
            script_path = os.path.join(vnc_log_dir, f'myvnc_vnc_submit.sh')
            self._write_batch_script(script_content, script_path)

            # Use sbatch with --parsable to get just the job ID
            sbatch_cmd = ['sbatch', '--parsable', script_path]

            cmd_str = ' '.join(str(arg) for arg in sbatch_cmd)
            cmd_entry = {
                'command': cmd_str,
                'stdout': '',
                'stderr': '',
                'success': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.command_history.append(cmd_entry)

            try:
                self.logger.info(f"Submitting VNC job with sbatch")
                stdout = self._run_command(sbatch_cmd, authenticated_user)

                job_id = stdout.strip().split(';')[0].strip()
                if not job_id.isdigit():
                    job_id_match = re.search(r'(\d+)', stdout)
                    job_id = job_id_match.group(1) if job_id_match else 'unknown'

                self.logger.info(f"Job submitted successfully, ID: {job_id}")
                return job_id

            except SLURMError as e:
                self.logger.error(f"Job submission failed: {str(e)}")
                cmd_entry['stderr'] += f"\nException: {str(e)}"
                raise e
            except Exception as e:
                error_msg = f"Job submission error: {str(e)}"
                self.logger.error(error_msg)
                cmd_entry['stderr'] += f"\nException: {str(e)}"
                raise Exception(error_msg)

        except Exception as e:
            if 'cmd_entry' in locals():
                cmd_entry['stderr'] += f"\nException: {str(e)}"
            else:
                self.command_history.append({
                    'command': 'Error preparing VNC job submission',
                    'stdout': '',
                    'stderr': str(e),
                    'success': False,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            raise

    def submit_tmux_job(self, session_config: Dict, slurm_config: Dict, authenticated_user: str = None, server_hostname: str = None) -> str:
        """Submit a tmux job using sbatch

        Args:
            session_config: Session configuration (name, site, etc.)
            slurm_config: SLURM configuration (partition, cpus, memory, etc.)
            authenticated_user: Optional authenticated username to run command as
            server_hostname: Server hostname for error messages

        Returns:
            Job ID if successful

        Raises:
            SLURMError if submission fails
        """
        try:
            user = authenticated_user if authenticated_user else os.environ.get('USER', '')
            user_home = os.path.expanduser(f'~{user}')

            job_name = 'myvnc_tmux'
            num_cores = int(slurm_config.get('cpus_per_task', slurm_config.get('num_cores', 2)))
            memory_gb = int(slurm_config.get('memory_gb', 16))

            session_name = session_config.get('name', 'myvnc_tmux_session')
            safe_session_name = session_name.replace(' ', '_')

            partition = slurm_config.get('partition', slurm_config.get('queue', 'interactive'))

            container_path = slurm_config.get('container', '')
            using_container = container_path and container_path.strip()

            if using_container:
                original_container_path = container_path
                container_path = os.path.realpath(container_path)
                if original_container_path != container_path:
                    self.logger.info(f"Resolved container path from '{original_container_path}' to '{container_path}'")

            os_constraint = slurm_config.get('constraint', slurm_config.get('os_select', ''))
            arch_constraint = slurm_config.get('arch_constraint', slurm_config.get('arch_select', ''))
            constraints = []
            if not using_container and os_constraint and os_constraint != "any":
                constraints.append(os_constraint)
            if arch_constraint and arch_constraint != "any":
                constraints.append(arch_constraint)

            time_limit = slurm_config.get('time_limit', '')
            host_filter = slurm_config.get('host_filter', slurm_config.get('nodelist', ''))

            # Set output/error log paths
            tmux_log_dir = os.path.join(user_home, '.tmux')
            try:
                os.makedirs(tmux_log_dir, mode=0o755, exist_ok=True)
                self.logger.info(f"Ensured .tmux directory exists: {tmux_log_dir}")
            except Exception as e:
                self.logger.warning(f"Could not create .tmux directory {tmux_log_dir}: {e}")

            stdout_log_path = f'{user_home}/.tmux/myvnc.%j.slurm_stdout.log'
            stderr_log_path = f'{user_home}/.tmux/myvnc.%j.slurm_stderr.log'

            # Get environment variables for container
            user_uid = None
            xdg_runtime_dir = None
            dbus_session_bus_address = None

            if using_container and authenticated_user:
                try:
                    uid_result = subprocess.run(['id', '-u', authenticated_user],
                                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    user_uid = uid_result.stdout.decode('utf-8').strip()
                    xdg_runtime_dir = f'/run/user/{user_uid}'
                    dbus_session_bus_address = f'unix:path=/run/user/{user_uid}/bus'
                    self.logger.info(f"Calculated environment for user {authenticated_user} (UID={user_uid})")
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Failed to get UID for user {authenticated_user}: {e.stderr.decode('utf-8')}")
                except Exception as e:
                    self.logger.error(f"Error getting UID for user {authenticated_user}: {str(e)}")

            # Build tmux command
            tmux_cmd = f'/usr/bin/tmux new-session -d -s {safe_session_name} && while /usr/bin/tmux has-session -t {safe_session_name} 2>/dev/null; do sleep 5; done'

            if using_container:
                self.logger.info(f"Wrapping tmux command with singularity container: {container_path}")
                container_cmd_parts = ['singularity', 'exec', '--cleanenv']

                if authenticated_user:
                    container_cmd_parts.extend(['--env', f'USER={authenticated_user}'])
                if xdg_runtime_dir:
                    container_cmd_parts.extend(['--env', f'XDG_RUNTIME_DIR={xdg_runtime_dir}'])
                if dbus_session_bus_address:
                    container_cmd_parts.extend(['--env', f'DBUS_SESSION_BUS_ADDRESS={dbus_session_bus_address}'])

                container_cmd_parts.extend(['--cpus', str(num_cores)])
                container_cmd_parts.extend(['--memory-reservation', f'{memory_gb}G'])
                container_cmd_parts.extend(['--memory', f'{memory_gb + 2}G'])
                container_cmd_parts.extend(['--memory-swap', f'{memory_gb * 2}G'])

                bindpaths_name = slurm_config.get('bindpaths', '')
                if bindpaths_name:
                    bindpaths = self.config_manager.get_bindpaths_by_name(bindpaths_name)
                    if bindpaths:
                        for path in bindpaths:
                            path = path.strip()
                            if path and os.path.exists(path):
                                container_cmd_parts.extend(['--bind', f'{path}:{path}'])

                container_cmd_parts.append(container_path)
                container_cmd_parts.extend(['/usr/bin/bash', '-c', tmux_cmd])
                exec_command = ' '.join(shlex.quote(p) if ' ' in p else p for p in container_cmd_parts)
            else:
                exec_command = tmux_cmd

            script_content = f"""#!/bin/bash
#SBATCH --partition={partition}
#SBATCH --cpus-per-task={num_cores}
#SBATCH --mem={memory_gb}G
#SBATCH --job-name={job_name}
#SBATCH --ntasks=1
#SBATCH --output={stdout_log_path}
#SBATCH --error={stderr_log_path}
#SBATCH --chdir={user_home}
{f'#SBATCH --constraint={chr(38).join(constraints)}' if constraints else ''}
{f'#SBATCH --time={time_limit}' if time_limit and time_limit.strip() else ''}
{f'#SBATCH --nodelist={host_filter}' if host_filter and host_filter.strip() else ''}

# Enable user lingering for systemd user sessions
/usr/bin/loginctl enable-linger {user} 2>/dev/null || true

# Execute tmux session
{exec_command}
"""
            script_path = os.path.join(tmux_log_dir, f'myvnc_tmux_submit.sh')
            self._write_batch_script(script_content, script_path)

            sbatch_cmd = ['sbatch', '--parsable', script_path]

            cmd_str = ' '.join(str(arg) for arg in sbatch_cmd)
            cmd_entry = {
                'command': cmd_str,
                'stdout': '',
                'stderr': '',
                'success': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.command_history.append(cmd_entry)

            try:
                self.logger.info(f"Submitting tmux job with sbatch")
                stdout = self._run_command(sbatch_cmd, authenticated_user)

                job_id = stdout.strip().split(';')[0].strip()
                if not job_id.isdigit():
                    job_id_match = re.search(r'(\d+)', stdout)
                    job_id = job_id_match.group(1) if job_id_match else 'unknown'

                self.logger.info(f"tmux job submitted successfully, ID: {job_id}")
                return job_id

            except SLURMError as e:
                self.logger.error(f"tmux job submission failed: {str(e)}")
                cmd_entry['stderr'] += f"\nException: {str(e)}"
                raise e
            except Exception as e:
                error_msg = f"tmux job submission error: {str(e)}"
                self.logger.error(error_msg)
                cmd_entry['stderr'] += f"\nException: {str(e)}"
                raise Exception(error_msg)

        except Exception as e:
            if 'cmd_entry' in locals():
                cmd_entry['stderr'] += f"\nException: {str(e)}"
            else:
                self.command_history.append({
                    'command': 'Error preparing tmux job submission',
                    'stdout': '',
                    'stderr': str(e),
                    'success': False,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            raise

    def get_job_owner(self, job_id: str, authenticated_user: str = None) -> Optional[str]:
        """
        Get the owner (user) of a specific job ID

        Args:
            job_id: Job ID to query
            authenticated_user: Optional authenticated username to run command as

        Returns:
            Username of the job owner, or None if not found
        """
        try:
            cmd = ['squeue', '--job', job_id, '--noheader', '--format', '%u']
            output = self._run_command(cmd, authenticated_user)

            if output and output.strip():
                job_owner = output.strip()
                self.logger.info(f"Job {job_id} is owned by user: {job_owner}")
                return job_owner
            else:
                self.logger.warning(f"Could not determine owner for job {job_id}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting job owner for {job_id}: {str(e)}")
            return None

    def kill_vnc_job(self, job_id: str, authenticated_user: str = None, reason: str = None) -> bool:
        """
        Kill a VNC/tmux job

        Args:
            job_id: Job ID to kill
            authenticated_user: Optional authenticated username to run command as
            reason: Optional reason for killing the job

        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Killing job: {job_id}")

        try:
            cmd = ['scancel']

            if reason:
                self.logger.info(f"Kill reason: {reason}")

            cmd.append(job_id)

            result = self._run_command(cmd, authenticated_user)
            self.logger.info(f"Kill result: Job {job_id} cancelled successfully: {result}")
            return True
        except Exception as e:
            self.logger.error(f"Kill failed: Failed to cancel job {job_id}: {str(e)}")
            return False

    def get_active_vnc_jobs(self, authenticated_user: str = None, all_users: bool = False) -> List[Dict]:
        """
        Get active VNC/tmux jobs for the current user with job name matching myvnc_*

        Args:
            authenticated_user: Optional authenticated username to run command as
            all_users: Whether to include jobs from all users

        Returns:
            List of jobs as dictionaries
        """
        jobs = []

        try:
            if all_users:
                user = None
            else:
                user = authenticated_user if authenticated_user else os.environ.get('USER', '')

            # squeue format: JobID, State, User, Partition, NodeList, TimeUsed, NumCPUs, MinMemory, Name, Command
            format_str = '%i|%t|%u|%P|%N|%M|%C|%m|%j|%o'
            cmd = [
                'squeue',
                '--noheader',
                '--format', format_str,
                '--name', 'myvnc_vncserver,myvnc_tmux',
            ]

            if user:
                cmd.extend(['--user', user])

            base_cmd = ' '.join(cmd)
            cmd_entry = {
                'command': base_cmd,
                'stdout': '',
                'stderr': '',
                'success': False,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.command_history.append(cmd_entry)

            try:
                output_str = self._run_command(cmd, authenticated_user)
                cmd_entry['stdout'] = output_str
                cmd_entry['success'] = True
            except SLURMError as e:
                error_str = str(e)
                cmd_entry['stderr'] = error_str
                # No jobs is not a real error
                if 'No jobs' in error_str or 'slurm_load_jobs' in error_str:
                    return []
                self.logger.error(f"Error executing squeue: {error_str}")
                return []

            output_lines = output_str.strip().split('\n')
            for line in output_lines:
                try:
                    if not line.strip():
                        continue

                    parts = line.split('|')
                    if len(parts) < 9:
                        self.logger.warning(f"Incomplete squeue output line: {line}")
                        continue

                    job_id = parts[0].strip()
                    state_code = parts[1].strip()
                    job_user = parts[2].strip()
                    partition = parts[3].strip()
                    nodelist = parts[4].strip()
                    time_used = parts[5].strip()
                    num_cpus = parts[6].strip()
                    min_memory = parts[7].strip()
                    job_name = parts[8].strip()
                    command = parts[9].strip() if len(parts) > 9 else ""

                    # Map SLURM state codes to display states
                    state_map = {
                        'PD': 'PEND',
                        'R': 'RUN',
                        'CG': 'RUN',
                        'CF': 'PEND',
                        'S': 'SUSP',
                        'ST': 'SUSP',
                        'CA': 'EXIT',
                        'CD': 'DONE',
                        'F': 'EXIT',
                        'TO': 'EXIT',
                        'NF': 'EXIT',
                        'SE': 'EXIT',
                    }
                    status = state_map.get(state_code, state_code)

                    self.logger.info(f"Job {job_id}: state={state_code}({status}), user={job_user}, node={nodelist}")

                    # Parse time_used (format: D-HH:MM:SS or HH:MM:SS or MM:SS)
                    run_time_seconds = 0
                    runtime_display = time_used
                    try:
                        if '-' in time_used:
                            days_part, time_part = time_used.split('-', 1)
                            days = int(days_part)
                            time_parts = time_part.split(':')
                        else:
                            days = 0
                            time_parts = time_used.split(':')

                        if len(time_parts) == 3:
                            hours, minutes, seconds = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
                        elif len(time_parts) == 2:
                            hours, minutes, seconds = 0, int(time_parts[0]), int(time_parts[1])
                        else:
                            hours, minutes, seconds = 0, 0, 0

                        total_hours = days * 24 + hours
                        run_time_seconds = total_hours * 3600 + minutes * 60 + seconds

                        if total_hours > 24:
                            d = total_hours // 24
                            h = total_hours % 24
                            runtime_display = f"{d}d {h}h {minutes}m"
                        else:
                            runtime_display = f"{total_hours}h {minutes}m"
                    except Exception:
                        runtime_display = time_used

                    # Parse resources
                    num_cores_val = None
                    memory_gb_val = None
                    resources_unknown = False

                    if status == "PEND":
                        resources_unknown = True
                    else:
                        try:
                            num_cores_val = int(num_cpus)
                        except (ValueError, TypeError):
                            num_cores_val = None

                        # Parse memory (could be like "16G", "16384M", "16384")
                        try:
                            if min_memory:
                                mem_str = min_memory.strip()
                                if mem_str.endswith('G'):
                                    memory_gb_val = float(mem_str[:-1])
                                elif mem_str.endswith('M'):
                                    memory_gb_val = float(mem_str[:-1]) / 1024
                                elif mem_str.endswith('T'):
                                    memory_gb_val = float(mem_str[:-1]) * 1024
                                elif mem_str.endswith('K'):
                                    memory_gb_val = float(mem_str[:-1]) / (1024 * 1024)
                                else:
                                    memory_gb_val = float(mem_str) / 1024  # Assume MB
                        except (ValueError, TypeError):
                            memory_gb_val = None

                    # Determine session type
                    session_type = "Unknown"
                    if job_name == "myvnc_vncserver":
                        session_type = "VNC"
                    elif job_name == "myvnc_tmux":
                        session_type = "tmux"

                    # Default display name
                    display_name = "VNC Session" if session_type == "VNC" else "tmux Session"

                    if session_type == "tmux" and command:
                        name_match = re.search(r'-s\s+([^\s&"\']+)', command)
                        if name_match:
                            display_name = name_match.group(1)
                    elif session_type == "VNC" and command:
                        name_match = re.search(r'-name\s+([^\s"]+|"([^"]+)")', command)
                        if name_match:
                            display_name = name_match.group(2) if name_match.group(2) else name_match.group(1)

                    # Extract OS info from constraints or command
                    os_name = 'N/A'
                    container_used = False
                    if command and '.sif' in command:
                        try:
                            slurm_config_data = self.config_manager.slurm_config
                            os_options = slurm_config_data.get('os_options', [])

                            for os_option in os_options:
                                cont_path = os_option.get('container', '')
                                if cont_path:
                                    cont_path = os.path.realpath(cont_path)
                                if cont_path and cont_path in command:
                                    name = os_option.get('name', '')
                                    os_name = name
                                    container_used = True
                                    break

                            if not container_used:
                                sif_match = re.search(r'([^/\s]+\.sif)', command)
                                if sif_match:
                                    os_name = f"Container ({sif_match.group(1)})"
                                    container_used = True
                        except Exception as e:
                            self.logger.warning(f"Error extracting container info: {str(e)}")

                    # Get host info
                    host = nodelist if nodelist and nodelist not in ('', '(None)') else None
                    exec_host = host

                    if host:
                        if ',' in host:
                            host = host.split(',')[0]
                        if '.' in host:
                            host = host.split('.')[0]

                    # For pending tmux jobs, clear host
                    if session_type == "tmux" and status == "PEND":
                        host = None
                        exec_host = None

                    # Get VNC display for running VNC jobs
                    display = None
                    port = None
                    if session_type == "VNC" and status == "RUN" and user:
                        user_home_for_display = os.path.expanduser(f'~{job_user}')
                        display_str = self._get_display_from_file(job_id, user_home_for_display)
                        if display_str:
                            display = int(display_str)
                            port = display

                    job = {
                        'job_id': job_id,
                        'name': display_name,
                        'status': status,
                        'queue': partition,
                        'from_host': nodelist,
                        'exec_host': exec_host,
                        'host': host,
                        'user': job_user,
                        'runtime': runtime_display,
                        'runtime_display': runtime_display,
                        'run_time_seconds': run_time_seconds,
                        'resource_req': f'cpus={num_cpus} mem={min_memory}',
                        'os': os_name,
                        'session_type': session_type,
                    }

                    if resources_unknown:
                        job['num_cores'] = None
                        job['cores'] = None
                        job['mem_gb'] = None
                        job['memory_gb'] = None
                        job['resources_unknown'] = True
                    else:
                        job['num_cores'] = num_cores_val
                        job['cores'] = num_cores_val
                        job['mem_gb'] = memory_gb_val
                        job['memory_gb'] = memory_gb_val

                    if display is not None:
                        job['display'] = display
                    if port is not None:
                        job['port'] = port

                    jobs.append(job)

                except Exception as e:
                    self.logger.error(f"Error processing SLURM job: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error retrieving SLURM jobs: {str(e)}")

        return jobs

    def get_vnc_connection_details(self, job_id: str, authenticated_user: str = None) -> Optional[Dict]:
        """
        Get connection details for a VNC job

        Args:
            job_id: Job ID
            authenticated_user: Optional authenticated username to run command as

        Returns:
            Dictionary with connection details or None if not found
        """
        try:
            self.logger.info(f"Getting connection details for SLURM job {job_id}")

            format_str = '%t|%u|%N|%j|%o'
            cmd = ['squeue', '--job', job_id, '--noheader', '--format', format_str]

            output = self._run_command(cmd, authenticated_user)

            if not output or not output.strip():
                self.logger.warning(f"No output from squeue for job {job_id}")
                return None

            parts = output.strip().split('|')
            if len(parts) < 5:
                self.logger.warning(f"Incomplete squeue output for job {job_id}")
                return None

            state_code = parts[0].strip()
            user = parts[1].strip()
            nodelist = parts[2].strip()
            job_name = parts[3].strip()
            command = parts[4].strip()

            state_map = {
                'PD': 'PEND', 'R': 'RUN', 'CG': 'RUN', 'CF': 'PEND',
                'S': 'SUSP', 'ST': 'SUSP', 'CA': 'EXIT', 'CD': 'DONE',
                'F': 'EXIT', 'TO': 'EXIT',
            }
            status = state_map.get(state_code, state_code)

            host = nodelist if nodelist and nodelist not in ('', '(None)') else None
            if host:
                if ',' in host:
                    host = host.split(',')[0]
                if '.' in host:
                    host = host.split('.')[0]

            if not host:
                self.logger.warning(f"Could not determine execution host for job {job_id}")
                return None

            # Get display from file
            display_num = None
            if status == "RUN" and user:
                user_home = os.path.expanduser(f'~{user}')
                display_num = self._get_display_from_file(job_id, user_home)

            # Fallback: extract from command
            if not display_num and command and status == "RUN":
                display_match = re.search(r':(\d+)', command)
                if display_match:
                    display_num = display_match.group(1)

            port = None
            if display_num:
                port = int(display_num)

            return {
                'job_id': job_id,
                'host': host,
                'display': display_num,
                'port': port,
                'user': user,
                'status': status
            }

        except Exception as e:
            self.logger.error(f"Failed to get VNC connection details: {str(e)}")
            return None
