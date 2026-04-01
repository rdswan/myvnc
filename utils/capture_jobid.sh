#!/usr/bin/bash
#
# LSF pre-exec (-E): write LSB_JOBID to a file so singularity --cleanenv + vncserver_wrapper can recover it.
# LSF sets LSB_JOBID before this runs. Pass a path whose name ends with .$$ so the shell expands
# $$ to the pre-exec PID (explicit digits, no %J). Writes that file plus myvnc_lsb_jobid_pointer
# (same directory) with the full path so vncserver_wrapper can find the data file.
#
# Usage: capture_jobid.sh /path/to/myvnc_lsb_jobid.$$   ($$ expanded by the shell that runs -E)

set -euo pipefail

out="${1:?capture_jobid.sh: output file path required}"

printf '%s\n' "${LSB_JOBID:-}" > "$out"
printf '%s\n' "$out" > "${out%/*}/myvnc_lsb_jobid_pointer"
