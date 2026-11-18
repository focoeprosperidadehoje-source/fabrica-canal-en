"""
Bloco 2 — Compilador de Novenas (EN)
Detecta séries de novena completas (9 dias públicos) no canal EN,
baixa os vídeos com yt-dlp, concatena sem re-encode e faz upload
como unlisted. Publicação via publicar_ambiente.py (cron 23:30 BRT).
"""

import os, sys, json, re, time, datetime, subprocess
from collections import defaultdict
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from google.auth.transport.requests import Request
import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==============================================================================
# 1. CONFIG
# ==============================================================================
GOOGLE_JSON   = os.environ.get("GOOGLE_CREDENTIALS")
YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")
SHEET_ID      = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"
PASTA_TEMP    = "/tmp/novena_comp_en"
PUBLISH_DELAY_BASE_H = 48

CFG = {
    "channel_id":    "UCOGQwey2JXGvL8cqZ9tmCoQ",
    "aba_sheet":     "EN_NOVENAS_COMPILADAS",
    "playlist_nome": "Complete Novenas — Our Lady",
    "idioma":        "en-US",
    "descricao_tpl": (
        "🙏 {serie} — Complete 9-Day Novena\n\n"
        "All 9 days together so you can pray without interruption.\n\n"
        "▶ 24H Live Prayer → https://youtube.com/channel/UCOGQwey2JXGvL8cqZ9tmCoQ/live\n\n"
        "#Novena #OurLady #CatholicPrayer #BlessedVirginMary #Faith #Miracles"
    ),
    "titulo_tpl": "Complete 9-Day Novena — {serie} 🙏",
    "tags": ["complete novena", "9 days", "our lady", "prayer", "blessed virgin mary",
             "faith", "miracles", "rosary", "catholic"],
}

os.makedirs(PASTA_TEMP, exist_ok=True)

# ==============================================================================
# 2. AUTH
# ==============================================================================
creds_sheets = Credentials.from_service_account_info(
    json.loads(GOOGLE_JSON),
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
gc = gspread.authorize(creds_sheets)

creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds_yt.expired and creds_yt.refresh_token:
    creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)

# ==============================================================================
# 3. SHEET HELPER
# ==============================================================================
HEADERS_COMP = ['canal', 'video_id', 'serie', 'titulo', 'dias',
                'data_geracao', 'publish_at', 'status']

def obter_aba_compiladas():
    sheet = gc.open_by_key(SHEET_ID)
    try:
        return sheet.worksheet(CFG['aba_sheet'])
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=CFG['aba_sheet'], rows=500, cols=10)
        ws.append_row(HEADERS_COMP)
        time.sleep(2)
        return ws

def series_ja_compiladas(ws):
    registros = ws.get_all_records()
    return {str(r.get('serie', '')).strip() for r in registros if r.get('serie')}

# ==============================================================================
# 4. DESCOBRIR VÍDEOS DE NOVENA
# EN usa "Day N" no título
# ==============================================================================
PADRAO_DIA_EN = re.compile(r'\bDay\s+(\d{1,2})\b', re.IGNORECASE)

def extrair_dia(titulo):
    m = PADRAO_DIA_EN.search(titulo)
    if m:
        return int(m.group(1))
    return None

def calcular_serie(titulo):
    s = PADRAO_DIA_EN.sub('', titulo)
    s = re.sub(r'\s*🙏.*', '', s)
    s = re.sub(r'\s*[-—–|]+\s*$', '', s).strip()
    return re.sub(r'\s{2,}', ' ', s)

def listar_videos_canal():
    from googleapiclient.errors import HttpError
    uploads_id = "UU" + CFG['channel_id'][2:]
    videos = []
    page_token = None
    print("  📺 Fetching channel videos (uploads playlist)...")
    while True:
        try:
            resp = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_id,
                maxResults=50,
                pageToken=page_token
            ).execute()
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print("[WARN] quotaExceeded — quota exhausted. Nothing compiled.")
                return []
            raise
        for item in resp.get("items", []):
            sn = item["snippet"]
            vid = sn["resourceId"]["videoId"]
            videos.append({
                "video_id": vid,
                "titulo": sn.get("title", ""),
                "published_at": sn.get("publishedAt", ""),
            })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.5)
    print(f"  → {len(videos)} videos found")
    return videos

def agrupar_novenas(videos):
    grupos = defaultdict(dict)
    for v in videos:
        dia = extrair_dia(v['titulo'])
        if dia is None or dia < 1 or dia > 9:
            continue
        serie = calcular_serie(v['titulo'])
        if not serie:
            continue
        if dia not in grupos[serie] or v['published_at'] > grupos[serie][dia]['published_at']:
            grupos[serie][dia] = v

    completas = []
    for serie, dias in grupos.items():
        if all(d in dias for d in range(1, 10)):
            completas.append({
                'serie': serie,
                'videos': [dias[d] for d in range(1, 10)],
            })
    return completas

# ==============================================================================
# 5. PLAYLIST
# ==============================================================================
def obter_ou_criar_playlist():
    nome = CFG['playlist_nome']
    page_token = None
    while True:
        resp = youtube.playlists().list(
            part="snippet", mine=True, maxResults=50, pageToken=page_token
        ).execute()
        for p in resp.get("items", []):
            if p["snippet"]["title"] == nome:
                pid = p["id"]
                print(f"  📂 Playlist found: {nome} → {pid}")
                return pid
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    r = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": nome, "defaultLanguage": CFG['idioma']},
            "status": {"privacyStatus": "public"},
        }
    ).execute()
    pid = r["id"]
    print(f"  📂 Playlist CREATED: {nome} → {pid}")
    return pid

