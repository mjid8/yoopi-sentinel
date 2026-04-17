#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Yoopi Sentinel — one-shot installer
#  Supports: Ubuntu 20/22/24, Debian 11/12, CentOS 8, Rocky 9,
#            Fedora, Arch / Manjaro
#  Safe to re-run — every step is idempotent.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="https://github.com/mjid8/yoopi-sentinel.git"

# ── Colors ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓${NC}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC}  $*"; }
err()  { echo -e "${RED}  ✗  $*${NC}"; exit 1; }
info() { echo -e "${CYAN}  →${NC}  $*"; }
step() { echo -e "\n${BOLD}── $* ──────────────────────────────────────${NC}"; }

# ── OS detection ─────────────────────────────────────────────────
detect_os() {
    PKG_MGR=""
    OS_NAME="unknown"

    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        OS_NAME="${NAME:-unknown}"
        local id="${ID:-}"
        local like="${ID_LIKE:-}"

        case "$id" in
            ubuntu|debian|linuxmint|pop)
                PKG_MGR="apt" ;;
            centos|rhel|rocky|almalinux|ol)
                PKG_MGR=$(command -v dnf &>/dev/null && echo "dnf" || echo "yum") ;;
            fedora)
                PKG_MGR="dnf" ;;
            arch|manjaro|endeavouros|garuda)
                PKG_MGR="pacman" ;;
            *)
                # Fall back to ID_LIKE
                case "$like" in
                    *debian*|*ubuntu*)
                        PKG_MGR="apt" ;;
                    *rhel*|*centos*|*fedora*)
                        PKG_MGR=$(command -v dnf &>/dev/null && echo "dnf" || echo "yum") ;;
                    *arch*)
                        PKG_MGR="pacman" ;;
                esac ;;
        esac
    fi

    if [ -z "$PKG_MGR" ]; then
        # Last resort: probe what's installed
        if   command -v apt-get &>/dev/null; then PKG_MGR="apt"
        elif command -v dnf     &>/dev/null; then PKG_MGR="dnf"
        elif command -v yum     &>/dev/null; then PKG_MGR="yum"
        elif command -v pacman  &>/dev/null; then PKG_MGR="pacman"
        else
            err "Cannot detect package manager. Install python3 and pip3 manually, then re-run."
        fi
    fi
}

# ── Package installer ─────────────────────────────────────────────
pkg_install() {
    local pkg="$1"
    info "Installing $pkg via $PKG_MGR..."
    case "$PKG_MGR" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y "$pkg"
            ;;
        dnf)
            sudo dnf install -y "$pkg"
            ;;
        yum)
            sudo yum install -y "$pkg"
            ;;
        pacman)
            sudo pacman -Sy --noconfirm "$pkg"
            ;;
    esac
}

# Map distro-generic names → real package names
pkg_name_python3() {
    case "$PKG_MGR" in
        pacman) echo "python" ;;
        *)      echo "python3" ;;
    esac
}

pkg_name_pip() {
    case "$PKG_MGR" in
        pacman) echo "python-pip" ;;
        *)      echo "python3-pip" ;;
    esac
}

# ── Step 1 — Python 3 ────────────────────────────────────────────
check_python() {
    step "Step 1/7  Python 3"
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 --version 2>&1)
        ok "python3 already installed  ($ver)"
    else
        warn "python3 not found — installing..."
        pkg_install "$(pkg_name_python3)"
        ok "python3 installed"
    fi
}

# ── Step 2 — pip ─────────────────────────────────────────────────
check_pip() {
    step "Step 2/7  pip"
    if command -v pip3 &>/dev/null; then
        ok "pip3 already installed"
    else
        warn "pip3 not found — installing..."
        pkg_install "$(pkg_name_pip)"
        ok "pip3 installed"
    fi
}

# ── Step 3 — Install yoopi-sentinel ──────────────────────────────
install_sentinel() {
    step "Step 3/7  Install yoopi-sentinel"

    if command -v sentinel &>/dev/null && \
       sentinel --version &>/dev/null 2>&1; then
        warn "sentinel is already installed — reinstalling to get latest version"
    fi

    info "Fetching from GitHub: ${REPO_URL}"

    # Try with --break-system-packages first (needed on Debian/Ubuntu 23+)
    if pip3 install "git+${REPO_URL}" \
            --break-system-packages \
            --force-reinstall \
            --quiet \
            2>/dev/null; then
        ok "Installed successfully"
    elif pip3 install "git+${REPO_URL}" \
            --force-reinstall \
            --quiet \
            2>/dev/null; then
        ok "Installed successfully (without --break-system-packages)"
    else
        # Show actual error on final attempt
        echo ""
        pip3 install "git+${REPO_URL}" --force-reinstall || true
        err "Installation failed. Check the output above for details."
    fi
}

