"""
Habilita embedding em todos os vídeos do canal EN via YouTube Data API.
Execução única — cron desabilitado por padrão.
"""
import os, sys, json, time
from google.oauth2.credentials import Credentials as YTCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")
CHANNEL_ID = "UCOGQwey2JXGvL8cqZ9tmCoQ"

creds = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds)

def listar_todos_videos():
    uploads_id = "UU" + CHANNEL_ID[2:]
    videos = []
    page_token = None
    print("Listando vídeos do canal EN...")
    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=page_token
        ).execute()
        for item in resp.get("items", []):
            videos.append(item["snippet"]["resourceId"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.3)
    print(f"  → {len(videos)} vídeos encontrados")
    return videos

def obter_status_videos(video_ids):
    """Busca privacyStatus de até 50 vídeos por vez."""
    status_map = {}
    for i in range(0, len(video_ids), 50):
        lote = video_ids[i:i+50]
        resp = youtube.videos().list(
            part="status",
            id=",".join(lote)
        ).execute()
        for item in resp.get("items", []):
            status_map[item["id"]] = item["status"]
        time.sleep(0.3)
    return status_map

def habilitar_embedding(video_id, privacy_status):
    try:
        youtube.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": privacy_status,
                    "embeddable": True,
                    "selfDeclaredMadeForKids": False,
                }
            }
        ).execute()
        return True
    except HttpError as e:
        print(f"  ❌ {video_id}: {e}")
        return False

def main():
    video_ids = listar_todos_videos()
    if not video_ids:
        print("Nenhum vídeo encontrado.")
        sys.exit(0)

    print("Verificando status de embedding...")
    status_map = obter_status_videos(video_ids)

    bloqueados = [
        vid for vid in video_ids
        if not status_map.get(vid, {}).get("embeddable", True)
    ]
    print(f"  → {len(bloqueados)} vídeos com embedding desabilitado")

    if not bloqueados:
        print("✅ Todos os vídeos já têm embedding habilitado.")
        sys.exit(0)

    ok = 0
    for vid in bloqueados:
        privacy = status_map[vid].get("privacyStatus", "public")
        if habilitar_embedding(vid, privacy):
            print(f"  ✅ {vid} ({privacy}) — embedding habilitado")
            ok += 1
        time.sleep(0.5)

    print(f"\n✅ Concluído: {ok}/{len(bloqueados)} vídeos atualizados.")

if __name__ == "__main__":
    main()