# ==============================================================================
# 6. DOWNLOAD + COMPILE
# ==============================================================================
COOKIES_PATH = os.path.join(PASTA_TEMP, "yt_cookies.txt")

def _preparar_cookies():
    conteudo = os.environ.get("YT_COOKIES", "")
    if conteudo.strip():
        with open(COOKIES_PATH, "w") as f:
            f.write(conteudo)
        print("  🍪 Cookies loaded for yt-dlp")
        return True
    return False

def baixar_video(video_id, destino_dir):
    url = f"https://www.youtube.com/watch?v={video_id}"
    saida = os.path.join(destino_dir, f"{video_id}.mp4")
    if os.path.exists(saida):
        return saida
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[ext=mp4]",
        "--merge-output-format", "mp4",
        "--sleep-interval", "3",
        "--max-sleep-interval", "7",
        "--extractor-retries", "3",
        "--fragment-retries", "3",
        "-o", saida,
    ]
    if os.path.exists(COOKIES_PATH):
        cmd += ["--cookies", COOKIES_PATH]
    cmd.append(url)
    for tentativa in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(saida):
            mb = os.path.getsize(saida) / (1024 * 1024)
            print(f"    ✅ {video_id} downloaded ({mb:.0f} MB)")
            return saida
        print(f"    ⚠️  Attempt {tentativa+1}: {r.stderr[-200:]}")
        time.sleep(10)
    return None

def compilar_videos(video_paths, saida):
    concat_txt = os.path.join(PASTA_TEMP, "concat_novena.txt")
    with open(concat_txt, "w") as f:
        for p in video_paths:
            f.write(f"file '{p}'\n")
    r = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", saida
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ❌ Concat error: {r.stderr[-500:]}")
        return None
    mb = os.path.getsize(saida) / (1024 * 1024)
    print(f"  ✅ Compilation: {mb:.0f} MB")
    return saida

# ==============================================================================
# 7. UPLOAD
# ==============================================================================
def upload_compilacao(video_path, titulo, descricao, tags):
    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descricao,
            "tags": tags[:15],
            "categoryId": "22",
            "defaultLanguage": CFG['idioma'],
            "defaultAudioLanguage": CFG['idioma'],
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
            "selfDeclaredMadeWithAlteredContent": True,
        }
    }
    for tentativa in range(3):
        try:
            resp = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
            ).execute()
            vid = resp.get("id")
            print(f"  ✅ Upload OK! ID: {vid}")
            return vid
        except Exception as e:
            print(f"  ❌ Attempt {tentativa+1}: {e}")
            time.sleep(15)
    return None

def adicionar_a_playlist(video_id, playlist_id):
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={"snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id}
            }}
        ).execute()
        print(f"  📂 Added to playlist.")
    except Exception as e:
        print(f"  ⚠️  Playlist insert: {e}")

# ==============================================================================
# 8. MAIN
# ==============================================================================
def main():
    print(f"\n📿 Bloco 2 — Novena Compiler — Channel EN\n")

    _preparar_cookies()
    aba = obter_aba_compiladas()
    ja_compiladas = series_ja_compiladas(aba)
    print(f"Already compiled series: {len(ja_compiladas)}")

    todos_videos = listar_videos_canal()
    grupos_completos = agrupar_novenas(todos_videos)
    print(f"Complete series (9 days) found: {len(grupos_completos)}")

    pendentes = [g for g in grupos_completos if g['serie'] not in ja_compiladas]
    print(f"Pending compilation: {len(pendentes)}")

    if not pendentes:
        print("✅ Nothing to compile.")
        return

    pendentes.sort(key=lambda g: g['videos'][0]['published_at'])

    playlist_id = obter_ou_criar_playlist()
    agora = datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))

    for i, grupo in enumerate(pendentes):
        serie = grupo['serie']
        print(f"\n{'='*60}")
        print(f"📿 Series {i+1}/{len(pendentes)}: {serie}")

        publish_at = agora + datetime.timedelta(hours=PUBLISH_DELAY_BASE_H + i * 24)

        pasta_serie = os.path.join(PASTA_TEMP, f"serie_{i}")
        os.makedirs(pasta_serie, exist_ok=True)
        paths = []
        falhou = False
        for v in grupo['videos']:
            p = baixar_video(v['video_id'], pasta_serie)
            if not p:
                print(f"  ❌ Failed to download {v['video_id']} — series skipped.")
                falhou = True
                break
            paths.append(p)

        if falhou:
            continue

        saida = os.path.join(PASTA_TEMP, f"novena_compiled_{i}.mp4")
        if os.path.exists(saida):
            os.remove(saida)
        video_comp = compilar_videos(paths, saida)
        if not video_comp:
            continue

        titulo = CFG['titulo_tpl'].format(serie=serie)
        descricao = CFG['descricao_tpl'].format(serie=serie)
        video_id = upload_compilacao(video_comp, titulo, descricao, CFG['tags'])
        if not video_id:
            continue

        adicionar_a_playlist(video_id, playlist_id)

        try:
            dias_str = ",".join(v['video_id'] for v in grupo['videos'])
            aba.append_row([
                "EN", video_id, serie, titulo, dias_str,
                agora.strftime('%Y-%m-%d %H:%M'),
                publish_at.strftime('%Y-%m-%d %H:%M'),
                'unlisted'
            ])
            print(f"  📋 Registered → publishes {publish_at.strftime('%d/%m %H:%M')} BRT")
        except Exception as e:
            print(f"  ⚠️  Sheet: {e}")

        for p in paths:
            try: os.remove(p)
            except: pass
        try: os.remove(video_comp)
        except: pass

    print(f"\n📿 Compiler done — {len(pendentes)} series processed.")

if __name__ == "__main__":
    main()
