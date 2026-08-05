import json, re, subprocess, sys
from pathlib import Path

CDP_PORT = 9333

def get_local_ip() -> str:
    result = subprocess.run(["ifconfig", "wlan0"], capture_output=True, text=True)
    m = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
    return m.group(1) if m else ""

def adb_connect(host: str, port: int) -> bool:
    result = subprocess.run(
        ["adb", "connect", f"{host}:{port}"], capture_output=True, text=True
    )
    return "connected" in result.stdout and "failed" not in result.stdout

def adb_scan_ports(host: str, saved_port: int, radius: int = 10) -> int | None:
    candidates = sorted(
        set(range(max(1024, saved_port - radius), saved_port + radius + 1)),
        key=lambda p: abs(p - saved_port),
    )
    for port in candidates:
        if adb_connect(host, port):
            return port
    return None

def forward_cdp_port() -> bool:
    result = subprocess.run(
        ["adb", "forward", f"tcp:{CDP_PORT}", "localabstract:chrome_devtools_remote"],
        capture_output=True, text=True,
    )
    return result.returncode == 0

def load_config(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"adb_host": "", "adb_port": 0}

def save_config(cfg: dict, path: Path) -> None:
    path.write_text(json.dumps(cfg, indent=2))

def setup_cdp():
    cfg_path = Path("config.json")
    cfg = load_config(cfg_path)
    
    connected = False
    current_ip = get_local_ip() or cfg.get("adb_host", "")
    if current_ip:
        if cfg.get("adb_port") and adb_connect(current_ip, cfg["adb_port"]):
            cfg["adb_host"] = current_ip
            save_config(cfg, cfg_path)
            connected = True
        else:
            port = adb_scan_ports(current_ip, cfg.get("adb_port") or 42000)
            if port:
                cfg["adb_host"] = current_ip
                cfg["adb_port"] = port
                save_config(cfg, cfg_path)
                connected = True

    if not connected:
        if sys.stdin.isatty():
            print("\nADB connection failed. On your phone:")
            print("  Settings → Developer Options → Wireless debugging")
            print("  → 'Pair device with pairing code'")
            pair_addr = input("Enter IP:PORT shown (or press Enter to skip): ").strip()
            if pair_addr:
                code = input("Enter 6-digit code: ").strip()
                subprocess.run(
                    ["adb", "pair", pair_addr], input=code,
                    capture_output=True, text=True,
                )
                host, _ = pair_addr.rsplit(":", 1)
                connect_port_str = input(
                    "Enter connect port (main Wireless debugging screen): "
                ).strip()
                if connect_port_str and adb_connect(host, int(connect_port_str)):
                    cfg["adb_host"] = host
                    cfg["adb_port"] = int(connect_port_str)
                    save_config(cfg, cfg_path)
                    connected = True
        else:
            print("Not connected, and no interactive TTY to prompt for pairing.")

    if connected:
        if forward_cdp_port():
            print(f"[success] Forwarded Android Chrome CDP to localhost:{CDP_PORT}")
            print(f"You can now run 'hermes' and it will use this live browser.")
        else:
            print("[error] Failed to forward CDP port.")
    else:
        print("[error] Failed to connect ADB.")

if __name__ == "__main__":
    setup_cdp()
