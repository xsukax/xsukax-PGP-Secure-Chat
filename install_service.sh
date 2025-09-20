#!/bin/bash

# xsukax PGP Secure Chat Server Installation Script
# Supports Debian/Ubuntu and CentOS/RHEL/Rocky/AlmaLinux

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Detect OS
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        print_error "Cannot detect operating system"
        exit 1
    fi
    
    case $OS in
        ubuntu|debian)
            OS_TYPE="debian"
            PACKAGE_MANAGER="apt"
            ;;
        centos|rhel|rocky|almalinux|fedora)
            OS_TYPE="redhat"
            PACKAGE_MANAGER="yum"
            if command -v dnf &> /dev/null; then
                PACKAGE_MANAGER="dnf"
            fi
            ;;
        *)
            print_error "Unsupported operating system: $OS"
            exit 1
            ;;
    esac
    
    print_status "Detected OS: $OS $OS_VERSION ($OS_TYPE)"
}

# Install Python3 and pip if not present
install_dependencies() {
    print_status "Installing dependencies..."
    
    case $OS_TYPE in
        debian)
            apt update
            apt install -y python3 python3-pip python3-venv
            ;;
        redhat)
            $PACKAGE_MANAGER update -y
            $PACKAGE_MANAGER install -y python3 python3-pip
            if [[ $OS == "centos" && $OS_VERSION == "7" ]]; then
                $PACKAGE_MANAGER install -y python36-devel
            fi
            ;;
    esac
    
    # Install Python packages
    pip3 install websockets asyncio --break-system-packages
    
    print_success "Dependencies installed"
}

# Create application directory and move server file
setup_application() {
    print_status "Setting up application..."
    
    # Check if server.py exists in current directory
    if [[ ! -f "server.py" ]]; then
        print_error "server.py not found in current directory"
        exit 1
    fi
    
    # Create application directory
    mkdir -p /opt/xsukax-pgp-chat
    
    # Move server file
    cp server.py /opt/xsukax-pgp-chat/
    chmod +x /opt/xsukax-pgp-chat/server.py
    
    # Create logs directory
    mkdir -p /var/log/xsukax-pgp-chat
    
    print_success "Application files copied to /opt/xsukax-pgp-chat"
}

# Create systemd service
create_service() {
    print_status "Creating systemd service..."
    
    cat > /etc/systemd/system/xsukax-pgp-chat.service << EOF
[Unit]
Description=xsukax PGP Secure Chat Server
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=root
WorkingDirectory=/opt/xsukax-pgp-chat
ExecStart=/usr/bin/python3 /opt/xsukax-pgp-chat/server.py
StandardOutput=journal
StandardError=journal
SyslogIdentifier=xsukax-pgp-chat

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/xsukax-pgp-chat

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload
    
    print_success "Systemd service created"
}

# Enable and start service
start_service() {
    print_status "Enabling and starting xsukax-pgp-chat service..."
    
    # Enable service to start on boot
    systemctl enable xsukax-pgp-chat
    
    # Start service
    systemctl start xsukax-pgp-chat
    
    # Check status
    sleep 2
    if systemctl is-active --quiet xsukax-pgp-chat; then
        print_success "xsukax PGP Chat Server is running!"
    else
        print_error "Failed to start service. Check logs with: journalctl -u xsukax-pgp-chat"
        exit 1
    fi
}

# Configure firewall
configure_firewall() {
    print_status "Configuring firewall..."
    
    case $OS_TYPE in
        debian)
            if command -v ufw &> /dev/null; then
                ufw allow 8765/tcp
                print_success "UFW firewall rule added for port 8765"
            else
                print_warning "UFW not found. Please manually open port 8765"
            fi
            ;;
        redhat)
            if command -v firewall-cmd &> /dev/null; then
                firewall-cmd --permanent --add-port=8765/tcp
                firewall-cmd --reload
                print_success "Firewalld rule added for port 8765"
            else
                print_warning "Firewalld not found. Please manually open port 8765"
            fi
            ;;
    esac
}

# Show service status and usage
show_status() {
    echo
    print_success "=== xsukax PGP Secure Chat Server Installation Complete ==="
    echo
    echo "Service Status:"
    systemctl status xsukax-pgp-chat --no-pager
    echo
    echo "Useful Commands:"
    echo "  Start:   sudo systemctl start xsukax-pgp-chat"
    echo "  Stop:    sudo systemctl stop xsukax-pgp-chat"
    echo "  Restart: sudo systemctl restart xsukax-pgp-chat"
    echo "  Status:  sudo systemctl status xsukax-pgp-chat"
    echo "  Logs:    sudo journalctl -u xsukax-pgp-chat -f"
    echo
    echo "Server is running on: ws://$(hostname -I | awk '{print $1}'):8765"
    echo "Configuration: /opt/xsukax-pgp-chat/"
    echo "Logs: journalctl -u xsukax-pgp-chat"
    echo
}

# Uninstall function
uninstall() {
    print_status "Uninstalling xsukax PGP Chat Server..."
    
    # Stop and disable service
    systemctl stop xsukax-pgp-chat 2>/dev/null || true
    systemctl disable xsukax-pgp-chat 2>/dev/null || true
    
    # Remove service file
    rm -f /etc/systemd/system/xsukax-pgp-chat.service
    
    # Remove application directory
    rm -rf /opt/xsukax-pgp-chat
    
    # Remove logs
    rm -rf /var/log/xsukax-pgp-chat
    
    # Reload systemd
    systemctl daemon-reload
    
    print_success "xsukax PGP Chat Server uninstalled"
}

# Main installation function
install() {
    echo "🔐 xsukax PGP Secure Chat Server Installer"
    echo "=========================================="
    
    check_root
    detect_os
    install_dependencies
    setup_application
    create_service
    start_service
    configure_firewall
    show_status
}

# Help function
show_help() {
    echo "xsukax PGP Secure Chat Server Installer"
    echo
    echo "Usage: $0 [OPTION]"
    echo
    echo "Options:"
    echo "  install     Install and start the chat server (default)"
    echo "  uninstall   Remove the chat server completely"
    echo "  status      Show current service status"
    echo "  help        Show this help message"
    echo
    echo "Examples:"
    echo "  sudo $0 install"
    echo "  sudo $0 uninstall"
    echo "  sudo $0 status"
    echo
}

# Main script logic
case "${1:-install}" in
    install)
        install
        ;;
    uninstall)
        check_root
        uninstall
        ;;
    status)
        systemctl status xsukax-pgp-chat --no-pager
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac
