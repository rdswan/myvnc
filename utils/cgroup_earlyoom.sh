#!/bin/bash
# Poor-man's earlyoom for LSF cgroup-v2 jobs (MyVNC VNC sessions and tmux
# sessions).
#
# Monitors the job's cgroup memory and, before LSF's OOM killer wipes out the
# whole job, kills the largest non-protected process. Protected processes:
#   1. This script's ancestor chain (xstartup / the bash heartbeat wrapper).
#   2. Any "guardian" process living in the cgroup whose comm matches a known
#      session keeper -- Xvnc/Xtigervnc/Xvfb (VNC) or "tmux: server" (tmux).
#      Guardians are rescanned every iteration because the tmux server
#      daemonizes (PPID=1) and isn't in our ancestor chain.
#
# Launch from a VNC xstartup script (truncating the log each session so it
# only reflects the current run):
#     nohup "$HOME/myvnc/utils/cgroup_earlyoom.sh" \
#         > "$HOME/.vnc/cgroup_earlyoom.log" 2>&1 &
#
# Launch from a tmux bsub wrapper (myvnc lsf_manager.py builds tmux_cmd as
# `unset LSB_QUEUE && tmux new-session -d ... && while has-session; do sleep;
# done`; insert the watcher before the tmux command):
#     unset LSB_QUEUE && \
#       "$HOME/myvnc/utils/cgroup_earlyoom.sh" \
#           > "$HOME/.tmux/cgroup_earlyoom.${LSB_JOBID}.log" 2>&1 & \
#       /usr/bin/tmux new-session -d -s NAME && \
#       while /usr/bin/tmux has-session -t NAME 2>/dev/null; do sleep 5; done
#
# Tunables (env vars set the defaults; CLI flags below override):
#   EARLYOOM_THRESHOLD  default 70    percent of cgroup memory.max
#   EARLYOOM_INTERVAL   default 5     seconds between checks
#   EARLYOOM_PRETEND    default 0     1 = log what would be killed, don't kill
#   EARLYOOM_SLACK      default 1     1 = DM the owning user via slackme on each kill
#   EARLYOOM_SLACK_BIN  default /tools_risc/common/bin/slackme

set -u

# -------- defaults (from env, with built-in fallbacks) --------
THRESHOLD="${EARLYOOM_THRESHOLD:-70}"
INTERVAL="${EARLYOOM_INTERVAL:-5}"
PRETEND="${EARLYOOM_PRETEND:-0}"
SLACK="${EARLYOOM_SLACK:-1}"
SLACK_BIN="${EARLYOOM_SLACK_BIN:-/tools_risc/common/bin/slackme}"

# -------- CLI flags (override the env defaults above) --------
for arg in "$@"; do
    case "$arg" in
        -n|--pretend|--dry-run) PRETEND=1 ;;
        --no-pretend)           PRETEND=0 ;;
        --slack)                SLACK=1 ;;
        --no-slack)             SLACK=0 ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

log() { printf '%s [cgroup_earlyoom %d] %s\n' "$(date '+%F %T')" "$$" "$*"; }

# alert() goes to stdout AND to syslog (user.warning) so a central syslog
# collector (Loki/promtail, rsyslog forwarding) can pick up intervention
# events. Failures of the syslog path are surfaced into the local log so
# they're visible without polling /var/log/messages.
alert() {
    log "$*"
    if command -v logger >/dev/null 2>&1; then
        local err rc
        err=$(logger --socket-errors=on -t cgroup_earlyoom -p user.warning -- "$*" 2>&1)
        rc=$?
        [ "$rc" -ne 0 ] && log "WARN: logger rc=$rc msg='$err' (syslog path failed)"
    else
        log "WARN: 'logger' not on PATH; syslog path disabled"
    fi
}

