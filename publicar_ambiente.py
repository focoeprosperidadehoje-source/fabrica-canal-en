"""Bloco 1 — Publicador Ambiente + Playlists — Canal EN"""
import os, json, time, datetime
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials as YTCredentials
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import gspread
from googleapiclient.discovery import build

GOOGLE_JSON      = os.environ.get("GOOGLE_CREDENTIALS")
YT_TOKEN_JSON    = os.environ.get("YOUTUBE_TOKEN_EN_JSON")
SHEET_ID         = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"
ABA              = "EN_AMBIENTE"
PLAYLIST_NOME    = "Catholic Sleep Music — Our Lady"

creds_sheets = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=['https://www.googleapis.com/auth/spreadsheets'])
gc = gspread.authorize(creds_sheets)
creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)

def obter_playlist():
    page_token = None
    while True:
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page_token).execute()
        for p in resp.get("items", []):
            if p["snippet"]["title"] == PLAYLIST_NOME: return p["id"]
        page_token = resp.get("nextPageToken")
        if not page_token: break
    r = youtube.playlists().insert(part="snippet,status", body={"snippet": {"title": PLAYLIST_NOME}, "status": {"privacyStatus": "public"}}).execute()
    print(f"  📂 Playlist criada: {r['id']}"); return r["id"]

def main():
    agora = datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))
    try: ws = gc.open_by_key(SHEET_ID).worksheet(ABA)
    except: print(f"Aba {ABA} não encontrada."); return
    registros = ws.get_all_records()
    if not registros: return
    playlist_id = obter_playlist()
    for i, row in enumerate(registros, start=2):
        if str(row.get('status','')).strip() != 'unlisted': continue
        video_id = str(row.get('video_id','')).strip()
        publish_at_str = str(row.get('publish_at','')).strip()
        if not video_id or not publish_at_str: continue
        try:
            publish_at = datetime.datetime.strptime(publish_at_str, '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        except: continue
        if agora < publish_at:
            h = int((publish_at - agora).total_seconds() // 3600)
            print(f"  ⏳ {video_id} — {h}h restantes"); continue
        for t in range(3):
            try:
                youtube.videos().update(part="status", body={"id": video_id, "status": {"privacyStatus": "public"}}).execute()
                col = list(registros[0].keys()).index('status') + 1
                ws.update_cell(i, col, 'public')
                print(f"  ✅ {video_id} publicado")
                try: youtube.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute(); print("  📂 Playlist OK.")
                except Exception as e: print(f"  ⚠️  Playlist: {e}")
                break
            except Exception as e:
                print(f"  ⚠️  T{t+1}: {e}"); time.sleep(10)

if __name__ == "__main__":
    main()
