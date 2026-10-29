# Project Report — P2P Chunk-Based File Sharing

---

## Development Platform

Development was carried out across **Linux Mint**, **Windows 11 Pro**, and **macOS**.  
All testing was performed on a local network using Python 3.12 (Linux Mint) and Python 3.14.5 (Windows 11 Pro).

Cross-platform transfer was verified between a Linux Mint machine (`192.168.1.26`) and a Windows 11 Pro machine (`192.168.1.6`) on the same home Wi-Fi network. The Linux downloader successfully retrieved all three chunks from the Windows uploader over TCP.

---

## Group Members & Division of Workload

| Member | Responsibilities |
|---|---|
| **Okan Ünal** | Implemented `chunk_uploader.py` and `chunk_downloader.py` — the full TCP transfer layer including the Diffie-Hellman handshake and DES encryption/decryption on both sides. |
| **Betül Nur Uzan** | Implemented `content_discovery.py` and `chunk_announcer.py` — the UDP broadcast mechanism, peer discovery logic, and the file-splitting routine. |
| **Barış Ortaabali** | Wrote `test_p2p.py` (33-check integration test suite), handled system integration across all modules, and prepared project documentation. |

---

## Challenges Faced

**1. TCP message boundaries**  
TCP is a stream protocol — it doesn't tell you where one message ends and the next begins. A chunk response could arrive split across several `recv()` calls with no way to know if you have the full thing yet. We fixed this by buffering incoming bytes and retrying `json.loads()` after each receive until it parsed cleanly.

**2. Thread safety in discovery**  
Multiple peers broadcast simultaneously, so the discovery module gets hit from several directions at once. We ran into race conditions when writing the JSON files and had to protect the shared state with a `threading.Lock`.

**3. Deriving a DES key from the DH shared secret**  
DES requires exactly 8 bytes as a key. Our Diffie-Hellman shared secret is just a small integer, so we had to decide how to turn it into a fixed-length byte sequence. We went with zero-padding it as a decimal string and slicing to 8 characters — straightforward, but both sides had to produce the exact same result.

**4. We had the wrong broadcast address the whole time**  
For a while, peers just weren't discovering each other and we couldn't figure out why. Turned out `BROADCAST_IP` in `chunk_announcer.py` didn't match our actual subnet. During development at home we used `192.168.1.255` (subnet `192.168.1.0/24`), but the university network sits on a different subnet and needs `10.20.255.255`. We kept forgetting to switch and burning time on it each time. The fix is trivial — one line — but it's easy to miss if you don't know what to look for. We noted it in the README so it's clear.

**5. It was the firewall**  
Chunk requests were silently timing out on Windows and we spent way too long looking at the code before someone thought to check the firewall. TCP 6001 and UDP 6000 were both blocked. We had to open a PowerShell window as administrator and add inbound rules manually:

```powershell
New-NetFirewallRule -DisplayName "P2P TCP 6001" -Direction Inbound -Protocol TCP -LocalPort 6001 -Action Allow
New-NetFirewallRule -DisplayName "P2P UDP 6000" -Direction Inbound -Protocol UDP -LocalPort 6000 -Action Allow
```

Once those were in, everything worked immediately. On Linux this was never an issue.

**6. Working across different operating systems**  
We each used a different OS during development — Linux Mint, Windows 11, and macOS. Small things kept catching us off guard: on Linux the interpreter is `python3`, on Windows it's `python`; file path separators behave differently; and the firewall situation on Windows didn't exist on Linux at all. Nothing critical, but it added friction throughout and meant we couldn't always reproduce each other's bugs right away.
