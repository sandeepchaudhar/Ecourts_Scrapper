#!/bin/bash

# eCourts Cause List Scraper Deployment Script
# This script helps with deployment and setup tasks

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to setup environment
setup_environment() {
    print_status "Setting up environment..."
    
    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        print_status "Creating .env file from template..."
        cp .env.example .env
        print_warning "Please edit .env file with your specific configuration"
    else
        print_status ".env file already exists"
    fi
    
    # Create necessary directories
    print_status "Creating necessary directories..."
    mkdir -p static/downloads
    mkdir -p static/images
    mkdir -p logs
    
    # Create .gitkeep files to preserve empty directories
    touch static/downloads/.gitkeep
    touch logs/.gitkeep
    
    print_success "Environment setup completed"
}

# Function to install dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."
    
    if command_exists python3; then
        python3 -m pip install --upgrade pip
        python3 -m pip install -r requirements.txt
        print_success "Dependencies installed successfully"
    else
        print_error "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
}

# Function to run development server
run_development() {
    print_status "Starting development server..."
    
    # Use development environment
    if [ -f .env.development ]; then
        export $(cat .env.development | grep -v '^#' | xargs)
    fi
    
    python3 app.py
}

# Function to build Docker image
build_docker() {
    print_status "Building Docker image..."
    
    if command_exists docker; then
        docker build -t ecourts-scraper:latest .
        print_success "Docker image built successfully"
    else
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
}

# Function to run with Docker Compose
run_docker() {
    print_status "Starting application with Docker Compose..."
    
    if command_exists docker-compose; then
        docker-compose up -d
        print_success "Application started successfully"
        print_status "Application is available at http://localhost:8000"
        print_status "Use 'docker-compose logs -f' to view logs"
    else
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

# Function to run development with Docker Compose
run_docker_dev() {
    print_status "Starting development environment with Docker Compose..."
    
    if command_exists docker-compose; then
        docker-compose --profile dev up -d ecourts-scraper-dev
        print_success "Development environment started successfully"
        print_status "Application is available at http://localhost:8001"
        print_status "Use 'docker-compose logs -f ecourts-scraper-dev' to view logs"
    else
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

# Function to stop Docker services
stop_docker() {
    print_status "Stopping Docker services..."
    
    if command_exists docker-compose; then
        docker-compose down
        print_success "Services stopped successfully"
    else
        print_error "Docker Compose is not installed."
        exit 1
    fi
}

# Function to show logs
show_logs() {
    if command_exists docker-compose; then
        docker-compose logs -f
    else
        print_status "Showing local logs..."
        tail -f ecourts_scraper.log
    fi
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    
    if [ -d "tests" ]; then
        python3 -m pytest tests/ -v
        print_success "Tests completed"
    else
        print_warning "No tests directory found"
    fi
}

# Function to clean up
cleanup() {
    print_status "Cleaning up..."
    
    # Remove Python cache
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    
    # Clean up logs (keep last 5 files)
    if [ -d "logs" ]; then
        find logs/ -name "*.log" -type f -printf '%T@ %p\n' | sort -n | head -n -5 | cut -d' ' -f2- | xargs rm -f 2>/dev/null || true
    fi
    
    print_success "Cleanup completed"
}

# Function to show help
show_help() {
    echo "eCourts Cause List Scraper Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  setup           Setup environment and create necessary files"
    echo "  install         Install Python dependencies"
    echo "  dev             Run development server"
    echo "  build           Build Docker image"
    echo "  start           Start application with Docker Compose"
    echo "  start-dev       Start development environment with Docker Compose"
    echo "  stop            Stop Docker services"
    echo "  logs            Show application logs"
    echo "  test            Run tests"
    echo "  clean           Clean up cache and old log files"
    echo "  help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 setup && $0 install && $0 dev"
    echo "  $0 build && $0 start"
    echo "  $0 start-dev"
}

# Main script logic
case "${1:-help}" in
    setup)
        setup_environment
        ;;
    install)
        install_dependencies
        ;;
    dev)
        run_development
        ;;
    build)
        build_docker
        ;;
    start)
        run_docker
        ;;
    start-dev)
        run_docker_dev
        ;;
    stop)
        stop_docker
        ;;
    logs)
        show_logs
        ;;
    test)
        run_tests
        ;;
    clean)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac