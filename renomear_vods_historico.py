#!/usr/bin/env python3
"""renomear_vods_historico.py — Canal EN — Our Lady"""

import os, json, re, time, sys
from datetime import datetime
import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

FUSO = pytz.timezone("America/New_York")

TEMAS = {
    0: "Our Lady — Protection & Spiritual Warfare",
    1: "Our Lady — Liberation & Deliverance",
    2: "Our Lady — Family Restoration",
    3: "Our Lady — Providence & Open Doors",
    4: "Our Lady — Healing & Mercy",
    5: "Our Lady — The Sacred Mantle",
    6: "Our Lady — Miracles & Gratitude",
}

NOMES_PLAYLIST = {
    0: "Our Lady — Protection & Spiritual Warfare",
    1: "Our Lady — Liberation & Deliverance",
    2: "Our Lady — Family Restoration",
    3: "Our Lady — Providence & Open Doors",
    4: "Our Lady — Healing & Mercy",
    5: "Our Lady — The Sacred Mantle",
    6: "Our Lady — Miracles & Gratitude",
}

token_raw = os.environ.get("YOUTUBE_TOKEN_EN", "").lstrip("﻿").strip()
if not token_raw:
    print("YOUTUBE_TOKEN_EN não encontrado.")
    sys.exit(1)

t = json.loads(token_raw)
creds = Credentials(
    token=t.get("access_token") or t.get("token"),
    refresh_token=t.get("refresh_token"),
    token_uri="https://oauth2.googleapis.com/token",
    client_id=t.get("client_id"),
    client_secret=t.get("client_secret"),
)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())

yt = build("youtube", "v3", credentials=creds)

PATTERN_GENERICO = re.compile(r"🔴|🟢|🔵|\bLIVE\b|EN VIVO|AO VIVO|EN DIRECT|IN DIRETTA|NA ŻYWO", re.IGNORECASE)

def garantir_playlists():
    existentes = {}
    token = None
    while True:
        resp = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        for p in resp.get("items", []):
            existentes[p["snippet"]["title"]] = p["id"]
        token = resp.get("nextPageToken")
        if not token:
            break
    ids = {}
    for wd, nome in NOMES_PLAYLIST.items():
        if nome in existentes:
            ids[str(wd)] = existentes[nome]
            print(f"  Playlist found: {nome} → {existentes[nome]}")
        else:
            r = yt.playlists().insert(
                part="snippet,status",
                body={"snippet": {"title": nome, "defaultLanguage": "en"}, "status": {"privacyStatus": "public"}},
            ).execute()
            ids[str(wd)] = r["id"]
            print(f"  Playlist CREATED: {nome} → {r['id']}")
    return ids

def ids_na_playlist(pid):
    ids = set()
    token = None
    while True:
        try:
            resp = yt.playlistItems().list(part="snippet", playlistId=pid, maxResults=50, pageToken=token).execute()
            for item in resp.get("items", []):
                ids.add(item["snippet"]["resourceId"]["videoId"])
            token = resp.get("nextPageToken")
            if not token:
                break
        except Exception:
            break
    return ids

print("\n=== Renaming historical VODs — Canal EN ===\n")
print("Ensuring thematic playlists...")
playlists = garantir_playlists()

print("\nListing completed live broadcasts...")
vods, token = [], None
while True:
    resp = yt.liveBroadcasts().list(part="id,snippet,status", broadcastStatus="completed", maxResults=50, pageToken=token).execute()
    vods.extend(resp.get("items", []))
    token = resp.get("nextPageToken")
    if not token:
        break
print(f"Total VODs: {len(vods)}")

renomeados = ja_ok = erros = 0
for vod in vods:
    vid = vod["id"]
    snip = vod["snippet"]
    titulo_atual = snip.get("title", "")
    dt_str = snip.get("actualStartTime") or snip.get("publishedAt") or snip.get("scheduledStartTime", "")
    try:
        dt_utc = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(FUSO)
    except Exception:
        dt_local = datetime.now(FUSO)

    wd = dt_local.weekday()
    tema = TEMAS[wd]
    h = dt_local.strftime("%I%p").lstrip("0").lower()
    titulo_novo = f"{tema} · {dt_local.strftime('%m/%d')} {h}"[:100]
    pid = playlists.get(str(wd))

    if PATTERN_GENERICO.search(titulo_atual):
        print(f"\n[{vid}] Renaming...")
        print(f"  FROM: {titulo_atual[:80]}")
        print(f"  TO:   {titulo_novo}")
        try:
            v_resp = yt.videos().list(part="snippet", id=vid).execute()
            if not v_resp.get("items"):
                print(f"  WARN: video {vid} not found — skipping")
                erros += 1
                continue
            v_snip = v_resp["items"][0]["snippet"]
            v_snip["title"] = titulo_novo
            yt.videos().update(part="snippet", body={"id": vid, "snippet": v_snip}).execute()
            renomeados += 1
            time.sleep(1)
        except Exception as e:
            print(f"  ERROR: {e}")
            erros += 1
    else:
        ja_ok += 1
        print(f"[{vid}] OK: {titulo_atual[:60]}")

    if pid:
        try:
            if vid not in ids_na_playlist(pid):
                yt.playlistItems().insert(
                    part="snippet",
                    body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}},
                ).execute()
                print(f"  → Added to thematic playlist wd={wd}")
                time.sleep(0.5)
        except Exception as e:
            print(f"  WARN playlist: {e}")

print(f"\n=== Done — EN: renamed={renomeados} ok={ja_ok} errors={erros} ===")
