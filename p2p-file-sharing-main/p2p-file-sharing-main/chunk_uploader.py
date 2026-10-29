import socket
import json
import os
import random
import base64
import threading
import pyDes
from datetime import datetime

TCP_PORT = 6001
CHUNKS_DIR = "my_chunks"
SHARED_DIR = "shared"
UPLOAD_LOG = f"{SHARED_DIR}/upload_log.txt"
CONN_TIMEOUT = 30
MAX_MSG_SIZE = 10 * 1024 * 1024  # 10 MB

p = 907
g = 7


def get_username():
    try:
        with open(f"{SHARED_DIR}/my_username.txt") as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def load_ip_to_name():
    try:
        with open(f"{SHARED_DIR}/ip_to_name.json") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def make_des_key(shared_secret_int: int) -> bytes:
    return str(shared_secret_int).zfill(8)[:8].encode('utf-8')


def recv_message(conn: socket.socket) -> str:
    data = b""
    while len(data) < MAX_MSG_SIZE:
        part = conn.recv(4096)
        if not part:
            break
        data += part
        try:
            json.loads(data.decode())
            break
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    if len(data) >= MAX_MSG_SIZE:
        raise ValueError("Message exceeds size limit")
    return data.decode()


def safe_chunk_path(chunk_name: str) -> str | None:
    chunks_root = os.path.realpath(CHUNKS_DIR)
    candidate = os.path.realpath(os.path.join(CHUNKS_DIR, chunk_name))
    if not candidate.startswith(chunks_root + os.sep):
        return None
    return candidate


def handle_client(conn: socket.socket, addr: tuple) -> None:
    conn.settimeout(CONN_TIMEOUT)
    ip = addr[0]
    ip_to_name = load_ip_to_name()
    requester_name = ip_to_name.get(ip, ip)
    shared_secret = None

    try:
        raw = recv_message(conn)
        message = json.loads(raw)

        if "key" in message:
            their_A = int(message["key"])
            b = random.randint(2, p - 2)
            B = pow(g, b, p)
            conn.sendall(json.dumps({"key": str(B)}).encode())
            shared_secret = pow(their_A, b, p)

            raw = recv_message(conn)
            message = json.loads(raw)

        if "requested secured content" in message:
            if not isinstance(shared_secret, int):
                conn.sendall(json.dumps({"error": "key exchange required"}).encode())
                return

            chunk_name = message["requested secured content"]
            chunk_path = safe_chunk_path(chunk_name)
            if chunk_path is None:
                conn.sendall(json.dumps({"error": "invalid chunk name"}).encode())
                return

            print(f"[UPLOADER] {requester_name} requested (SECURE): '{chunk_name}'")

            if not os.path.exists(chunk_path):
                conn.sendall(json.dumps({"error": "chunk not found"}).encode())
                return

            with open(chunk_path, "rb") as f:
                raw_bytes = f.read()

            des_key = make_des_key(shared_secret)
            encrypted_bytes = pyDes.des(
                des_key, pyDes.ECB, pad=None, padmode=pyDes.PAD_PKCS5
            ).encrypt(raw_bytes)
            encoded_str = base64.b64encode(encrypted_bytes).decode('utf-8')  # type: ignore[arg-type]

            conn.sendall(json.dumps({
                "chunk name": chunk_name,
                "encrypted chunk": encoded_str
            }).encode())

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(UPLOAD_LOG, "a") as f:
                f.write(f"{timestamp} | {chunk_name} | {requester_name} | SENT\n")

            print(f"[UPLOADER] '{chunk_name}' encrypted and sent to {requester_name}")

        elif "requested content" in message:
            chunk_name = message["requested content"]
            chunk_path = safe_chunk_path(chunk_name)
            if chunk_path is None:
                conn.sendall(json.dumps({"error": "invalid chunk name"}).encode())
                return

            print(f"[UPLOADER] {requester_name} requested (PLAIN): '{chunk_name}'")

            if not os.path.exists(chunk_path):
                conn.sendall(json.dumps({"error": "chunk not found"}).encode())
                return

            with open(chunk_path, "rb") as f:
                raw_bytes = f.read()

            json_safe = base64.b64encode(raw_bytes).decode('utf-8')
            conn.sendall(json.dumps({
                "chunk name": chunk_name,
                "data": json_safe
            }).encode())

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(UPLOAD_LOG, "a") as f:
                f.write(f"{timestamp} | {chunk_name} | {requester_name} | SENT\n")

            print(f"[UPLOADER] '{chunk_name}' sent to {requester_name}")

    except (ValueError, json.JSONDecodeError, OSError, socket.timeout) as e:
        print(f"[UPLOADER] Error ({requester_name}): {e}")

    finally:
        conn.close()


def main():
    os.makedirs(SHARED_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", TCP_PORT))
    server.listen(10)

    print(f"[UPLOADER] Listening on TCP port {TCP_PORT}...")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    finally:
        server.close()


if __name__ == "__main__":
    main()
