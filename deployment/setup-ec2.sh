#!/bin/bash

# EC2 Initial Setup Script for Meta-Data-Tag-Generator
# Run this script on a fresh EC2 instance (Ubuntu 22.04 LTS recommended)

set -e

echo "========================================="
echo "EC2 Initial Setup for Meta-Data-Tag-Generator"
echo "========================================="

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
echo "Installing Docker..."
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Install Docker Compose standalone
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add current user to docker group
sudo usermod -aG docker $USER

# Install AWS CLI
echo "Installing AWS CLI..."
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws

# Create application directory
echo "Creating application directory..."
mkdir -p ~/meta-tag-generator
cd ~/meta-tag-generator

# Configure AWS credentials (interactive)
echo ""
echo "========================================="
echo "AWS Configuration"
echo "========================================="
echo "Please configure AWS credentials for ECR access:"
aws configure

# Test Docker
echo "Testing Docker installation..."
sudo docker run hello-world

echo ""
echo "========================================="
echo "Setup completed successfully! ✓"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Log out and log back in for Docker group changes to take effect"
echo "2. Configure GitHub Actions secrets with:"
echo "   - AWS_ACCESS_KEY_ID"
echo "   - AWS_SECRET_ACCESS_KEY"
echo "   - AWS_ACCOUNT_ID"
echo "   - EC2_HOST (this instance's public IP)"
echo "   - EC2_USER (ubuntu)"
echo "   - EC2_SSH_PRIVATE_KEY"
echo "3. Create ECR repositories:"
echo "   aws ecr create-repository --repository-name meta-tag-backend"
echo "   aws ecr create-repository --repository-name meta-tag-frontend"
echo "4. Push code to GitHub to trigger deployment"
echo ""