# DM the owning user via slackme on a kill event. One concise message per
# intervention; failures are logged but do not block the kill. Time-boxed so
# a hung slack hook can't stall the watcher.
# Args: $1=verb, $2=pid, $3=rss_mb, $4=limit_gb, $5=cmdline
slack_notify() {
    [ "$SLACK" = 1 ] || return 0
    if [ ! -x "$SLACK_BIN" ]; then
        log "WARN: slack disabled: $SLACK_BIN not executable"; return 0
    fi
    local verb="$1" pid="$2" rss_mb="$3" limit_gb="$4" cmdline="$5"
    [ ${#cmdline} -gt 200 ] && cmdline="${cmdline:0:200}..."
    local prefix=""
    [ "$PRETEND" = 1 ] && prefix="[PRETEND] "
    local msg
    msg=$(printf '%s%s PID %s on %s consuming %s MB out of %s GB reserved. Cmdline: %s' \
        "$prefix" "$verb" "$pid" "$(hostname)" "$rss_mb" "$limit_gb" "$cmdline")
    if ! printf '%s\n' "$msg" | timeout 5 "$SLACK_BIN" >/dev/null 2>&1; then
        log "WARN: slack notification failed (rc=$?)"
    fi
}

# Probe the syslog path once at startup. If syslog is broken, you see it
# here in the local log rather than discovering it only when a real
# intervention fires and silently fails to reach Loki.
syslog_selftest() {
    if ! command -v logger >/dev/null 2>&1; then
        log "syslog self-test: SKIP (no logger binary)"; return
    fi
    local err rc
    err=$(logger --socket-errors=on -t cgroup_earlyoom -p user.info -- \
        "watcher started job=$1 pid=$$ host=$(hostname) -- syslog self-test" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log "syslog self-test: OK (sent user.info; grep /var/log/messages for tag=cgroup_earlyoom)"
    else
        log "syslog self-test: FAIL rc=$rc err='$err'"
    fi
}

trap 'log "exiting on signal"; exit 0' INT TERM

# Walk up the cgroup tree until memory.max is a real number (the leaf in an
# LSF v2 job has memory.max="max"; the real limit lives on the parent).
find_limit_cgroup() {
    local cg val
    cg="/sys/fs/cgroup$(awk -F: '$2==""{print $3}' /proc/self/cgroup)"
    cg="${cg//\/\//\/}"   # collapse "//" from the join
    while [ "$cg" != "/sys/fs/cgroup" ] && [ -d "$cg" ]; do
        if [ -r "$cg/memory.max" ]; then
            val=$(cat "$cg/memory.max")
            if [ -n "$val" ] && [ "$val" != "max" ]; then
                printf '%s\n' "$cg"
                return 0
            fi
        fi
        cg=$(dirname "$cg")
    done
    return 1
}

# Walk our ppid chain; protect every ancestor up to (and including) a known
# session keeper. For VNC jobs the chain ends at Xvnc; for tmux jobs it ends
# at the bash heartbeat wrapper (tmux itself daemonizes, so it's NOT in the
# chain -- it's caught separately by find_guardian_pids).
find_ancestor_pids() {
    local pid=$$ comm
    local -a chain=()
    while [ -n "$pid" ] && [ "$pid" -gt 1 ]; do
        comm=$(cat "/proc/$pid/comm" 2>/dev/null) || break
        [ -z "$comm" ] && break
        chain+=("$pid")
        case "$comm" in
            Xvnc|Xvnc4|Xtigervnc|Xvfb) break ;;
        esac
        pid=$(awk '/^PPid:/{print $2}' "/proc/$pid/status" 2>/dev/null)
    done
    printf '%s\n' "${chain[@]}"
}

# Scan a list of PIDs and emit those whose kernel comm marks them as a
# session "guardian" we must never kill. Re-run each tick so that a
# late-starting tmux server (PPID=1, not in our ancestor chain) is found.
# Note: tmux sets its comm to literal "tmux: server" (with a space) via
# prctl(PR_SET_NAME), so we read /proc/PID/comm directly rather than relying
# on whitespace-tokenizing ps output.
find_guardian_pids() {
    local pid comm
    for pid in $1; do
        comm=$(cat "/proc/$pid/comm" 2>/dev/null) || continue
        case "$comm" in
            Xvnc|Xvnc4|Xtigervnc|Xvfb|"tmux: server"|tmux)
                printf '%s\n' "$pid" ;;
        esac
    done
}

CGROUP_PATH=$(find_limit_cgroup) || {
    log "ERROR: no ancestor cgroup has a numeric memory.max; nothing to monitor"
    exit 1
}

# Pull the LSF job id out of the cgroup path (e.g. job.557129800.18902.1778467099)
# for inclusion in syslog records, so central log search can group by job.
JOBID=$(printf '%s\n' "$CGROUP_PATH" | grep -oE 'job\.[0-9.]+' | head -1)
[ -z "$JOBID" ] && JOBID="unknown-job"

# Ancestor chain is static for the life of this script; guardian PIDs are
# rescanned each iteration (see main loop).
ANCESTORS=$(find_ancestor_pids | sort -u)

# Snapshot the limit at startup so the banner can spell out what the
# percentage threshold actually means in GB.
STARTUP_LIMIT=$(cat "$CGROUP_PATH/memory.max" 2>/dev/null)
STARTUP_CURRENT=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null)
LIMIT_GB=$(awk -v b="$STARTUP_LIMIT"  'BEGIN{printf "%.2f", b/1024/1024/1024}')
THRESH_GB=$(awk -v b="$STARTUP_LIMIT" -v t="$THRESHOLD" 'BEGIN{printf "%.2f", (b*t/100)/1024/1024/1024}')
START_GB=$(awk -v b="$STARTUP_CURRENT" 'BEGIN{printf "%.2f", b/1024/1024/1024}')
START_PCT=$(( 100 * STARTUP_CURRENT / STARTUP_LIMIT ))

