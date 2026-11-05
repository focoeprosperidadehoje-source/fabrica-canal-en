"""
Bloco 3 — Thumbnail Updater — Canal EN
Env: GOOGLE_CREDENTIALS, YOUTUBE_TOKEN_EN_JSON, VIDEO_ID (opcional)
"""
import os, sys, json, time, datetime, re, textwrap, random

from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image, ImageDraw, ImageFont

GOOGLE_JSON     = os.environ.get("GOOGLE_CREDENTIALS")
YT_TOKEN_JSON   = os.environ.get("YOUTUBE_TOKEN_EN_JSON")
VIDEO_ID_UNICO  = os.environ.get("VIDEO_ID", "").strip()
CANAL           = "EN"
CHANNEL_ID      = "UCOGQwey2JXGvL8cqZ9tmCoQ"
PASTA_IMAGENS   = "1IyWdkNqdKQn8kDX-EWSEjKqOLNPEg6jk"
PASTA_TEMP      = "/tmp/thumbnail_b3"
DIAS_RETROATIVOS = 7

os.makedirs(PASTA_TEMP, exist_ok=True)

credenciais_dict = json.loads(GOOGLE_JSON)
creds_drive = Credentials.from_service_account_info(
    credenciais_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
)
drive_service = build('drive', 'v3', credentials=creds_drive)
creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)


def listar_imagens_drive():
    res, page_token = [], None
    while True:
        for _ in range(3):
            try:
                resp = drive_service.files().list(
                    q=f"'{PASTA_IMAGENS}' in parents and trashed=false",
                    spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token
                ).execute(); break
            except Exception as e: print(f"[WARN] Drive: {e}"); time.sleep(5)
        else: return res
        for f in resp.get('files', []):
            if f['name'].lower().endswith(('.jpg', '.jpeg', '.png')): res.append(f)
        page_token = resp.get('nextPageToken')
        if not page_token: break
    return res

def baixar_imagem(file_id, destino):
    for _ in range(3):
        try:
            req = drive_service.files().get_media(fileId=file_id)
            with open(destino, 'wb') as f: f.write(req.execute())
            return destino
        except Exception as e: print(f"[WARN] Download: {e}"); time.sleep(5)
    return None

def criar_thumbnail(img_path, titulo, destino):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720), Image.LANCZOS)
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle([(0, 400), (1280, 720)], fill=(0, 0, 0, 180))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        try: font_lg = ImageFont.truetype("Anton.ttf", 62); font_sm = ImageFont.truetype("Anton.ttf", 30)
        except: font_lg = font_sm = ImageFont.load_default()
        partes = re.split(r'\s*[—–]\s*', titulo, maxsplit=1)
        principal = re.sub(r'[^\x00-\x7FÀ-ÿ\w\s\.\!\?\,\:\;\-\(\)\[\]]', '', partes[0]).strip()
        subtitulo = re.sub(r'[^\x00-\x7FÀ-ÿ\w\s\.\!\?\,\:\;\-\(\)\[\]]', '', partes[1]).strip() if len(partes) > 1 else ''
        linhas = textwrap.wrap(principal, width=20)[:3]
        y = 420
        for i, linha in enumerate(linhas):
            cor = (255, 220, 80) if i == 0 else (235, 235, 235)
            bb = draw.textbbox((0, 0), linha, font=font_lg)
            x = (1280 - (bb[2] - bb[0])) // 2
            draw.text((x+2, y+2), linha, font=font_lg, fill=(0, 0, 0, 160))
            draw.text((x, y), linha, font=font_lg, fill=cor)
            y += (bb[3] - bb[1]) + 6
        if subtitulo:
            bb2 = draw.textbbox((0,0), subtitulo[:50], font=font_sm)
            x2 = (1280 - (bb2[2]-bb2[0])) // 2
            draw.text((x2, min(y+10, 682)), subtitulo[:50], font=font_sm, fill=(180, 180, 180))
        img.save(destino, 'JPEG', quality=92); return destino
    except Exception as e: print(f"[WARN] Thumbnail: {e}"); return None

def obter_videos_recentes():
    uploads_pid = 'UU' + CHANNEL_ID[2:]
    corte = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DIAS_RETROATIVOS)
    video_ids, page_token = [], None
    while True:
        resp = youtube.playlistItems().list(
            part='contentDetails', playlistId=uploads_pid, maxResults=50, pageToken=page_token
        ).execute()
        for item in resp.get('items', []):
            cd = item['contentDetails']
            pub = cd.get('videoPublishedAt', '')
            try:
                dt = datetime.datetime.fromisoformat(pub.replace('Z', '+00:00'))
                if dt >= corte: video_ids.append(cd['videoId'])
                else: return video_ids
            except: video_ids.append(cd['videoId'])
        page_token = resp.get('nextPageToken')
        if not page_token: break
    return video_ids

def main():
    print(f"\n🖼️  Bloco 3 — Thumbnail Updater — Canal {CANAL}")
    img_files = listar_imagens_drive()
    if not img_files: print("❌ Sem imagens."); sys.exit(1)
    sample = random.sample(img_files, min(5, len(img_files)))
    imgs_locais = []
    for f in sample:
        ext = os.path.splitext(f['name'])[1].lower() or '.jpg'
        dest = os.path.join(PASTA_TEMP, f"img_{f['id']}{ext}")
        if not os.path.exists(dest): baixar_imagem(f['id'], dest)
        if os.path.exists(dest): imgs_locais.append(dest)
    if not imgs_locais: print("❌ Falha ao baixar imagens."); sys.exit(1)
    video_ids = [VIDEO_ID_UNICO] if VIDEO_ID_UNICO else obter_videos_recentes()
    if not video_ids: print("  ℹ️  Nenhum vídeo."); return
    detalhes = {}
    for i in range(0, len(video_ids), 50):
        resp = youtube.videos().list(part='snippet,status', id=','.join(video_ids[i:i+50])).execute()
        for item in resp.get('items', []): detalhes[item['id']] = item
    processados = 0
    for video_id in video_ids:
        item = detalhes.get(video_id)
        if not item: continue
        titulo = item['snippet'].get('title', '')
        print(f"\n  📹 {video_id} | {titulo[:55]}")
        img_path = random.choice(imgs_locais)
        thumb_path = os.path.join(PASTA_TEMP, f"thumb_{video_id}.jpg")
        thumb = criar_thumbnail(img_path, titulo, thumb_path)
        if not thumb: continue
        for _ in range(3):
            try:
                youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path, mimetype='image/jpeg')).execute()
                print(f"  ✅ Thumbnail aplicado"); processados += 1; break
            except Exception as e: print(f"  ⚠️  set: {e}"); time.sleep(10)
        try: os.remove(thumb_path)
        except: pass
        time.sleep(2)
    print(f"\n🖼️  Concluído — {processados} thumbnails aplicados.")

if __name__ == "__main__":
    main()
