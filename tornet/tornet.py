#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# tornet - Automate IP address changes using Tor
# Author: Fidal
# Copyright (c) 2024 Fidal.
#
# Fork patch: Prefer RU exit nodes first; if RU exits are unavailable,
# fall back to other countries (or any exit) automatically by editing torrc.

import os
import sys
import time
import argparse
import requests
import subprocess
import signal
import shutil
import random

TOOL_NAME = "tornet"
VERSION = "2.2.1"

green = "\033[92m"
red = "\033[91m"
white = "\033[97m"
reset = "\033[0m"
cyan = "\033[36m"

def print_banner():
    """Print tool banner"""
    banner = f"""
{green}
████████╗ ██████╗ ██████╗ ███╗   ██╗███████╗████████╗
╚══██╔══╝██╔═══██╗██╔══██╗████╗  ██║██╔════╝╚══██╔══╝
   ██║   ██║   ██║██████╔╝██╔██╗ ██║█████╗     ██║
   ██║   ██║   ██║██╔══██╗██║╚██╗██║██╔══╝     ██║
   ██║   ╚██████╔╝██║  ██║██║ ╚████║███████╗   ██║
   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝
{white}                    Version: {VERSION}
{white} +---------------------{cyan}({red}ByteBreach{cyan}){white}----------------------+{reset}
{white} +--------------{cyan}({red}Improved by Ayad Seghiri{cyan}){white}--------------------+{reset}
{reset}"""
    print(banner)

def log(msg: str):
    """Print info message"""
    print(f"{white} [{green}+{white}]{green} {msg}{reset}")

def error(msg: str, exit_code: int = 1):
    """Print error message and optionally exit"""
    print(f"{white} [{red}!{white}] {red}{msg}{reset}")
    if exit_code > 0:
        sys.exit(exit_code)

def warning(msg: str):
    """Print warning message"""
    print(f"{white} [{red}!{white}] {red}{msg}{reset}")

def is_root():
    """Check if running as root"""
    return os.geteuid() == 0

def has_sudo():
    """Check if sudo is available"""
    return shutil.which("sudo") is not None

def run_cmd(cmd, use_sudo=False, check=True):
    """Run command safely with optional sudo"""
    if use_sudo and not is_root():
        if not has_sudo():
            error("Root privileges required but sudo not available. Run as root or install sudo.", 2)
        cmd = ["sudo"] + cmd

    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
        return result
    except subprocess.CalledProcessError as e:
        if check:
            error(f"Command failed: {' '.join(cmd)}\nError: {e.stderr.strip()}")
        return e

def detect_service_manager():
    """Detect if systemd or sysv init is used"""
    if shutil.which("systemctl") and os.path.exists("/run/systemd/system"):
        return "systemctl"
    elif shutil.which("service"):
        return "service"
    return None

def service_action(action):
    """Perform service action (start/stop/reload) on tor"""
    service_mgr = detect_service_manager()

    if service_mgr == "systemctl":
        cmd = ["systemctl", action, "tor"]
    elif service_mgr == "service":
        cmd = ["service", "tor", action]
    else:
        error("No supported service manager found (systemctl or service)", 3)

    result = run_cmd(cmd, use_sudo=True, check=False)
    if result.returncode != 0:
        warning(f"Failed to {action} tor service: {result.stderr.strip()}")

def restart_tor_service():
    """Restart tor so torrc changes take effect."""
    service_mgr = detect_service_manager()
    if service_mgr == "systemctl":
        result = run_cmd(["systemctl", "restart", "tor"], use_sudo=True, check=False)
    elif service_mgr == "service":
        result = run_cmd(["service", "tor", "restart"], use_sudo=True, check=False)
    else:
        error("No supported service manager found (systemctl or service)", 3)

    if getattr(result, "returncode", 1) != 0:
        warning(f"Failed to restart tor service: {getattr(result, 'stderr', '').strip()}")

