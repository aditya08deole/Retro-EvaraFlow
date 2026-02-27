#!/bin/bash
# Auto-update script for RetroFit v2.1 fleet devices
# Designed to be run via cron:
#   */30 * * * * /home/pi/Desktop/Evaratech/Evaraflow/run_cmd_bash.sh >> /home/pi/Desktop/Evaratech/Evaraflow/update.log 2>&1

REPO_DIR="/home/pi/Desktop/Evaratech/Evaraflow"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX Starting update check..."

# Step 1: Check internet connectivity
wget -q --spider --timeout=5 http://google.com
if [ $? -ne 0 ]; then
    echo "$LOG_PREFIX No internet — skipping"
    exit 0
fi

# Step 2: Verify repository
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "$LOG_PREFIX ERROR: Not a git repository: $REPO_DIR"
    exit 1
fi

cd "$REPO_DIR" || exit 1

# Step 3: Current commit
CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null)
CURRENT_SHORT=${CURRENT_COMMIT:0:7}

if [ -z "$CURRENT_COMMIT" ]; then
    echo "$LOG_PREFIX ERROR: git rev-parse failed"
    exit 1
fi

# Step 4: Protect device-specific files
git update-index --assume-unchanged config_WM.py 2>/dev/null

# Step 5: Pull updates
PULL_OUTPUT=$(git pull origin master 2>&1)
PULL_EXIT=$?

if [ $PULL_EXIT -ne 0 ]; then
    echo "$LOG_PREFIX ERROR: git pull failed (exit $PULL_EXIT): $PULL_OUTPUT"
    exit 1
fi

# Step 6: Check for changes
NEW_COMMIT=$(git rev-parse HEAD 2>/dev/null)
NEW_SHORT=${NEW_COMMIT:0:7}

if [ "$CURRENT_COMMIT" != "$NEW_COMMIT" ]; then
    echo "$LOG_PREFIX Update detected: $CURRENT_SHORT -> $NEW_SHORT"

    # Re-install dependencies if requirements.txt changed
    if git diff --name-only "$CURRENT_COMMIT" "$NEW_COMMIT" | grep -q "requirements.txt"; then
        echo "$LOG_PREFIX requirements.txt changed — reinstalling deps..."
        "$REPO_DIR/.venv/bin/pip3" install --no-cache-dir -r requirements.txt > /dev/null 2>&1
    fi

    # Restart service
    sudo systemctl restart codetest.service
    RESTART_EXIT=$?

    if [ $RESTART_EXIT -eq 0 ]; then
        echo "$LOG_PREFIX Service restarted successfully"
    else
        echo "$LOG_PREFIX ERROR: Service restart failed (exit $RESTART_EXIT)"
    fi
else
    echo "$LOG_PREFIX No changes (at $CURRENT_SHORT)"
fi