# ── Step 4 — PATH ────────────────────────────────────────────────
ensure_path() {
    step "Step 4/7  PATH"
    local bin_dir="$HOME/.local/bin"
    local export_line="export PATH=\"\$HOME/.local/bin:\$PATH\""
    local bashrc="$HOME/.bashrc"

    # Always export for the current shell session
    export PATH="$bin_dir:$PATH"

    if grep -qF '.local/bin' "$bashrc" 2>/dev/null; then
        ok "~/.local/bin already in $bashrc"
    else
        {
            echo ""
            echo "# Added by Yoopi Sentinel installer"
            echo "$export_line"
        } >> "$bashrc"
        ok "Added ~/.local/bin to PATH in $bashrc"
    fi

    # Also check /etc/profile.d if running as root (system-wide install)
    if [ "$(id -u)" = "0" ] && [ -d /etc/profile.d ]; then
        if [ ! -f /etc/profile.d/sentinel-path.sh ]; then
            echo 'export PATH="/root/.local/bin:$PATH"' \
                | sudo tee /etc/profile.d/sentinel-path.sh > /dev/null
            ok "Written /etc/profile.d/sentinel-path.sh"
        fi
    fi
}

# ── Step 5 — Verify binary ───────────────────────────────────────
verify_binary() {
    step "Step 5/7  Verify"
    if command -v sentinel &>/dev/null; then
        ok "sentinel binary found at: $(command -v sentinel)"
    else
        warn "sentinel not found in PATH after install."
        warn "This usually means pip installed it to a directory not yet in your PATH."
        warn "Try: source ~/.bashrc  — then re-run this installer."
        err "Cannot continue without sentinel in PATH."
    fi
}

# ── Step 6 — sentinel init ───────────────────────────────────────
run_init() {
    step "Step 6/7  Configure"

    if [ -f sentinel.yml ]; then
        ok "Existing config found, skipping init — run 'sentinel init' manually to reconfigure"
        return
    fi

    echo ""
    info "Launching interactive setup wizard..."
    echo ""
    sentinel init
}

# ── Step 7 — systemd service ─────────────────────────────────────
offer_service_install() {
    step "Step 7/7  Systemd service"

    if ! command -v systemctl &>/dev/null; then
        warn "systemd not available on this system."
        info "To run Sentinel in the background you can use:"
        info "  nohup sentinel start --config sentinel.yml > /tmp/sentinel.log 2>&1 &"
        info "  — or run:  sentinel start --daemon"
        return
    fi

    echo ""
    if ask_yes_no "Install Sentinel as a systemd service (auto-start on boot)?" y; then
        echo ""
        if sudo -n true 2>/dev/null; then
            sudo sentinel install
        else
            warn "This step requires sudo to write the systemd service file."
            info "Run the following command to complete the setup:"
            echo ""
            echo "    sudo sentinel install"
            echo ""
        fi
    else
        ok "Skipping systemd install."
        info "You can set it up later with:  sudo sentinel install"
    fi
}

# ── Helper: yes/no prompt ─────────────────────────────────────────
# Usage: ask_yes_no "prompt" [non_interactive_default]
#   non_interactive_default: "y" or "n" (default "n")
#   When stdin is not a terminal the default is applied automatically.
ask_yes_no() {
    local prompt="$1"
    local noterm_default="${2:-n}"
    local reply

    if [ ! -t 0 ]; then
        echo -e "${CYAN}  ?${NC}  ${prompt} [y/n]  → ${noterm_default} (non-interactive)"
        [ "$noterm_default" = "y" ] && return 0 || return 1
    fi

    while true; do
        echo -en "${CYAN}  ?${NC}  ${prompt} [y/n] "
        read -r reply
        case "$reply" in
            [Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo])     return 1 ;;
            *) echo "    Please answer y or n." ;;
        esac
    done
}

# ── Summary ───────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗"
    echo -e "║   ✅  Yoopi Sentinel installed successfully!  ║"
    echo -e "╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Available commands:${NC}"
    echo ""
    echo -e "  ${GREEN}sentinel start${NC}              Start monitoring (foreground)"
    echo -e "  ${GREEN}sentinel start --daemon${NC}     Start monitoring (background)"
    echo -e "  ${GREEN}sentinel status${NC}             Quick terminal status check"
    echo -e "  ${GREEN}sentinel install${NC}            Install as systemd service"
    echo -e "  ${GREEN}sentinel update${NC}             Update to latest version"
    echo -e "  ${GREEN}sentinel init${NC}               Re-run setup wizard"
    echo ""
    echo -e "  ${YELLOW}Note:${NC} If 'sentinel' is not found, run:  source ~/.bashrc"
    echo ""
}

# ── Entry point ───────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BOLD}${CYAN}  ☀   Yoopi Sentinel — Installer${NC}"
    echo -e "  ${CYAN}https://github.com/mjid8/yoopi-sentinel${NC}"
    echo ""

    detect_os
    info "Detected OS: ${OS_NAME}  |  Package manager: ${PKG_MGR}"

    check_python
    check_pip
    install_sentinel
    ensure_path
    verify_binary
    run_init
    offer_service_install
    print_summary
}

main "$@"