log "watching $CGROUP_PATH"
log "job=${JOBID}  memory limit: ${LIMIT_GB} GB  current usage: ${START_GB} GB (${START_PCT}%)"
log "intervention threshold: ${THRESHOLD}% = ${THRESH_GB} GB used"
log "poll interval: ${INTERVAL}s$([ "$PRETEND" = 1 ] && echo '  [PRETEND MODE -- no kills]')"
log "slack notify: $([ "$SLACK" = 1 ] && echo "ON  ($SLACK_BIN)" || echo "OFF")"
log "protected ancestors: $(echo $ANCESTORS)"
syslog_selftest "$JOBID"

while true; do
    if ! LIMIT=$(cat "$CGROUP_PATH/memory.max" 2>/dev/null) \
       || ! CURRENT=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null); then
        log "cgroup files vanished (job ended?); exiting"
        exit 0
    fi
    [ "$LIMIT" = "max" ] && { sleep "$INTERVAL"; continue; }

    USAGE_PCT=$(( 100 * CURRENT / LIMIT ))

    if [ "$USAGE_PCT" -gt "$THRESHOLD" ]; then
        # All PIDs in this cgroup subtree. In v2 with the "no internal
        # processes" rule the leaf holds everything, but walking the tree is
        # safe and future-proof.
        PIDS=$(find "$CGROUP_PATH" -name cgroup.procs -exec cat {} + 2>/dev/null | sort -u)
        if [ -z "$PIDS" ]; then
            sleep "$INTERVAL"; continue
        fi

        # Rebuild the protected set each tick: ancestor chain (static) plus
        # any guardian-comm process currently alive in the cgroup (dynamic --
        # the tmux server may not exist yet when this script first starts).
        GUARDIANS=$(find_guardian_pids "$PIDS")
        PROTECTED=$(printf '%s\n%s\n' "$ANCESTORS" "$GUARDIANS" \
            | grep -v '^$' | sort -u | tr '\n' '|' | sed 's/|$//')

        # Largest-RSS PID that isn't in the protected set.
        TARGET_PID=$(
            ps -o pid=,rss= -p "$(echo "$PIDS" | paste -sd,)" 2>/dev/null \
              | awk -v skip="$PROTECTED" '
                    BEGIN { n=split(skip,a,"|"); for(i=1;i<=n;i++) s[a[i]]=1 }
                    !($1 in s) { print $2, $1 }
                ' \
              | sort -nr \
              | awk 'NR==1 {print $2}'
        )

        if [ -n "$TARGET_PID" ] && [ "$TARGET_PID" -gt 0 ]; then
            CMDLINE=$(tr '\0' ' ' < "/proc/$TARGET_PID/cmdline" 2>/dev/null)
            [ -z "$CMDLINE" ] && CMDLINE=$(ps -p "$TARGET_PID" -o comm= 2>/dev/null)
            PID_USER=$(ps -p "$TARGET_PID" -o user= 2>/dev/null | tr -d ' ')
            [ -z "$PID_USER" ] && PID_USER="?"
            PID_RSS_KB=$(ps -p "$TARGET_PID" -o rss= 2>/dev/null | tr -d ' ')
            PID_RSS_MB=$(( PID_RSS_KB / 1024 ))
            LIMIT_KB=$(( LIMIT / 1024 ))
            PID_PCT=$(( 100 * PID_RSS_KB / LIMIT_KB ))
            VERB=$([ "$PRETEND" = 1 ] && echo "would kill" || echo "killing")
            TAG=$([ "$PRETEND" = 1 ] && echo " (PRETEND)" || echo "")

            alert "--- LSF OOM INTERVENTION${TAG} ---"
            alert "job=${JOBID} user=${PID_USER} cgroup usage ${USAGE_PCT}% of $((LIMIT/1024/1024/1024)) GB limit"
            alert "${VERB} PID ${TARGET_PID} (user=${PID_USER}): ${PID_RSS_MB} MB (${PID_PCT}% of limit)"
            alert "cmdline: ${CMDLINE}"
            [ "$PRETEND" = 1 ] || kill -9 "$TARGET_PID" 2>/dev/null
            slack_notify "Killed" "$TARGET_PID" "$PID_RSS_MB" "$((LIMIT/1024/1024/1024))" "$CMDLINE"
            alert "----------------------------"
        else
            log "usage ${USAGE_PCT}% over threshold but no non-protected target found"
        fi
    fi
    sleep "$INTERVAL"
done
