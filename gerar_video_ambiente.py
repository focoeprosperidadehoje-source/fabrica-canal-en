"""
Bloco 1 — Vídeo Ambiente Noturno — Canal EN
Gera slideshows 4h/6h/8h com imagens de Our Lady + gregorian music.
Upload como unlisted. Publicação via publicar_ambiente.py.
"""

import os, sys, json, time, datetime, subprocess, random
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from google.auth.transport.requests import Request
import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image, ImageDraw, ImageFont

GOOGLE_JSON    = os.environ.get("GOOGLE_CREDENTIALS")
YT_TOKEN_JSON  = os.environ.get("YOUTUBE_TOKEN_JSON")
CANAL          = "EN"
SHEET_ID       = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"
PASTA_TEMP     = "/tmp/ambiente"
PUBLISH_DELAY_H = 48

os.makedirs(PASTA_TEMP, exist_ok=True)

CFG = {
    'pasta_imagens': '1IyWdkNqdKQn8kDX-EWSEjKqOLNPEg6jk',
    'pasta_musicas': '1gxZA1TlQPzuf737XOo_n8blfOThnddgm',
    'aba_sheet': 'EN_AMBIENTE',
    'titulos': {
        4: 'Catholic Music to Sleep — Our Lady [4h] 🙏',
        6: 'Catholic Music to Sleep — Our Lady [6h] 🙏',
        8: 'Catholic Music to Sleep — Our Lady [8h] 🙏',
    },
    'descricao': (
        "🙏 Sleep in peace under the Mantle of the Blessed Virgin Mary.\n"
        "Gregorian chant and prayers for your nightly rest.\n\n"
        "Close your eyes. Our Lady watches over you all night long.\n\n"
        "▶ SEE ALSO:\n"
        "📿 Prayer 24H Live → https://youtube.com/channel/UCOGQwey2JXGvL8cqZ9tmCoQ/live\n\n"
        "#CatholicMusic #Sleep #OurLady #Gregorian #NightPrayer "
        "#BlessedVirginMary #Meditation #Faith #Peace #Rest"
    ),
    'tags': ['catholic music', 'sleep', 'our lady', 'gregorian', 'night prayer',
             'blessed virgin mary', 'meditation', 'relaxation', 'faith', 'peace'],
    'idioma': 'en-US',
    'sub_thumb': 'Gregorian Chant • Night Prayer',
}

# ==============================================================================
# AUTH
# ==============================================================================
credenciais_dict = json.loads(GOOGLE_JSON)
creds_sheets = Credentials.from_service_account_info(
    credenciais_dict,
    scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
)
gc = gspread.authorize(creds_sheets)
drive_service = build('drive', 'v3', credentials=creds_sheets)

creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds_yt.expired and creds_yt.refresh_token:
    creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)

# ==============================================================================
# HELPERS (mesmas funções do ES — Drive, Sheet, Thumbnail, FFmpeg, Upload)
# ==============================================================================
def listar_arquivos(folder_id, extensoes=None):
    res, page_token = [], None
    while True:
        for _ in range(4):
            try:
                resp = drive_service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token
                ).execute(); break
            except Exception as e:
                print(f"[WARN] Drive: {e}"); time.sleep(5)
        else:
            return res
        for f in resp.get('files', []):
            if extensoes is None or f['name'].lower().endswith(extensoes):
                res.append(f)
        page_token = resp.get('nextPageToken')
        if not page_token: break
    return res

def baixar_arquivo(file_id, destino):
    for _ in range(4):
        try:
            req = drive_service.files().get_media(fileId=file_id)
            with open(destino, 'wb') as f: f.write(req.execute())
            return destino
        except Exception as e:
            print(f"[WARN] Download {file_id}: {e}"); time.sleep(5)
    raise Exception(f"Falha ao baixar {file_id}")

def obter_aba(nome_aba):
    sheet = gc.open_by_key(SHEET_ID)
    try:
        return sheet.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=nome_aba, rows=200, cols=10)
        ws.append_row(['canal', 'video_id', 'titulo', 'duracao_h', 'data_geracao', 'publish_at', 'status'])
        time.sleep(2); return ws

def criar_thumbnail(img_path, duracao_h, subtitulo, destino):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720), Image.LANCZOS)
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle([(0, 460), (1280, 720)], fill=(0, 0, 0, 170))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        try: font_lg = ImageFont.truetype("Anton.ttf", 80); font_sm = ImageFont.truetype("Anton.ttf", 34)
        except: font_lg = font_sm = ImageFont.load_default()
        texto = f"{duracao_h} HOURS"
        bb = draw.textbbox((0, 0), texto, font=font_lg)
        x = (1280 - (bb[2] - bb[0])) // 2
        draw.text((x+2, 502), texto, font=font_lg, fill=(0, 0, 0, 180))
        draw.text((x, 500), texto, font=font_lg, fill=(255, 220, 90))
        bb2 = draw.textbbox((0, 0), subtitulo, font=font_sm)
        x2 = (1280 - (bb2[2] - bb2[0])) // 2
        draw.text((x2, 622), subtitulo, font=font_sm, fill=(210, 210, 210))
        img.save(destino, 'JPEG', quality=92); return destino
    except Exception as e:
        print(f"[WARN] Thumbnail: {e}"); return None

