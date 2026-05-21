#!/bin/bash
# =============================================================================
# ZeniPost — EC2 AMI Preparation Script
# =============================================================================
# Run this ONCE on a fresh Ubuntu 22.04 LTS EC2 instance to produce a
# ready-to-ship AMI.  When anyone launches from that AMI:
#
#   1. Instance boots
#   2. systemd starts zenipost-setup.service automatically
#   3. User opens http://<public-ip>:8080 in browser
#   4. Fills out the 8-step wizard
#   5. App is live — wizard stops itself, never runs again
#
# Usage (run as root or with sudo):
#   chmod +x prepare_ami.sh
#   sudo ./prepare_ami.sh
#
# After this script finishes:
#   - Create an AMI snapshot of this instance in the AWS Console
#   - Distribute that AMI to customers
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/zenipost"
APP_USER="ubuntu"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "  ${GREEN}✔${RESET}  $*"; }
info() { echo -e "  ${CYAN}→${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}!${RESET}  $*"; }
step() { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }
fail() { echo -e "\n${RED}✘ $*${RESET}"; exit 1; }

# ── Must run as root ──────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || fail "Run as root: sudo ./prepare_ami.sh"

echo -e "\n${BOLD}ZeniPost AMI Preparation${RESET}"
echo "  Building a launch-ready AMI from $(lsb_release -ds 2>/dev/null || uname -sr)"
echo "  Target app directory: $APP_DIR"
echo ""

# =============================================================================
# 1. System update
# =============================================================================
step "System update"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq \
  -o Dpkg::Options::="--force-confdef" \
  -o Dpkg::Options::="--force-confold"
ok "System packages updated"

# =============================================================================
# 2. Essential packages
# =============================================================================
step "Installing essential packages"
apt-get install -y -qq \
  curl wget git ca-certificates gnupg lsb-release \
  python3 python3-pip python3-venv \
  jq unzip htop ncdu \
  ufw fail2ban
ok "Essential packages installed"

# =============================================================================
# 3. Docker Engine
# =============================================================================
step "Installing Docker Engine"
if command -v docker &>/dev/null; then
  warn "Docker already installed: $(docker --version)"
else
  # Official Docker install script
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
  rm /tmp/get-docker.sh
  ok "Docker installed: $(docker --version)"
fi

# Docker Compose v2 plugin
if docker compose version &>/dev/null; then
  ok "Docker Compose v2 already present: $(docker compose version)"
else
  apt-get install -y -qq docker-compose-plugin
  ok "Docker Compose v2 installed: $(docker compose version)"
fi

# Add app user to docker group so it can run docker without sudo
usermod -aG docker "$APP_USER" 2>/dev/null || true
ok "User '$APP_USER' added to docker group"

# Enable Docker on boot
systemctl enable docker
systemctl start docker
ok "Docker enabled and started"

# =============================================================================
# 4. Deploy application files
# =============================================================================
step "Deploying application to $APP_DIR"

# Create directory
mkdir -p "$APP_DIR"

# Rsync the repo (excluding dev/build artifacts)
if [[ "$SCRIPT_DIR" != "$APP_DIR" ]]; then
  rsync -a --delete \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='.setup_complete' \
    --exclude='.setup_session.json' \
    --exclude='license.json' \
    --exclude='backend/var/log' \
    --exclude='nginx/ssl' \
    "$SCRIPT_DIR/" "$APP_DIR/"
  ok "Application files deployed to $APP_DIR"
else
  warn "Script is already running from $APP_DIR — skipping rsync"
fi

# Ensure nginx/ssl directory exists (certbot will populate it during setup)
mkdir -p "$APP_DIR/nginx/ssl"

# Set ownership
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
ok "Ownership set to $APP_USER:$APP_USER"

# Make setup_server.py and prepare_ami.sh executable
chmod +x "$APP_DIR/setup_server.py" 2>/dev/null || true
chmod +x "$APP_DIR/install.py"      2>/dev/null || true
ok "Scripts marked executable"

# =============================================================================
# 5. Systemd service
# =============================================================================
step "Installing zenipost-setup systemd service"

SERVICE_SRC="$APP_DIR/systemd/zenipost-setup.service"
SERVICE_DST="/etc/systemd/system/zenipost-setup.service"

if [[ -f "$SERVICE_SRC" ]]; then
  cp "$SERVICE_SRC" "$SERVICE_DST"
  systemctl daemon-reload
  systemctl enable zenipost-setup
  ok "zenipost-setup.service installed and enabled"
else
  fail "Service file not found at $SERVICE_SRC"
fi

# =============================================================================
# 6. Firewall (ufw) — open only required ports
# =============================================================================
step "Configuring UFW firewall"
# UFW is secondary to EC2 Security Groups but adds defence-in-depth
ufw --force reset          >/dev/null 2>&1
ufw default deny incoming  >/dev/null 2>&1
ufw default allow outgoing >/dev/null 2>&1
ufw allow 22/tcp           >/dev/null 2>&1   # SSH
ufw allow 8080/tcp         >/dev/null 2>&1   # Setup wizard
ufw allow 80/tcp           >/dev/null 2>&1   # HTTP + LE challenge
ufw allow 443/tcp          >/dev/null 2>&1   # HTTPS
ufw --force enable         >/dev/null 2>&1
ok "UFW enabled: 22, 80, 443, 8080 open"

