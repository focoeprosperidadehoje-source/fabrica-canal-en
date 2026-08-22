#!/usr/bin/env python3
"""
gerar_token_en.py — Generates youtube_token.json for Canal EN (live stream).
Run once on the VPS after initial setup.

Usage:
  cd /root/ao_vivo_en
  python3 gerar_token_en.py

The script shows a URL — open it in your browser, authorize with
canalinteligenciadivina@gmail.com choosing Canal EN,
paste the code back here. The token is saved automatically.
"""

import json
import os
import sys
from pathlib import Path

def _load_env(path: str):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_env("/root/ao_vivo_en/.env")

CLIENT_ID     = os.environ.get("YT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
SAVE_PATH     = Path("/root/ao_vivo_en/youtube_token.json")
SCOPES        = ["https://www.googleapis.com/auth/youtube"]

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: YT_CLIENT_ID or YT_CLIENT_SECRET missing from /root/ao_vivo_en/.env")
    print()
    print("Extract them from the ES token on the old VPS and add to .env:")
    print("  On VPS 80.241.213.27:")
    print("    python3 -c \"import json; d=json.load(open('/root/ao_vivo_es/youtube_token.json')); print('YT_CLIENT_ID=' + d.get('client_id','')); print('YT_CLIENT_SECRET=' + d.get('client_secret',''))\"")
    print()
    print("  Then on THIS VPS (169.58.220.233), add to /root/ao_vivo_en/.env:")
    print("    echo 'YT_CLIENT_ID=...' >> /root/ao_vivo_en/.env")
    print("    echo 'YT_CLIENT_SECRET=...' >> /root/ao_vivo_en/.env")
    sys.exit(1)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Installing google-auth-oauthlib...")
    import subprocess
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "google-auth-oauthlib"],
        check=True
    )
    from google_auth_oauthlib.flow import InstalledAppFlow

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

print("=" * 60)
print("YouTube Token Generator — Canal EN")
print("=" * 60)
print()
print("1. Copy the URL below and open in your browser")
print("2. Log in with canalinteligenciadivina@gmail.com")
print("3. Choose Canal EN when asked")
print("4. Authorize and copy the code shown")
print("5. Paste the code here and press Enter")
print()

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
print(f"URL to authorize:\n{auth_url}\n")
code = input("Paste the code here: ").strip()
flow.fetch_token(code=code)
creds = flow.credentials

SAVE_PATH.write_text(creds.to_json())
print()
print(f"✅ Token saved to {SAVE_PATH}")
print()
print("Next step — start the EN live:")
print("  systemctl start ao_vivo_en")
print("  systemctl status ao_vivo_en")
