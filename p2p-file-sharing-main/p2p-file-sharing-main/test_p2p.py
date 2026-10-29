#!/usr/bin/env python3
"""
Integration test for P2P File Sharing.
Run from inside p2p_project/:  python3 test_p2p.py

Tests all core functionality without needing a real LAN:
  1. File splitting (chunk names, sizes)
  2. Content discovery (dict values are usernames, not IPs)
  3. Unsecure TCP transfer (uploader serves plain chunk)
  4. Secure TCP transfer (DH key exchange + DES encrypt/decrypt)
  5. View-contents parsing (chunk name → file name)
  6. Log file format (SENT / RECEIVED fields)
"""

import os, sys, json, time, socket, threading, base64, random
import pyDes

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── counters ───────────────────────────────────────────────────
PASS = FAIL = 0

def check(label, condition):
    global PASS, FAIL
    mark = "✓" if condition else "✗"
    print(f"  {mark}  {label}")
    if condition:
        PASS += 1
    else:
        FAIL += 1

def section(title):
    print(f"\n{'─'*52}")
    print(f"  {title}")
    print(f"{'─'*52}")

# ── shared dirs / test data ────────────────────────────────────
TEST_FILE   = "shared/_test_image.png"
TEST_PORT   = 16001   # avoids conflict with real uploader on 6001
TEST_DATA   = bytes(range(256)) * 8   # 2 048 bytes — deterministic content

def setup():
    for d in ("my_chunks", "shared", "downloads"):
        os.makedirs(d, exist_ok=True)
    with open(TEST_FILE, "wb") as f:
        f.write(TEST_DATA)
    with open("shared/my_username.txt", "w") as f:
        f.write("Alice")
    with open("shared/ip_to_name.json", "w") as f:
        json.dump({"127.0.0.1": "Bob"}, f)
    with open("shared/name_to_ip.json", "w") as f:
        json.dump({"Bob": "127.0.0.1"}, f)

def teardown():
    for path in [TEST_FILE,
                 "shared/_test_image 1", "shared/_test_image 2", "shared/_test_image 3",
                 "shared/upload_log.txt", "shared/download_log.txt"]:
        try: os.remove(path)
        except OSError: pass
    for i in (1, 2, 3):
        try: os.remove(f"my_chunks/_test_image {i}")
        except OSError: pass

# ── TCP helper ─────────────────────────────────────────────────
def recv_json(sock: socket.socket) -> dict:
    """Read until a complete JSON object arrives."""
    sock.settimeout(8)
    buf = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        try:
            return json.loads(buf.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    raise RuntimeError("Connection closed before complete JSON received")

# ── mini uploader server on TEST_PORT ─────────────────────────
def start_uploader(port: int = TEST_PORT):
    import chunk_uploader
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(10)
    srv.settimeout(15)

    def serve():
        try:
            while True:
                try:
                    conn, addr = srv.accept()
                    threading.Thread(
                        target=chunk_uploader.handle_client,
                        args=(conn, addr), daemon=True
                    ).start()
                except socket.timeout:
                    break
        finally:
            srv.close()

    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.15)   # let the socket bind


# ══════════════════════════════════════════════════════════════
# Test 1 — File Splitting
# ══════════════════════════════════════════════════════════════
def test_split():
    section("Test 1 · File Splitting")
    from chunk_announcer import split_file

    names = split_file(TEST_FILE)

    check("exactly 3 chunks produced",          len(names) == 3)
    check("chunk names use space (not _)",       all(" " in n for n in names))
    check("chunk 1 ends with ' 1'",             names[0].endswith(" 1"))

    reassembled = b""
    for n in names:
        path = os.path.join("my_chunks", n)
        check(f"chunk file exists: {n}",        os.path.exists(path))
        with open(path, "rb") as f:
            reassembled += f.read()

    check("reassembled data == original",       reassembled == TEST_DATA)

    # Return the base name for later tests (e.g. "_test_image")
    return names[0].rsplit(" ", 1)[0]


# ══════════════════════════════════════════════════════════════
# Test 2 — Content Discovery dict values
# ══════════════════════════════════════════════════════════════
def test_discovery():
    section("Test 2 · Content Discovery (username storage)")
    import content_discovery as cd

    with cd.lock:
        cd.ip_to_username["10.0.0.2"] = "Eve"
        cd.username_to_ip["Eve"] = "10.0.0.2"
        for chunk in ["flower 1", "flower 2", "flower 3"]:
            cd.content_dict.setdefault(chunk, [])
            if "Eve" not in cd.content_dict[chunk]:
                cd.content_dict[chunk].append("Eve")
        cd.save_dicts()

    saved = json.load(open("shared/content_dict.json"))
    check("content_dict value is username, not IP",   saved.get("flower 1") == ["Eve"])

    ip_map = json.load(open("shared/ip_to_name.json"))
    check("ip_to_name maps IP → username",            ip_map.get("10.0.0.2") == "Eve")

    nm_map = json.load(open("shared/name_to_ip.json"))
    check("name_to_ip maps username → IP",            nm_map.get("Eve") == "10.0.0.2")


