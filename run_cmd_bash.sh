#!/bin/bash
# Auto-update script for RetroFit v2.1 fleet devices
# Repository: https://github.com/aditya08deole/Retro-EvaraFlow.git
#
# Designed to be run via cron:
#   */30 * * * * /home/pi/Desktop/Evaratech/Evaraflow/run_cmd_bash.sh >> /home/pi/Desktop/Evaratech/Evaraflow/update.log 2>&1

REPO_DIR="/home/pi/Desktop/Evaratech/Evaraflow"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting update check..."

# Step 1: Check internet connectivity (save result immediately)
wget -q --spider http://google.com
INTERNET_OK=$?

if [[ $INTERNET_OK -ne 0 ]]; then
    echo "$LOG_PREFIX No Internet connection — skipping update"
    exit 0
fi

# Step 2: Navigate to repository directory
if [ ! -d "$REPO_DIR" ]; then
    echo "$LOG_PREFIX ERROR: Repository directory not found: $REPO_DIR"
    exit 1
fi

cd "$REPO_DIR" || exit 1

# Step 3: Get current commit hash
CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null)
CURRENT_SHORT=${CURRENT_COMMIT:0:7}

if [ -z "$CURRENT_COMMIT" ]; then
    echo "$LOG_PREFIX ERROR: Not a git repository or git not installed"
    exit 1
fi

# Step 4: Protect device-specific files from git operations
git update-index --assume-unchanged config_WM.py 2>/dev/null

# Step 5: Pull updates from master branch
PULL_OUTPUT=$(git pull origin master 2>&1)
PULL_EXIT=$?

if [ $PULL_EXIT -ne 0 ]; then
    echo "$LOG_PREFIX ERROR: git pull failed (exit $PULL_EXIT): $PULL_OUTPUT"
    exit 1
fi

# Step 6: Get new commit hash and compare
NEW_COMMIT=$(git rev-parse HEAD 2>/dev/null)
NEW_SHORT=${NEW_COMMIT:0:7}

if [[ "$CURRENT_COMMIT" != "$NEW_COMMIT" ]]; then
    echo "$LOG_PREFIX Update detected: $CURRENT_SHORT -> $NEW_SHORT"
    echo "$LOG_PREFIX Pull output: $PULL_OUTPUT"
    
    # Restart service to apply updates (systemd auto-clears Python cache)
    sudo systemctl restart codetest.service
    RESTART_EXIT=$?
    
    if [ $RESTART_EXIT -eq 0 ]; then
        echo "$LOG_PREFIX Service restarted successfully"
    else
        echo "$LOG_PREFIX ERROR: Service restart failed (exit $RESTART_EXIT)"
    fi
else
    echo "$LOG_PREFIX No changes detected (at $CURRENT_SHORT)"
fi
