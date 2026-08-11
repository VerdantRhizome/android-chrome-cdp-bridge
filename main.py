import json, subprocess, sys, time, os
from pathlib import Path
from zeroconf import Zeroconf, ServiceBrowser

CDP_PORT = int(os.environ.get("CDP_PORT", 9222))

def adb_connect(host: str, port: int) -> str | None:
    """Return the connected device serial (host:port) or None on failure."""
    result = subprocess.run(
        ["adb", "connect", f"{host}:{port}"], capture_output=True, text=True
    )
    out = (result.stdout or "") + (result.stderr or "")
    if "connected" in out and "failed" not in out:
        return f"{host}:{port}"
    print(f"[adb connect {host}:{port}] -> {out.strip()}")
    return None

def forward_cdp_port(serial: str | None = None) -> bool:
    # Use an explicit -s <serial> selector so an ambiguous "more than one
    # device/emulator" state cannot make the forward silently fail.
    #
    # IMPORTANT (don't be confused later): when connecting over Wireless
    # Debugging, the real Tab S9 (SM-X810) registers under the serial
    # "emulator-5554" -- `adb devices` shows it as `emulator-5554  device`
    # with product `gts9pwifieea`. It is NOT a phantom emulator. So a
    # discovered serial of "emulator-5554" IS the tablet; forward to it
    # normally. (A *true* phantom would be a leftover from `adb tcpip`.)
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["forward", f"tcp:{CDP_PORT}", "localabstract:chrome_devtools_remote"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[warn] adb forward failed: {result.stderr.strip() or result.stdout.strip()}")
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
    serial: str | None = None
    
    if service:
        host, port = service
        print(f"Discovered ADB service at {host}:{port}. Attempting to connect...")
        serial = adb_connect(host, port)
        if serial:
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
            pair_addr = input("Enter PAIRING IP:PORT shown (or press Enter to skip): ").strip()
            if pair_addr:
                code = input("Enter 6-digit code: ").strip()
                pair_res = subprocess.run(
                    ["adb", "pair", pair_addr],
                    input=code + "\n",
                    capture_output=True, text=True,
                )
                pair_out = (pair_res.stdout or "") + (pair_res.stderr or "")
                print(pair_out.strip())
                if "successfully paired" not in pair_out.lower():
                    print("[error] adb pair did not confirm success; pairing may have failed.")
                # Android tells you which CONNECT port to use after a successful pair.
                # Parse "connect with adb connect <host>:<port>" from the pair output,
                # falling back to the pairing host + a port you can type below.
                connect_host, connect_port = None, None
                for line in pair_out.splitlines():
                    if "adb connect" in line:
                        tok = line.split("adb connect")[-1].strip()
                        if ":" in tok:
                            connect_host, p = tok.rsplit(":", 1)
                            if p.isdigit():
                                connect_port = int(p)
                if connect_host is None:
                    connect_host = pair_addr.rsplit(":", 1)[0]

                print("\nPairing attempted. Now connecting to the CONNECT port...")
                if connect_port is None:
                    cp = input(
                        "Enter CONNECT port (main Wireless Debugging screen, NOT the pairing port): "
                    ).strip()
                    if cp.isdigit():
                        connect_port = int(cp)
                if connect_port is not None:
                    serial = adb_connect(connect_host, connect_port)
                    if serial:
                        connected = True
                else:
                    # last resort: re-scan via mDNS
                    service = discover_adb_service(timeout=5)
                    if service:
                        host, port = service
                        serial = adb_connect(host, port)
                        if serial:
                            connected = True
        else:
            print("Not connected, and no interactive TTY to prompt for pairing.")

    if connected:
        if forward_cdp_port(serial):
            print(f"[success] Forwarded Android Chrome CDP to localhost:{CDP_PORT}")
            print(f"You can now run 'hermes' and it will use this live browser.")
        else:
            print("[error] Failed to forward CDP port.")
    else:
        print("[error] Failed to connect ADB.")

def main() -> int:
    setup_cdp()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
