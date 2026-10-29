# P2P Chunk-Based File Sharing

A peer-to-peer file sharing system for our Network Programming course. Files are split into 3 chunks and shared across peers on a local network using UDP broadcasts. Downloads can be plain or encrypted using DES over a Diffie-Hellman key exchange.

## Requirements

```
pip install pyDes
```

Python 3.10+ required. On Linux use `pip3` and `python3`; on Windows `pip` and `python` should work if Python is in your PATH.

## How to Run

Open 4 terminals and `cd` into the project folder in each one. Start them in this order — discovery and uploader need to be listening before anything is announced or downloaded.

**Terminal 1 — Discovery (start first):**
```
python3 content_discovery.py
```

**Terminal 2 — Uploader (start second):**
```
python3 chunk_uploader.py
```

**Terminal 3 — Announcer:**
```
python3 chunk_announcer.py
```
It will ask for your username and the path to a file you want to share. The file gets split into 3 chunks automatically.

**Terminal 4 — Downloader:**
```
python3 chunk_downloader.py
```

In the downloader menu: `1` to view available files, `2` to download (you'll be asked whether to use encryption).

## Notes

- **Broadcast IP:** `BROADCAST_IP` in `chunk_announcer.py` must match your subnet's broadcast address. At home on a typical `192.168.1.0/24` network this is `192.168.1.255`; on the university network it's `10.20.255.255`. If peers can't see each other, this is the first thing to check.
- All peers must be on the same LAN.
- **Windows firewall:** TCP 6001 and UDP 6000 are blocked by default. Open an admin PowerShell and run:
  ```powershell
  New-NetFirewallRule -DisplayName "P2P TCP 6001" -Direction Inbound -Protocol TCP -LocalPort 6001 -Action Allow
  New-NetFirewallRule -DisplayName "P2P UDP 6000" -Direction Inbound -Protocol UDP -LocalPort 6000 -Action Allow
  ```
- Files are always split into exactly 3 chunks.
- Peer list resets every 60 seconds, so seeders must stay running.