def detect_package_manager():
    """Detect available package manager"""
    managers = [
        ("apt", ["apt-get"]),
        ("dnf", ["dnf"]),
        ("yum", ["yum"]),
        ("pacman", ["pacman"]),
        ("apk", ["apk"]),
        ("zypper", ["zypper"])
    ]

    for pm, binaries in managers:
        if any(shutil.which(binary) for binary in binaries):
            return pm
    return None

def install_package(package_name):
    """Install system package using detected package manager"""
    pm = detect_package_manager()
    if not pm:
        error("No supported package manager found. Please install packages manually.", 4)

    if pm == "apt":
        run_cmd(["apt-get", "update"], use_sudo=True)
        run_cmd(["apt-get", "install", "-y", package_name], use_sudo=True)
    elif pm == "dnf":
        run_cmd(["dnf", "install", "-y", package_name], use_sudo=True)
    elif pm == "yum":
        run_cmd(["yum", "install", "-y", package_name], use_sudo=True)
    elif pm == "pacman":
        run_cmd(["pacman", "-Sy", "--noconfirm", package_name], use_sudo=True)
    elif pm == "apk":
        run_cmd(["apk", "add", package_name], use_sudo=True)
    elif pm == "zypper":
        run_cmd(["zypper", "--non-interactive", "install", package_name], use_sudo=True)

