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
#define MAX_ENV_VARS 100
#define MAX_ENV_VAR_LEN 1024

/* List of allowed LSF commands - security whitelist */
static const char* allowed_commands[] = {
    "bjobs", "bsub", "bkill", "bqueues", "bhosts", "lsload", "lshosts", "busers"
};
static const int num_allowed_commands = sizeof(allowed_commands) / sizeof(allowed_commands[0]);

/* List of LSF environment variables to preserve */
static const char* lsf_env_vars[] = {
    "LSF_BINDIR", "LSF_LIBDIR", "LSF_SERVERDIR", "LSF_ENVDIR", 
    "LSF_CONFDIR", "LSF_INCLUDEDIR", "LSF_MISC", "LSF_TOP",
    "LSF_VERSION", "LSF_LIM_PORT", "LSF_RES_PORT", "LSF_MBD_PORT",
    "LSF_SBD_PORT", "LSF_AUTH", "LSF_USE_HOSTEQUIV", "LSF_ROOT_REX",
    "LSF_REXD_CONNECT_TIMEOUT", "LSF_DEBUG_LIM", "LSF_DEBUG_RES",
    "LSF_DEBUG_SBD", "LSF_TIME_FORMAT", "LSF_TMPDIR", "LSF_LOGDIR",
    "LSF_LOG_MASK", "LSF_DISABLE_LSRUN", "LSF_RSH", "LSF_RCP",
    "LSF_GETPWNAM_RETRY", "LSF_GETPWNAM_TIMEOUT", "LSF_UNIT_FOR_LIMITS",
    "LSF_HPC_EXTENSIONS", "LSF_STRIP_DOMAIN", "LSF_MASTER_LIST",
    "LSF_SERVER_HOSTS", "LSB_CONFDIR", "LSB_SHAREDIR", "LSB_DEFAULTPROJECT",
    "LSB_DEFAULTQUEUE", "LSB_HOSTS", "LSB_MCPU_HOSTS", "LSB_SHAREDIR",
    "LSB_SUBK_SHOW_EXEC_HOST", "LSB_NTASKS", "LSB_NTASKS_PARALLEL",
    "LSB_QUEUE", "LSB_BATCH", "LSB_JOBID", "LSB_JOBINDEX", "LSB_HOSTS",
    "LSB_MCPU_HOSTS", "LSB_DJOB_HOSTFILE", "LSB_DJOB_RANKFILE",
    "LSB_DJOB_NUMPROC", "LSB_EFFECTIVE_RSRCREQ", "LSB_SUB_HOST",
    "LSB_EXEC_CLUSTER", "LSB_SUB_CLUSTER", "LSB_INTERACTIVE",
    "LSB_JOBFILENAME", "LSB_OUTPUTFILE", "LSB_ERRORFILE", "LSB_INPUTFILE",
    "LSB_CHKFILENAME", "LSB_RESTART", "LSB_RESTART_CMD", "LSB_CHKPNT_METHOD",
    "LSB_CHKPNT_DIR", "LSB_CHKPNT_PERIOD", "LSB_JOBPGIDS", "LSB_JOBPIDS",
    "LSB_BIND_JOB", "LSB_BIND_CPU_LIST", "LSB_BIND_MEM_LIST",
    "LSB_AFFINITY_HOSTFILE", "LSB_PJL_TASK_GEOMETRY"
};
static const int num_lsf_env_vars = sizeof(lsf_env_vars) / sizeof(lsf_env_vars[0]);

/* Structure to hold environment variable */
struct env_var {
    char name[MAX_ENV_VAR_LEN];
    char value[MAX_ENV_VAR_LEN];
};

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

/* Function to preserve LSF environment variables */
int preserve_lsf_environment(struct env_var* preserved_vars, int* num_preserved) {
    *num_preserved = 0;
    
    /* Preserve LSF environment variables */
    for (int i = 0; i < num_lsf_env_vars && *num_preserved < MAX_ENV_VARS; i++) {
        const char* value = getenv(lsf_env_vars[i]);
        if (value) {
            strncpy(preserved_vars[*num_preserved].name, lsf_env_vars[i], MAX_ENV_VAR_LEN - 1);
            strncpy(preserved_vars[*num_preserved].value, value, MAX_ENV_VAR_LEN - 1);
            preserved_vars[*num_preserved].name[MAX_ENV_VAR_LEN - 1] = '\0';
            preserved_vars[*num_preserved].value[MAX_ENV_VAR_LEN - 1] = '\0';
            (*num_preserved)++;
        }
    }
    
    /* Also preserve PATH */
    const char* path_value = getenv("PATH");
    if (path_value && *num_preserved < MAX_ENV_VARS) {
        strncpy(preserved_vars[*num_preserved].name, "PATH", MAX_ENV_VAR_LEN - 1);
        strncpy(preserved_vars[*num_preserved].value, path_value, MAX_ENV_VAR_LEN - 1);
        preserved_vars[*num_preserved].name[MAX_ENV_VAR_LEN - 1] = '\0';
        preserved_vars[*num_preserved].value[MAX_ENV_VAR_LEN - 1] = '\0';
        (*num_preserved)++;
    }
    
    return 0;
}

/* Function to safely set environment for the target user */
int setup_user_environment(const char* username, struct passwd* pwd, 
                          struct env_var* preserved_vars, int num_preserved) {
    /* Clear environment */
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
    
    /* Restore preserved environment variables */
    for (int i = 0; i < num_preserved; i++) {
        if (setenv(preserved_vars[i].name, preserved_vars[i].value, 1) != 0) {
            fprintf(stderr, "Failed to restore environment variable %s\n", preserved_vars[i].name);
            return -1;
        }
    }
    
    /* If PATH wasn't preserved, set a default */
    if (getenv("PATH") == NULL) {
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
    struct env_var preserved_vars[MAX_ENV_VARS];
    int num_preserved = 0;
    
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
    
    /* Preserve LSF environment variables before clearing */
    if (preserve_lsf_environment(preserved_vars, &num_preserved) != 0) {
        fprintf(stderr, "Failed to preserve environment variables\n");
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
        
        /* Setup environment with preserved LSF variables */
        if (setup_user_environment(username, pwd, preserved_vars, num_preserved) != 0) {
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