# =============================================================================
# 7. fail2ban — basic SSH brute-force protection
# =============================================================================
step "Configuring fail2ban"
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s
EOF
systemctl enable fail2ban
systemctl restart fail2ban
ok "fail2ban configured"

# =============================================================================
# 8. Kernel / sysctl tuning for a network-heavy app
# =============================================================================
step "Applying sysctl tuning"
cat > /etc/sysctl.d/99-zenipost.conf << 'EOF'
# Increase connection backlog
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
# Reuse TIME_WAIT sockets
net.ipv4.tcp_tw_reuse = 1
# Faster keepalive
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 10
# File descriptor limits
fs.file-max = 200000
EOF
sysctl -p /etc/sysctl.d/99-zenipost.conf >/dev/null 2>&1
ok "sysctl tuning applied"

# Raise ulimit for ubuntu user
cat >> /etc/security/limits.d/zenipost.conf << 'EOF'
ubuntu soft nofile 65536
ubuntu hard nofile 65536
EOF
ok "File descriptor limits raised"

# =============================================================================
# 9. logrotate for Docker logs
# =============================================================================
step "Configuring Docker log rotation"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
EOF
systemctl restart docker
ok "Docker log rotation configured (50 MB × 5 files)"

# =============================================================================
# 10. ec2-instance-connect (allows browser-based SSH from AWS Console)
# =============================================================================
step "Installing EC2 Instance Connect"
apt-get install -y -qq ec2-instance-connect 2>/dev/null && ok "ec2-instance-connect installed" || warn "ec2-instance-connect not available — skipping"

# =============================================================================
# 11. CloudWatch agent (optional — uncomment if you want metrics)
# =============================================================================
# step "Installing CloudWatch agent"
# wget -q https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
# dpkg -i amazon-cloudwatch-agent.deb
# ok "CloudWatch agent installed"

# =============================================================================
# 12. AMI cleanup — remove anything that shouldn't be baked in
# =============================================================================
step "Cleaning up for AMI snapshot"

# Stop setup wizard service before snapshot (it will auto-start on next boot)
systemctl stop zenipost-setup 2>/dev/null || true

# Remove SSH host keys — new ones are auto-generated on first boot
rm -f /etc/ssh/ssh_host_*
ok "SSH host keys removed (will regenerate on first boot)"

# Clear machine-id — new one is generated on first boot
truncate -s 0 /etc/machine-id
ok "machine-id cleared"

# Remove cloud-init artefacts so it re-runs on new instance
cloud-init clean --logs 2>/dev/null || true
ok "cloud-init cleaned"

# Remove history and temp files
rm -f /root/.bash_history /home/ubuntu/.bash_history 2>/dev/null || true
rm -rf /tmp/* /var/tmp/* 2>/dev/null || true
ok "History and temp files removed"

# Trim apt cache
apt-get autoremove -y -qq
apt-get clean -qq
ok "APT cache cleaned"

# Remove any leftover .setup_complete or session files
rm -f "$APP_DIR/.setup_complete" "$APP_DIR/.setup_session.json" 2>/dev/null || true
ok "Setup state cleared"

# Remove license.json if accidentally present
rm -f "$APP_DIR/license.json" 2>/dev/null || true
ok "license.json removed (will be uploaded during setup)"

# =============================================================================
# 13. Final checks
# =============================================================================
step "Final verification"

# Verify setup_server.py syntax
python3 -c "
import ast
with open('$APP_DIR/setup_server.py') as f: ast.parse(f.read())
print('  setup_server.py syntax OK')
"

# Verify systemd service is enabled
systemctl is-enabled zenipost-setup >/dev/null 2>&1 && ok "zenipost-setup.service enabled" || fail "Service not enabled!"

echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  AMI preparation complete!${RESET}"
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. In AWS Console → EC2 → Instances → right-click this instance"
echo -e "     → ${CYAN}Create Image${RESET} → name it e.g. ${CYAN}zenipost-v1.0-$(date +%Y%m%d)${RESET}"
echo -e "  2. Wait for the AMI to reach 'available' state (~5–10 min)"
echo -e "  3. Share or publish the AMI ID to your customers"
echo ""
echo -e "  ${BOLD}Customer launch instructions:${RESET}"
echo -e "  1. Launch EC2 from your AMI (t3.medium or larger recommended)"
echo -e "  2. Security Group: open TCP ${CYAN}8080${RESET}, ${CYAN}80${RESET}, ${CYAN}443${RESET}, ${CYAN}22${RESET} inbound"
echo -e "  3. Open ${CYAN}http://<public-ip>:8080${RESET} in browser"
echo -e "  4. Follow the 8-step setup wizard"
echo -e "  5. App is live — wizard stops itself automatically"
echo ""