# ══════════════════════════════════════════════════════════════
# Test 3 — Unsecure TCP Transfer
# ══════════════════════════════════════════════════════════════
def test_unsecure(base_name: str):
    section("Test 3 · Unsecure TCP Transfer")

    chunk_name = f"{base_name} 1"
    chunk_size = (len(TEST_DATA) + 2) // 3
    expected   = TEST_DATA[:chunk_size]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", TEST_PORT))
    sock.sendall(json.dumps({"requested content": chunk_name}).encode())

    resp = recv_json(sock)
    sock.close()

    check('no "error" in response',                 "error" not in resp)
    check('response has key "chunk name"',          "chunk name" in resp)
    check('response has key "data"',                "data" in resp)
    check("received chunk name matches request",    resp.get("chunk name") == chunk_name)

    received = base64.b64decode(resp.get("data", ""))
    check("data decodes to correct bytes",          received == expected)


# ══════════════════════════════════════════════════════════════
# Test 4 — Secure TCP Transfer (DH + DES)
# ══════════════════════════════════════════════════════════════
def test_secure(base_name: str):
    section("Test 4 · Secure TCP Transfer (DH p=907 g=7 + DES)")

    p, g = 907, 7
    chunk_name = f"{base_name} 1"
    chunk_size = (len(TEST_DATA) + 2) // 3
    expected   = TEST_DATA[:chunk_size]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", TEST_PORT))

    # ── DH handshake ──────────────────────────────────────────
    a = random.randint(2, p - 2)
    A = pow(g, a, p)
    sock.sendall(json.dumps({"key": str(A)}).encode())

    key_resp = recv_json(sock)
    check('server replied with "key" field',        "key" in key_resp)

    B = int(key_resp["key"])
    check("server public key B is in range (0, p)", 0 < B < p)

    shared = pow(B, a, p)
    check("shared secret computed (> 0)",           shared > 0)
    check("shared secret in valid range (< p)",     shared < p)

    # ── content request ───────────────────────────────────────
    sock.sendall(json.dumps({"requested secured content": chunk_name}).encode())
    resp = recv_json(sock)
    sock.close()

    check('no "error" in response',                 "error" not in resp)
    check('response has key "chunk name"',          "chunk name" in resp)
    check('response has key "encrypted chunk"',     "encrypted chunk" in resp)

    # ── decrypt ───────────────────────────────────────────────
    des_key = str(shared).zfill(8)[:8].encode("utf-8")
    enc_bytes = base64.b64decode(resp.get("encrypted chunk", ""))
    decrypted = pyDes.des(
        des_key, pyDes.ECB, pad=None, padmode=pyDes.PAD_PKCS5
    ).decrypt(enc_bytes)

    check("decrypted data matches original chunk",  decrypted == expected)


# ══════════════════════════════════════════════════════════════
# Test 5 — View Contents (chunk name → file name)
# ══════════════════════════════════════════════════════════════
def test_view_contents():
    section("Test 5 · View Contents (chunk name → file name)")

    # Inject a fresh content dict
    with open("shared/content_dict.json", "w") as f:
        json.dump({
            "forest 1": ["Alice"],
            "forest 2": ["Alice"],
            "forest 3": ["Bob"],
            "flower 1": ["Bob"],
        }, f)

    from chunk_downloader import load_dicts
    _, _, cd = load_dicts()

    file_names = set()
    for chunk_name in cd:
        parts = chunk_name.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            file_names.add(parts[0])
        else:
            file_names.add(chunk_name)

    check('"forest 1/2/3" collapses to "forest"',  "forest" in file_names)
    check('"flower 1" collapses to "flower"',       "flower" in file_names)
    check("only 2 unique file names",               len(file_names) == 2)
    check("no raw chunk names remain",
          not any(n[-2:] in (" 1"," 2"," 3") for n in file_names))


# ══════════════════════════════════════════════════════════════
# Test 6 — Log file format
# ══════════════════════════════════════════════════════════════
def test_logs():
    section("Test 6 · Log File Format")

    dl = "shared/download_log.txt"
    ul = "shared/upload_log.txt"

    # upload log is written by the uploader during TCP tests
    check("upload_log.txt was created",   os.path.exists(ul))
    if os.path.exists(ul):
        line = open(ul).readline().strip()
        parts = line.split(" | ")
        check("upload log: 4 pipe-delimited fields",  len(parts) == 4)
        check("upload log: last field is SENT",        parts[-1] == "SENT")

    # download log is written by download_chunk(); write a sample entry to verify format
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(dl, "a") as f:
        f.write(f"{ts} | forest 1 | Bob (10.0.0.1) | RECEIVED\n")
    check("download_log.txt was created", os.path.exists(dl))
    last = open(dl).readlines()[-1].strip()
    parts = last.split(" | ")
    check("download log: 4 pipe-delimited fields",    len(parts) == 4)
    check("download log: last field is RECEIVED",     parts[-1] == "RECEIVED")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("P2P File Sharing — Integration Tests")
    print("=" * 52)

    setup()
    base_name = test_split()
    test_discovery()

    print("\n  [starting mini uploader on 127.0.0.1:16001 ...]")
    start_uploader(TEST_PORT)

    test_unsecure(base_name)
    test_secure(base_name)
    test_view_contents()
    test_logs()
    teardown()

    print(f"\n{'═'*52}")
    result = "ALL PASSED" if FAIL == 0 else f"{FAIL} FAILED"
    print(f"  Result: {PASS} passed, {FAIL} failed  —  {result}")
    print("═" * 52)
    sys.exit(0 if FAIL == 0 else 1)
