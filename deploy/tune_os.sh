#!/bin/bash
# ==============================================================================
# SCRIPT TỰ ĐỘNG TINH CHỈNH OS CHO CỤM VOICE WORKERS (TASK 4.1)
# ==============================================================================

set -e

echo "=== [XIAOZHI CLUSTER] Bắt đầu tinh chỉnh hệ điều hành Linux ==="

# 1. Thiết lập ulimit
ulimit -n 65535
if ! grep -q "nofile 65535" /etc/security/limits.conf 2>/dev/null; then
    echo "* soft nofile 65535" | sudo tee -a /etc/security/limits.conf
    echo "* hard nofile 65535" | sudo tee -a /etc/security/limits.conf
    echo "root soft nofile 65535" | sudo tee -a /etc/security/limits.conf
    echo "root hard nofile 65535" | sudo tee -a /etc/security/limits.conf
fi

# 2. Áp dụng sysctl cấu hình mạng
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/sysctl_tuning.conf" ]; then
    sudo cp "$SCRIPT_DIR/sysctl_tuning.conf" /etc/sysctl.d/99-xiaozhi-cluster.conf
    sudo sysctl --system
fi

echo "=== [XIAOZHI CLUSTER] Hoàn tất tinh chỉnh OS (ulimit 65535, somaxconn 8192, tcp_tw_reuse 1) ==="
