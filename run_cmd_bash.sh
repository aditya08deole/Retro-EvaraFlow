#!/bin/bash
# Auto-update script for Retro-EvaraFlow fleet devices
# Repository: https://github.com/aditya08deole/Retro-EvaraFlow.git

# Check internet connectivity
wget -q --spider http://google.com

# Get current commit hash
cicomid=$(git rev-parse HEAD)
cicomid=${cicomid:0:7}

if [[ $? -eq 0 ]]
 then
    # Navigate to repository directory
    cd /home/pi/Desktop/Evaratech/Evaraflow/
    
    # Protect device-specific files from git operations
    git update-index --assume-unchanged Variable.txt 2>/dev/null
    git update-index --assume-unchanged var2.txt 2>/dev/null
    git update-index --assume-unchanged config_WM.py 2>/dev/null
    
    # Pull updates from master branch
    git pull origin master
    
    # Get new commit hash
    cicomid_new=$(git rev-parse HEAD)
    cicomid_new=${cicomid_new:0:7}
    
    # Check if code changed
    if [[ "$cicomid" != "$cicomid_new" ]]
    then
      echo "Update detected: $cicomid -> $cicomid_new"
      cicomid=$cicomid_new
      
      # Restart service to apply updates
      sudo systemctl restart codetest.service
      echo "Service restarted successfully"
    else
      echo 'No changes detected'
    fi

else
    echo 'No Internet connection - skipping update'

fi
