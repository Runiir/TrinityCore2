"""One bounded local modern-login connection probe; it does not authenticate."""
import json
from pathlib import Path
import socket
import time


def main():
    output = Path.home() / ".local/share/trinity-client442-lab/evidence/login_transport_probe.json"
    with socket.socket() as server:
        server.bind(("127.0.0.1", 1119))
        server.listen(1)
        server.settimeout(45)
        print("Observing one client connection on 127.0.0.1:1119", flush=True)
        try:
            connection, address = server.accept()
        except TimeoutError:
            receipt = {"accepted": False, "reason": "no_connection_within_45_seconds"}
        else:
            with connection:
                connection.settimeout(5)
                header = connection.recv(6)
            receipt = {"accepted": True, "remote_address": address[0], "first_six_bytes_hex": header.hex(),
                       "tls_client_hello_record": header[:2] == b"\x16\x03",
                       "http_upgrade_request": header.startswith(b"GET "),
                       "legacy_grunt_challenge": header[:1] == b"\0"}
    receipt.update({"schema": "client442_login_transport_probe_v1", "timestamp_unix": time.time(),
                    "endpoint": "127.0.0.1:1119", "authenticated": False,
                    "purpose": "classify_first_record_only_without_reading_login_credentials"})
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