def ensure_pip():
    """Ensure pip is available"""
    try:
        subprocess.run([sys.executable, "-c", "import pip"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        log("pip not found, attempting to install...")

        # Try ensurepip first
        try:
            run_cmd([sys.executable, "-m", "ensurepip", "--upgrade"])
            return True
        except Exception:
            pass

        # Try system package manager
        try:
            pm = detect_package_manager()
            if pm == "apt":
                install_package("python3-pip")
            elif pm in ["dnf", "yum"]:
                install_package("python3-pip")
            elif pm == "pacman":
                install_package("python-pip")
            elif pm == "apk":
                install_package("py3-pip")
            elif pm == "zypper":
                install_package("python3-pip")
            return True
        except Exception:
            error("Failed to install pip. Please install pip manually.", 5)

def ensure_requests():
    """Ensure requests package is available"""
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        log("requests package not found, installing...")
        ensure_pip()
        try:
            run_cmd([sys.executable, "-m", "pip", "install", "requests", "requests[socks]"])
            return True
        except Exception:
            error("Failed to install requests package.", 6)

def is_tor_installed():
    """Check if tor binary is installed"""
    return shutil.which("tor") is not None

def ensure_tor():
    """Ensure tor is installed"""
    if is_tor_installed():
        return True

    log("tor not found, installing...")
    try:
        install_package("tor")
        return True
    except Exception:
        error("Failed to install tor. Please install tor manually.", 7)

def is_tor_running():
    """Check if tor process is running"""
    if shutil.which("pgrep"):
        try:
            subprocess.run(["pgrep", "-x", "tor"], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    # Fallback: check /proc
    try:
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    with open(f"/proc/{pid}/comm", "r") as f:
                        if f.read().strip() == "tor":
                            return True
                except Exception:
                    continue
    except Exception:
        pass

    return False

def get_current_ip():
    """Get current public IP address"""
    if is_tor_running():
        return get_ip_via_tor()
    else:
        return get_ip_direct()

def get_ip_via_tor():
    """Get IP address via Tor proxy"""
    url = 'https://api.ipify.org'
    proxies = {
        'http': 'socks5://127.0.0.1:9050',
        'https': 'socks5://127.0.0.1:9050'
    }
    try:
        response = requests.get(url, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        warning("Having trouble connecting to the Tor network. Please wait a moment.")
        return None

def get_ip_direct():
    """Get IP address directly (without Tor)"""
    try:
        response = requests.get('https://api.ipify.org', timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        warning("Having trouble fetching IP address. Please check your internet connection.")
        return None

def change_ip():
    """Change IP by reloading Tor service"""
    service_action("reload")
    time.sleep(2)  # Wait for new circuit
    return get_current_ip()

def print_ip(ip):
    """Print current IP address"""
    log(f"Your IP address is: {white}{ip}{reset}")

def change_ip_repeatedly(interval_str, count):
    """Change IP repeatedly with specified interval and count"""
    if count == 0:  # Infinite loop
        while True:
            try:
                sleep_time = parse_interval(interval_str)
                time.sleep(sleep_time)
                new_ip = change_ip()
                if new_ip:
                    print_ip(new_ip)
            except KeyboardInterrupt:
                break
    else:
        for _ in range(count):
            try:
                sleep_time = parse_interval(interval_str)
                time.sleep(sleep_time)
                new_ip = change_ip()
                if new_ip:
                    print_ip(new_ip)
            except KeyboardInterrupt:
                break

def parse_interval(interval_str):
    """Parse interval string (single number or range)"""
    try:
        if "-" in str(interval_str):
            start, end = map(int, str(interval_str).split("-", 1))
            return random.randint(start, end)
        else:
            return int(interval_str)
    except ValueError:
        error("Invalid interval format. Use number or range (e.g., '60' or '30-120')", 8)

def auto_fix():
    """Automatically fix dependencies"""
    log("Running auto-fix...")
    ensure_pip()
    ensure_requests()
    ensure_tor()
    log("Auto-fix complete")

def stop_services():
    """Stop tor service and tornet processes"""
    service_action("stop")
    try:
        subprocess.run(["pkill", "-f", TOOL_NAME], check=False, capture_output=True)
    except Exception:
        pass
    log(f"Tor services and {TOOL_NAME} processes stopped.")

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    stop_services()
    print(f"\n{white} [{red}!{white}] {red}Program terminated by user.{reset}")
    sys.exit(0)

def check_internet_connection():
    """Check if internet connection is available"""
    try:
        requests.get('http://www.google.com', timeout=5)
        return True
    except requests.RequestException:
        error("Internet connection required but not available.", 9)

def initialize_environment():
    """Initialize tor environment"""
    service_action("start")
    log("Tor service started. Please wait for Tor to establish connection.")
    log("Configure your browser to use Tor proxy (127.0.0.1:9050) for anonymity.")

# -----------------------------
# Tor exit-country preference
# -----------------------------

def detect_torrc_path(custom: str = ""):
    """Try to locate torrc in common distro paths."""
    if custom and os.path.isfile(custom):
        return custom

    candidates = [
        "/etc/tor/torrc",                 # Debian/Ubuntu, many distros
        "/etc/tor/torrc.default",         # some setups
        "/usr/local/etc/tor/torrc",       # custom installs
        "/etc/torrc",                     # rare/legacy
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

def set_tor_exit_policy(torrc_path: str, exit_nodes: str, strict: bool):
    """
    Update torrc with ExitNodes + StrictNodes.
    exit_nodes examples:
      "{ru}" or "{ru},{de},{nl}" or "" (empty = no ExitNodes line)
    """
    if not torrc_path:
        error("torrc file not found. Use --torrc /path/to/torrc", 20)

    try:
        with open(torrc_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        error(f"Failed to read torrc: {e}", 22)

    def is_policy_line(s: str) -> bool:
        s2 = s.strip()
        return s2.startswith("ExitNodes") or s2.startswith("StrictNodes")

    # Remove existing policy lines to avoid duplicates.
    new_lines = [ln for ln in lines if not is_policy_line(ln)]

    # Append our policy at the end for predictability.
    new_lines.append("\n# --- tornet exit policy ---\n")
    if exit_nodes.strip():
        new_lines.append(f"ExitNodes {exit_nodes.strip()}\n")
    new_lines.append(f"StrictNodes {'1' if strict else '0'}\n")

    try:
        with open(torrc_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        error(f"Failed to write torrc: {e}", 23)

def apply_prefer_ru_then_fallback(torrc_path: str, fallback_exits: str):
    """
    1) Try strict RU-only exits.
    2) If Tor doesn't come up (no IP via Tor), fall back to:
       - any exits (if fallback_exits == "any" or empty)
       - or a soft preference list (StrictNodes 0) for provided countries.
    """
    log("Trying STRICT Russia-only Tor exits (ExitNodes {ru}, StrictNodes 1)...")
    set_tor_exit_policy(torrc_path, "{ru}", strict=True)
    restart_tor_service()

    # Give Tor time to bootstrap after restart
    time.sleep(6)
    ip = get_ip_via_tor()
    if ip:
        log(f"Tor is up with RU exit (if available). Current Tor IP: {white}{ip}{reset}")
        return

    warning("RU-only exits not available (Tor didn't establish). Falling back...")
    fb = (fallback_exits or "").strip().lower()

    if fb == "any" or fb == "":
        # Allow any exit node.
        set_tor_exit_policy(torrc_path, "", strict=False)
    else:
        # Prefer specific countries, but do NOT force strictness (Tor may choose others if needed).
        countries = [c.strip().lower() for c in fb.split(",") if c.strip()]
        exit_nodes = ",".join([f"{{{c}}}" for c in countries])
        set_tor_exit_policy(torrc_path, exit_nodes, strict=False)

    restart_tor_service()
    time.sleep(6)
    ip2 = get_ip_via_tor()
    if ip2:
        log(f"Tor is up after fallback. Current Tor IP: {white}{ip2}{reset}")
    else:
        warning("Fallback also failed to establish Tor connectivity (Tor may be blocked).")

def main():
    """Main function"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)

    parser = argparse.ArgumentParser(description="TorNet - Automate IP address changes using Tor")
    parser.add_argument('--interval', type=str, default='60',
                        help='Time in seconds between IP changes (or range like "30-120")')
    parser.add_argument('--count', type=int, default=10,
                        help='Number of times to change IP. If 0, change IP indefinitely')
    parser.add_argument('--ip', action='store_true',
                        help='Display current IP address and exit')
    parser.add_argument('--auto-fix', action='store_true',
                        help='Automatically install missing dependencies')
    parser.add_argument('--stop', action='store_true',
                        help='Stop all Tor services and tornet processes')
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {VERSION}')

    # New: prefer RU then fallback
    parser.add_argument('--prefer-ru', action='store_true',
                        help='Try Russia (RU) exit nodes first; if unavailable, fallback automatically')
    parser.add_argument('--fallback-exits', type=str, default='de,nl,fr,pl,se,fi,lt,lv,ee',
                        help='Comma-separated fallback country codes. Use "any" to allow any exit country.')
    parser.add_argument('--torrc', type=str, default='',
                        help='Path to torrc (default: auto-detect common locations)')

    args = parser.parse_args()

    if args.stop:
        stop_services()
        return

    if args.ip:
        ip = get_current_ip()
        if ip:
            print_ip(ip)
        return

    if args.auto_fix:
        auto_fix()
        return

    # Check dependencies
    if not is_tor_installed():
        error("Tor is not installed. Run with --auto-fix to install automatically.", 10)

    try:
        import requests  # noqa: F401
    except ImportError:
        error("requests package not found. Run with --auto-fix to install automatically.", 11)

    check_internet_connection()
    print_banner()

    # Apply RU-first policy before starting Tor (edits torrc + restarts tor)
    if args.prefer_ru:
        torrc_path = detect_torrc_path(args.torrc)
        log(f"Using torrc: {torrc_path}")
        apply_prefer_ru_then_fallback(torrc_path, args.fallback_exits)

    initialize_environment()

    # Wait for tor to establish connection
    time.sleep(5)

    change_ip_repeatedly(args.interval, args.count)

if __name__ == "__main__":
    main()
