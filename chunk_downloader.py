import socket
import json
import os
import random
import base64
import pyDes
from datetime import datetime

SHARED_DIR = "shared"
CHUNKS_DIR = "my_chunks"
DOWNLOADS_DIR = "downloads"
DOWNLOAD_LOG = f"{SHARED_DIR}/download_log.txt"
TCP_PORT = 6001
CONN_TIMEOUT = 30
MAX_MSG_SIZE = 10 * 1024 * 1024  # 10 MB

p = 907
g = 7


def load_dicts():
    try:
        with open(f"{SHARED_DIR}/ip_to_name.json") as f:
            ip_to_name = json.load(f)
    except (OSError, json.JSONDecodeError):
        ip_to_name = {}

    try:
        with open(f"{SHARED_DIR}/name_to_ip.json") as f:
            name_to_ip = json.load(f)
    except (OSError, json.JSONDecodeError):
        name_to_ip = {}

    try:
        with open(f"{SHARED_DIR}/content_dict.json") as f:
            content_dict = json.load(f)
    except (OSError, json.JSONDecodeError):
        content_dict = {}

    return ip_to_name, name_to_ip, content_dict


def view_contents():
    _, _, content_dict = load_dicts()

    file_names = set()
    for chunk_name in content_dict.keys():
        parts = chunk_name.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            file_names.add(parts[0])
        else:
            file_names.add(chunk_name)

    if not file_names:
        print("\nNo content found in network.")
        return

    print("\n=== Available Contents ===")
    for name in sorted(file_names):
        print(f"  - {name}")
    print()


def make_des_key(shared_secret_int: int) -> bytes:
    return str(shared_secret_int).zfill(8)[:8].encode('utf-8')


def recv_all(sock: socket.socket) -> bytes:
    data = b""
    while len(data) < MAX_MSG_SIZE:
        part = sock.recv(65536)
        if not part:
            break
        data += part
        try:
            json.loads(data.decode())
            break
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    if len(data) >= MAX_MSG_SIZE:
        raise ValueError("Response exceeds size limit")
    return data


def diffie_hellman_client(sock: socket.socket) -> int:
    a = random.randint(2, p - 2)
    A = pow(g, a, p)

    sock.sendall(json.dumps({"key": str(A)}).encode())

    response = recv_all(sock)
    data = json.loads(response.decode())
    B = int(data["key"])
    return pow(B, a, p)


def download_chunk(ip: str, chunk_name: str, username: str, secure: bool) -> bytes | None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Requesting '{chunk_name}' from {username} ({ip})...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONN_TIMEOUT)
        sock.connect((ip, TCP_PORT))

        shared_secret = None

        if secure:
            shared_secret = diffie_hellman_client(sock)
            request = json.dumps({"requested secured content": chunk_name})
        else:
            request = json.dumps({"requested content": chunk_name})

        sock.sendall(request.encode())

        response_data = recv_all(sock)
        sock.close()

        response = json.loads(response_data.decode())

        if "error" in response:
            print(f"[DOWNLOADER] Error: {response['error']}")
            return None

        if secure:
            if shared_secret is None:
                raise ValueError("No shared secret after key exchange")
            encrypted_b64 = response.get("encrypted chunk", "")
            des_key = make_des_key(shared_secret)
            encrypted_bytes = base64.b64decode(encrypted_b64)
            chunk_data = pyDes.des(
                des_key, pyDes.ECB, pad=None, padmode=pyDes.PAD_PKCS5
            ).decrypt(encrypted_bytes)
        else:
            data_b64 = response.get("data", "")
            chunk_data = base64.b64decode(data_b64)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(DOWNLOAD_LOG, "a") as f:
            f.write(f"{timestamp} | {chunk_name} | {username} ({ip}) | RECEIVED\n")

        print(f"[DOWNLOADER] '{chunk_name}' successfully received from {username}")
        return chunk_data

    except (OSError, ValueError, KeyError, json.JSONDecodeError, socket.timeout) as e:
        print(f"[DOWNLOADER] Chunk [{chunk_name}] cannot be downloaded from {username}: {e}")
        return None


def combine_chunks(file_base: str, ext: str, chunk_data_list: list[bytes]) -> str:
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    output_path = f"{DOWNLOADS_DIR}/{file_base}{ext}"
    with open(output_path, "wb") as f:
        for data in chunk_data_list:
            f.write(data)
    return output_path


def download_content():
    ip_to_name, name_to_ip, content_dict = load_dicts()

    filename_input = input("Content name to download (e.g., forest or forest.png): ").strip()
    file_base, ext = os.path.splitext(filename_input)

    choice = input("Download securely? (yes/no): ").strip().lower()
    secure = choice in ("yes", "y")

    all_chunks_data: list[bytes | None] = []

    for i in range(1, 4):
        chunk_name = f"{file_base} {i}"
        usernames = content_dict.get(chunk_name, [])

        if not usernames:
            print(f"[DOWNLOADER] WARNING: No peers found for '{chunk_name}'!")
            all_chunks_data.append(None)
            continue

        chunk_data = None
        for username in usernames:
            ip = name_to_ip.get(username)
            if not ip:
                continue
            chunk_data = download_chunk(ip, chunk_name, username, secure)
            if chunk_data is not None:
                os.makedirs(CHUNKS_DIR, exist_ok=True)
                with open(f"{CHUNKS_DIR}/{chunk_name}", "wb") as f:
                    f.write(chunk_data)
                break

        if chunk_data is None:
            print(f"[DOWNLOADER] CHUNK {chunk_name.upper()} CANNOT BE DOWNLOADED FROM ONLINE PEERS.")

        all_chunks_data.append(chunk_data)

    if all(d is not None for d in all_chunks_data):
        output_path = combine_chunks(file_base, ext, [d for d in all_chunks_data if d is not None])
        print(f"\nFile successfully downloaded: {output_path}")
    else:
        print("\nDownload incomplete — some chunks are missing.")


def view_history():
    print("\n=== Transfer History ===")
    found = False

    if os.path.exists(DOWNLOAD_LOG):
        with open(DOWNLOAD_LOG) as f:
            content = f.read().strip()
        if content:
            print("-- Downloads --")
            print(content)
            found = True

    upload_log = f"{SHARED_DIR}/upload_log.txt"
    if os.path.exists(upload_log):
        with open(upload_log) as f:
            content = f.read().strip()
        if content:
            print("-- Uploads --")
            print(content)
            found = True

    if not found:
        print("No history yet.")


def main():
    os.makedirs(SHARED_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    while True:
        print("\n=== Chunk Downloader ===")
        print("1. View Contents")
        print("2. Download Content")
        print("3. History")
        print("4. Exit")

        choice = input("Select: ").strip()

        if choice == "1":
            view_contents()
        elif choice == "2":
            download_content()
        elif choice == "3":
            view_history()
        elif choice == "4":
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