def gerar_slideshow(imgs_locais, musica_local, duracao_total_s, saida):
    DURACAO_SEG_S = 15
    segs = []
    for i, img in enumerate(imgs_locais):
        seg = os.path.join(PASTA_TEMP, f"seg_{i:03d}.ts")
        if not os.path.exists(seg):
            r = subprocess.run([
                'ffmpeg', '-y', '-loop', '1', '-framerate', '24', '-i', img,
                '-t', str(DURACAO_SEG_S),
                '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                '-pix_fmt', 'yuv420p', '-r', '24', '-an', seg
            ], capture_output=True, text=True)
            if r.returncode != 0: print(f"  ❌ Seg {i}: {r.stderr[-200:]}"); continue
        segs.append(seg)
    if not segs: return None
    concat_txt = os.path.join(PASTA_TEMP, "concat_longa.txt")
    total, linhas = 0, []
    while total < duracao_total_s:
        for seg in segs:
            linhas.append(f"file '{seg}'\n"); total += DURACAO_SEG_S
            if total >= duracao_total_s: break
    with open(concat_txt, 'w') as f: f.writelines(linhas)
    video_mudo = os.path.join(PASTA_TEMP, "video_mudo.mp4")
    r = subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt,
                        '-t', str(duracao_total_s), '-c', 'copy', video_mudo], capture_output=True, text=True)
    if r.returncode != 0: print(f"  ❌ Concat: {r.stderr[-300:]}"); return None
    r2 = subprocess.run(['ffmpeg', '-y', '-i', video_mudo,
                         '-stream_loop', '-1', '-i', musica_local,
                         '-map', '0:v', '-map', '1:a',
                         '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
                         '-t', str(duracao_total_s), saida], capture_output=True, text=True)
    if r2.returncode != 0: print(f"  ❌ Áudio: {r2.stderr[-300:]}"); return None
    try: os.remove(video_mudo)
    except: pass
    return saida

def upload_ambiente(video_path, titulo, descricao, tags, idioma, thumb_path=None):
    body = {
        "snippet": {"title": titulo[:100], "description": descricao, "tags": tags[:15],
                    "categoryId": "22", "defaultLanguage": idioma, "defaultAudioLanguage": idioma},
        "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False,
                   "selfDeclaredMadeWithAlteredContent": True}
    }
    video_id = None
    for _ in range(3):
        try:
            resp = youtube.videos().insert(part="snippet,status", body=body,
                       media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")).execute()
            video_id = resp.get("id"); print(f"  ✅ Upload OK! ID: {video_id}"); break
        except Exception as e:
            print(f"  ❌ Upload: {e}"); time.sleep(15)
    if not video_id: return None
    if thumb_path and os.path.exists(thumb_path):
        try: youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path)).execute(); print("  🖼️  Thumb OK.")
        except Exception as e: print(f"  ⚠️  Thumb: {e}")
    return video_id

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print(f"\n🌙 Bloco 1 — Vídeo Ambiente — Canal {CANAL}")
    aba = obter_aba(CFG['aba_sheet'])
    img_files = listar_arquivos(CFG['pasta_imagens'], ('.jpg', '.jpeg', '.png'))
    if not img_files: print("❌ Sem imagens."); sys.exit(1)
    random.shuffle(img_files); img_files = img_files[:20]
    imgs_locais = []
    for f in img_files:
        ext = os.path.splitext(f['name'])[1].lower() or '.jpg'
        dest = os.path.join(PASTA_TEMP, f"img_{f['id']}{ext}")
        if not os.path.exists(dest): baixar_arquivo(f['id'], dest)
        imgs_locais.append(dest)
    print(f"  → {len(imgs_locais)} imagens")
    musica_files = listar_arquivos(CFG['pasta_musicas'], ('.mp3', '.m4a', '.aac'))
    musica_local = None
    if musica_files:
        mf = random.choice(musica_files)
        ext = os.path.splitext(mf['name'])[1].lower() or '.mp3'
        dest_m = os.path.join(PASTA_TEMP, f"musica{ext}")
        baixar_arquivo(mf['id'], dest_m); musica_local = dest_m
    else:
        import urllib.request
        dest_m = os.path.join(PASTA_TEMP, "gregorian.mp3")
        try:
            urllib.request.urlretrieve("https://archive.org/download/GregorianChant/GregorianChant01.mp3", dest_m)
            musica_local = dest_m
        except:
            subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                           '-t', '300', '-c:a', 'mp3', os.path.join(PASTA_TEMP, "silence.mp3")], capture_output=True)
            musica_local = os.path.join(PASTA_TEMP, "silence.mp3")
    agora = datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))
    publish_at = agora + datetime.timedelta(hours=PUBLISH_DELAY_H)
    for duracao_h in [4, 6, 8]:
        print(f"\n{'='*50}\n🕐 Gerando {duracao_h}h")
        saida = os.path.join(PASTA_TEMP, f"ambiente_{duracao_h}h.mp4")
        if os.path.exists(saida): os.remove(saida)
        video_path = gerar_slideshow(imgs_locais, musica_local, duracao_h * 3600, saida)
        if not video_path: continue
        thumb = os.path.join(PASTA_TEMP, f"thumb_{duracao_h}h.jpg")
        criar_thumbnail(imgs_locais[0], duracao_h, CFG['sub_thumb'], thumb)
        video_id = upload_ambiente(video_path, CFG['titulos'][duracao_h], CFG['descricao'],
                                   CFG['tags'], CFG['idioma'], thumb)
        if video_id:
            try:
                aba.append_row([CANAL, video_id, CFG['titulos'][duracao_h], duracao_h,
                                agora.strftime('%Y-%m-%d %H:%M'), publish_at.strftime('%Y-%m-%d %H:%M'), 'unlisted'])
            except Exception as e: print(f"  ⚠️  Planilha: {e}")
        try: os.remove(video_path)
        except: pass
    print(f"\n🌙 Concluído — Canal {CANAL}")

if __name__ == "__main__":
    main()
