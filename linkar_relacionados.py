"""
Bloco 4 — Vídeos Relacionados — Canal EN
Env: GOOGLE_CREDENTIALS, YOUTUBE_TOKEN_EN_JSON
"""
import os, sys, json, time, datetime

from google.oauth2.credentials import Credentials as YTCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CANAL         = "EN"
CHANNEL_ID    = "UCOGQwey2JXGvL8cqZ9tmCoQ"
YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_EN_JSON")
MAX_VIDEOS    = 10
DIAS          = 30
MARKER        = "📌 More videos to help you:"
SECTION_HDR   = "📌 More videos to help you:\n"
COMMENT_TPL   = "🙏 May these videos also accompany you in prayer!\n{links}\n\nGod bless you 🕊️"
SNIPPET_OK    = {'title','description','tags','categoryId','defaultLanguage','defaultAudioLanguage'}

if not YT_TOKEN_JSON: print("❌ Token não encontrado."); sys.exit(1)
creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)

def obter_uploads():
    uploads_pid = 'UU' + CHANNEL_ID[2:]
    ids, page_token = [], None
    while len(ids) < 50:
        for _ in range(3):
            try:
                resp = youtube.playlistItems().list(
                    part='contentDetails', playlistId=uploads_pid, maxResults=50, pageToken=page_token
                ).execute(); break
            except Exception as e: print(f"[WARN] {e}"); time.sleep(10)
        else: break
        for item in resp.get('items', []): ids.append(item['contentDetails']['videoId'])
        page_token = resp.get('nextPageToken')
        if not page_token: break
    return ids[:50]

def main():
    print(f"\n🔗 Bloco 4 — Vídeos Relacionados — Canal {CANAL}")
    video_ids = obter_uploads()
    detalhes = {}
    for i in range(0, len(video_ids), 50):
        resp = youtube.videos().list(part='snippet,status', id=','.join(video_ids[i:i+50])).execute()
        for item in resp.get('items', []): detalhes[item['id']] = item
    publicos = [v for v in video_ids if detalhes.get(v, {}).get('status', {}).get('privacyStatus') == 'public']
    corte = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DIAS)
    recentes = [v for v in publicos if
                datetime.datetime.fromisoformat(detalhes[v]['snippet'].get('publishedAt','2020-01-01T00:00:00Z').replace('Z','+00:00')) >= corte]
    print(f"  → {len(recentes)} recentes públicos")
    processados = 0
    for video_id in recentes:
        if processados >= MAX_VIDEOS: break
        item = detalhes[video_id]
        titulo = item['snippet'].get('title','')
        desc = item['snippet'].get('description','')
        if MARKER in desc: continue
        outros = [v for v in publicos if v != video_id][:3]
        if len(outros) < 2: continue
        links = '\n\n'.join([f"▶ {detalhes[v]['snippet']['title'][:60]}\n   https://youtu.be/{v}" for v in outros if v in detalhes])
        nova_desc = desc.rstrip() + '\n\n' + SECTION_HDR + links
        snippet_limpo = {k: v for k, v in item['snippet'].items() if k in SNIPPET_OK}
        snippet_limpo['description'] = nova_desc
        print(f"\n  📹 {video_id} | {titulo[:50]}")
        for _ in range(3):
            try:
                youtube.videos().update(part='snippet', body={'id': video_id, 'snippet': snippet_limpo}).execute()
                print(f"  ✅ Descrição atualizada"); break
            except Exception as e: print(f"  ⚠️  update: {e}"); time.sleep(15)
        else: continue
        try:
            youtube.commentThreads().insert(part='snippet', body={'snippet': {'videoId': video_id, 'topLevelComment': {'snippet': {'textOriginal': COMMENT_TPL.format(links=links)}}}}).execute()
            print(f"  💬 Comentário postado")
        except Exception as e: print(f"  ⚠️  Comentário: {e}")
        processados += 1; time.sleep(3)
    print(f"\n🔗 Concluído — {processados} vídeos processados.")

if __name__ == "__main__":
    main()
