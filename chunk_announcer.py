import socket
import json
import time
import os
import threading

BROADCAST_IP = "10.20.255.255"
BROADCAST_PORT = 6000
BROADCAST_INTERVAL = 8
CHUNKS_DIR = "my_chunks"
SHARED_DIR = "shared"


def split_file(filepath):
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    with open(filepath, 'rb') as f:
        data = f.read()

    total_size = len(data)
    chunk_size = (total_size + 2) // 3

    filename = os.path.splitext(os.path.basename(filepath))[0]
    chunk_names = []

    for i in range(3):
        start = i * chunk_size
        end = min(start + chunk_size, total_size)
        if start >= total_size:
            break
        chunk_data = data[start:end]
        chunk_name = f"{filename} {i+1}"
        chunk_path = os.path.join(CHUNKS_DIR, chunk_name)

        with open(chunk_path, 'wb') as f:
            f.write(chunk_data)

        chunk_names.append(chunk_name)

    return chunk_names


def get_all_chunks():
    if not os.path.exists(CHUNKS_DIR):
        return []
    return [f for f in os.listdir(CHUNKS_DIR)]


def broadcast_presence(username):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        chunks = get_all_chunks()
        message = json.dumps({"username": username, "chunks": chunks})
        sock.sendto(message.encode(), (BROADCAST_IP, BROADCAST_PORT))
        print(f"[ANNOUNCER] Broadcast sent: {chunks}")
        time.sleep(BROADCAST_INTERVAL)


def main():
    os.makedirs(SHARED_DIR, exist_ok=True)

    username = input("Enter your username: ").strip()
    filepath = input("Enter the path to your file: ").strip()

    if not os.path.exists(filepath):
        print("File not found!")
        return

    chunk_names = split_file(filepath)
    print(f"File split into {len(chunk_names)} chunks: {chunk_names}")
    print(f"Starting to announce as '{username}'...")

    with open(f"{SHARED_DIR}/my_username.txt", "w") as f:
        f.write(username)

    broadcast_presence(username)


if __name__ == "__main__":
    main()