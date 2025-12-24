#!/bin/bash

# Deployment script for Meta-Data-Tag-Generator on AWS EC2
# This script should be run on the EC2 instance

set -e

echo "========================================="
echo "Meta-Data-Tag-Generator Deployment Script"
echo "========================================="

# Configuration
APP_DIR="$HOME/meta-tag-generator"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Navigate to application directory
cd "$APP_DIR" || {
    print_error "Application directory not found: $APP_DIR"
    exit 1
}

print_status "Pulling latest Docker images..."
docker-compose pull

print_status "Stopping existing containers..."
docker-compose down

print_status "Starting services..."
docker-compose up -d

print_status "Waiting for services to be healthy..."
sleep 30

# Check if backend is healthy
if curl -f http://localhost:8000/api/health &> /dev/null; then
    print_status "Backend is healthy ✓"
else
    print_error "Backend health check failed ✗"
    docker-compose logs backend
    exit 1
fi

# Check if frontend is accessible
if curl -f http://localhost:3000 &> /dev/null; then
    print_status "Frontend is healthy ✓"
else
    print_warning "Frontend health check failed (may need more time)"
fi

print_status "Cleaning up old Docker images..."
docker image prune -af > /dev/null 2>&1

print_status "Deployment completed successfully! 🚀"
print_status "Backend: http://localhost:8000"
print_status "Frontend: http://localhost:3000"

echo "========================================="
echo "View logs with: docker-compose logs -f"
echo "========================================="

