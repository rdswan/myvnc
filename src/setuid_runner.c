/*
 * SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
 * SPDX-License-Identifier: Apache-2.0
 *
 * Setuid binary for executing LSF commands as authenticated users
 * 
 * This binary is designed to be run as setuid root to allow the myvnc server
 * (running as non-root) to execute LSF commands as authenticated users.
 *
 * Usage: setuid_runner <username> <command> [args...]
 */

#define _GNU_SOURCE  /* For clearenv() and setenv() */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pwd.h>
#include <grp.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <errno.h>
#include <limits.h>
#include <ctype.h>

#define MAX_ARGS 256
#define MAX_USERNAME_LEN 32
#define MAX_PATH_LEN 4096

/* List of allowed LSF commands - security whitelist */
static const char* allowed_commands[] = {
    "bjobs", "bsub", "bkill"
};
static const int num_allowed_commands = sizeof(allowed_commands) / sizeof(allowed_commands[0]);

/* Function to validate username - basic null check only */
int is_valid_username(const char* username) {
    return (username != NULL && strlen(username) > 0);
}

/* Function to check if command is in the allowed list */
int is_allowed_command(const char* command) {
    if (!command) return 0;
    
    /* Extract just the command name from full path if present */
    const char* cmd_name = strrchr(command, '/');
    if (cmd_name) {
        cmd_name++; /* Skip the '/' */
    } else {
        cmd_name = command;
    }
    
    for (int i = 0; i < num_allowed_commands; i++) {
        if (strcmp(cmd_name, allowed_commands[i]) == 0) {
            return 1;
        }
    }
    return 0;
}

/* Function to safely set environment for the target user */
int setup_user_environment(const char* username, struct passwd* pwd) {
    /* Clear environment and set basic variables */
    if (clearenv() != 0) {
        fprintf(stderr, "Failed to clear environment\n");
        return -1;
    }
    
    /* Set essential environment variables */
    if (setenv("USER", username, 1) != 0 ||
        setenv("LOGNAME", username, 1) != 0 ||
        setenv("HOME", pwd->pw_dir, 1) != 0 ||
        setenv("SHELL", pwd->pw_shell, 1) != 0) {
        fprintf(stderr, "Failed to set environment variables\n");
        return -1;
    }
    
    /* Preserve PATH for LSF commands */
    const char* original_path = getenv("PATH");
    if (original_path) {
        if (setenv("PATH", original_path, 1) != 0) {
            fprintf(stderr, "Failed to set PATH\n");
            return -1;
        }
    } else {
        /* Set a default PATH that includes common LSF locations */
        if (setenv("PATH", "/usr/local/lsf/bin:/usr/bin:/bin:/usr/local/bin", 1) != 0) {
            fprintf(stderr, "Failed to set default PATH\n");
            return -1;
        }
    }
    
    return 0;
}

int main(int argc, char* argv[]) {
    struct passwd* pwd;
    pid_t pid;
    int status;
    
    /* Validate arguments */
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <username> <command> [args...]\n", argv[0]);
        return 1;
    }
    
    const char* username = argv[1];
    const char* command = argv[2];
    
    /* Basic username check */
    if (!is_valid_username(username)) {
        fprintf(stderr, "Username cannot be empty\n");
        return 1;
    }
    
    /* Validate command is in allowed list */
    if (!is_allowed_command(command)) {
        fprintf(stderr, "Command not allowed: %s\n", command);
        return 1;
    }
    
    /* Get user information */
    pwd = getpwnam(username);
    if (!pwd) {
        fprintf(stderr, "User not found: %s\n", username);
        return 1;
    }
    
    /* Fork to create child process */
    pid = fork();
    if (pid == -1) {
        perror("fork failed");
        return 1;
    }
    
    if (pid == 0) {
        /* Child process - change user and execute command */
        
        /* Set supplementary groups */
        if (initgroups(username, pwd->pw_gid) == -1) {
            perror("initgroups failed");
            exit(1);
        }
        
        /* Set group ID */
        if (setgid(pwd->pw_gid) == -1) {
            perror("setgid failed");
            exit(1);
        }
        
        /* Set user ID */
        if (setuid(pwd->pw_uid) == -1) {
            perror("setuid failed");
            exit(1);
        }
        
        /* Verify we're running as the correct user */
        if (getuid() != pwd->pw_uid || geteuid() != pwd->pw_uid) {
            fprintf(stderr, "Failed to change to user %s\n", username);
            exit(1);
        }
        
        /* Setup environment */
        if (setup_user_environment(username, pwd) != 0) {
            exit(1);
        }
        
        /* Change to user's home directory */
        if (chdir(pwd->pw_dir) == -1) {
            /* Not fatal - just warn and continue */
            fprintf(stderr, "Warning: Could not change to home directory %s\n", pwd->pw_dir);
        }
        
        /* Execute the command */
        /* argv[2] onwards contains the command and its arguments */
        char** exec_args = &argv[2];
        execvp(command, exec_args);
        
        /* If we get here, execvp failed */
        perror("execvp failed");
        exit(1);
    } else {
        /* Parent process - wait for child */
        if (waitpid(pid, &status, 0) == -1) {
            perror("waitpid failed");
            return 1;
        }
        
        /* Return the exit status of the child process */
        if (WIFEXITED(status)) {
            return WEXITSTATUS(status);
        } else if (WIFSIGNALED(status)) {
            /* Child was killed by signal */
            return 128 + WTERMSIG(status);
        } else {
            /* Unexpected termination */
            return 1;
        }
    }
}
