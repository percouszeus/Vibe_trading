#!/bin/bash

# deploy_oci.sh
# Bootstrap script for deploying Vibe Trading to an OCI ARM instance.

set -e

echo "Starting deployment of Vibe Trading..."

# 1. Update system and install dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv git htop screen

# 2. Setup project directory
PROJECT_DIR="$HOME/Vibe_trading"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Cloning repository..."
    # Assuming the repo is public or ssh keys are set up.
    # Replace with the actual repository URL
    git clone https://github.com/percouszeus/Vibe_trading.git "$PROJECT_DIR"
else
    echo "Repository exists. Pulling latest changes..."
    cd "$PROJECT_DIR"
    git reset --hard HEAD
    git pull origin main
fi

cd "$PROJECT_DIR"

# 3. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Installing requirements..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure systemd service
echo "Configuring systemd service..."
sudo cp vibe_trading.service /etc/systemd/system/
sudo sed -i "s|/home/ubuntu|$HOME|g" /etc/systemd/system/vibe_trading.service

sudo systemctl daemon-reload
sudo systemctl enable vibe_trading.service
sudo systemctl restart vibe_trading.service

echo "Deployment complete! Vibe Trading is running."
echo "Check status: sudo systemctl status vibe_trading"
echo "Check logs: sudo journalctl -u vibe_trading -f"
