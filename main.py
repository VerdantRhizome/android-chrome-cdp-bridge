import json, subprocess, sys, time
from pathlib import Path
from zeroconf import Zeroconf, ServiceBrowser

CDP_PORT = 9333

def adb_connect(host: str, port: int) -> bool:
    result = subprocess.run(
        ["adb", "connect", f"{host}:{port}"], capture_output=True, text=True
    )
    return "connected" in result.stdout and "failed" not in result.stdout

def forward_cdp_port() -> bool:
    result = subprocess.run(
        ["adb", "forward", f"tcp:{CDP_PORT}", "localabstract:chrome_devtools_remote"],
        capture_output=True, text=True,
    )
    return result.returncode == 0

def discover_adb_service(timeout: int = 3):
    found_service = None

    def on_service_state_change(zeroconf, service_type, name, state_change):
        nonlocal found_service
        if state_change.name == "Added":
            info = zeroconf.get_service_info(service_type, name)
            if info:
                # Get the first IPv4 address
                addresses = info.parsed_addresses()
                if addresses:
                    found_service = (addresses[0], info.port)

    zc = Zeroconf()
    browser = ServiceBrowser(zc, "_adb-tls-connect._tcp.local.", handlers=[on_service_state_change])
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if found_service:
            break
        time.sleep(0.1)
    
    zc.close()
    return found_service

def setup_cdp():
    print("Scanning local network for ADB Wireless Debugging service...")
    service = discover_adb_service(timeout=4)
    
    connected = False
    
    if service:
        host, port = service
        print(f"Discovered ADB service at {host}:{port}. Attempting to connect...")
        if adb_connect(host, port):
            connected = True
        else:
            print("[error] Discovered service but failed to connect (ADB pairing may have expired).")
    else:
        print("[error] Could not find any ADB Wireless Debugging service on the network.")

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
                
                print("\nPairing complete! Re-scanning for the connection port...")
                service = discover_adb_service(timeout=5)
                if service:
                    host, port = service
                    if adb_connect(host, port):
                        connected = True
                else:
                    connect_port_str = input(
                        "Scan failed. Enter connect port (main Wireless debugging screen): "
                    ).strip()
                    if connect_port_str and adb_connect(host, int(connect_port_str)):
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
