#!/bin/bash
# Retro-EvaraFlow Installation Script

echo "Installing Retro-EvaraFlow Water Meter Reader..."

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python dependencies
sudo apt-get install -y python3-pip python3-opencv python3-numpy
sudo pip3 install -r requirements.txt

# Create log file
touch error.log

# Copy systemd service
sudo cp codetest.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable codetest.service

# Start service
sudo systemctl start codetest.service

# Check status
sudo systemctl status codetest.service

echo "Installation complete!"
echo "Use 'sudo systemctl status codetest.service' to check status"
echo "Use 'sudo journalctl -u codetest.service -f' to view logs"
