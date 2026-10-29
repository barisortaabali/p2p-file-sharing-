import socket
import json
import time
import threading
import os

UDP_PORT = 6000
SHARED_DIR = "shared"

ip_to_username = {}
username_to_ip = {}
content_dict = {}
lock = threading.Lock()


def save_dicts():
    with open(f"{SHARED_DIR}/ip_to_name.json", "w") as f:
        json.dump(ip_to_username, f)
    with open(f"{SHARED_DIR}/name_to_ip.json", "w") as f:
        json.dump(username_to_ip, f)
    with open(f"{SHARED_DIR}/content_dict.json", "w") as f:
        json.dump(content_dict, f)


def clear_dicts_periodically():
    global ip_to_username, username_to_ip, content_dict
    while True:
        time.sleep(60)
        with lock:
            ip_to_username.clear()
            username_to_ip.clear()
            content_dict.clear()
            save_dicts()
            print("[DISCOVERY] Dictionaries cleared (60 seconds elapsed)")


def listen():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", UDP_PORT))

    print(f"[DISCOVERY] Listening on UDP port {UDP_PORT}...")

    while True:
        data, addr = sock.recvfrom(65535)
        ip = addr[0]

        try:
            message = json.loads(data.decode())
            username = message.get("username", "unknown")
            chunks = message.get("chunks", [])

            with lock:
                ip_to_username[ip] = username
                username_to_ip[username] = ip

                for chunk in chunks:
                    if chunk not in content_dict:
                        content_dict[chunk] = []
                    if username not in content_dict[chunk]:
                        content_dict[chunk].append(username)

                save_dicts()

            print(f"[DISCOVERY] {username} : {', '.join(chunks)}")

        except json.JSONDecodeError:
            print(f"[DISCOVERY] Invalid JSON from {ip}")


def main():
    os.makedirs(SHARED_DIR, exist_ok=True)

    cleaner = threading.Thread(target=clear_dicts_periodically, daemon=True)
    cleaner.start()

    listen()


if __name__ == "__main__":
    main()