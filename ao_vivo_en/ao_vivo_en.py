#!/usr/bin/env python3
"""
ao_vivo_en.py — Live 24/7 Canal EN — Blessed Virgin Mary

Threads:
  TRANSMISSOR — 12h cycles, RTMP horizontal, block rotation
  SUPLICAS    — 2-3min intercession segment per block
  MONITOR     — disk health and stock alerts
  ASSEMBLER   — combines audio_*.mp3 (GitHub Actions) + videos_base/

Base blocks (~20min H) arrive via rsync from GitHub Actions 6x/day.
VPS does not encode long blocks — only transmits + generates short supplication segments.
"""

import os
import json
import time
import random
import logging
import threading
import subprocess
import asyncio
import re
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import pytz
from google import genai
from google.oauth2.service_account import Credentials as SACredentials
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import edge_tts

def _load_env(path=".env"):
    import os
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_env(str(Path("/root/ao_vivo_en/.env")))

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

LOG_FILE = Path("/root/ao_vivo_en/ao_vivo.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(threadName)s — %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("ao_vivo_en")


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS AND CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

CANAL_ID       = os.environ.get("CANAL_ID_EN", "UCOGQwey2JXGvL8cqZ9tmCoQ")
PLAYLIST_LIVES = os.environ.get("PLAYLIST_ID_LIVES_EN", "PLCtaYjhJCPSc")
FUSO           = pytz.timezone(os.environ.get("FUSO_EN", "America/New_York"))

STREAM_KEY_H   = os.environ.get("STREAM_KEY_H_EN", "")
STREAM_KEY_V   = ""   # EN live starts horizontal only
INGEST_URL     = os.environ.get("INGEST_URL", "rtmp://a.rtmp.youtube.com/live2")
BROADCAST_ID_H = os.environ.get("BROADCAST_ID_H_EN", "")
MODO_PERMANENTE = bool(STREAM_KEY_H)

BASE_DIR        = Path("/root/ao_vivo_en")
DIR_BLOCOS      = BASE_DIR / "blocos"
DIR_SUPLICAS    = BASE_DIR / "suplicas"
DIR_INSUMOS_H   = BASE_DIR / "insumos_h"   # Our Lady images 16:9
DIR_INSUMOS_V   = BASE_DIR / "insumos_v"   # fallback
DIR_MUSICAS_M   = BASE_DIR / "musicas" / "manha"
DIR_MUSICAS_N   = BASE_DIR / "musicas" / "noite"
DIR_VIDEOS_BASE = BASE_DIR / "videos_base"  # Our Lady slides without sound (10min each)

PLAYLIST_H_FILE = BASE_DIR / "playlist_h.txt"
YT_TOKEN_FILE   = BASE_DIR / "youtube_token.json"
GCP_CREDS_FILE  = BASE_DIR / "google_credentials_en.json"

# Google Drive IDs — assets for supplications on VPS
DRIVE_INSUMOS_H_ID = os.environ.get("DRIVE_OUR_LADY_H_ID", "")
DRIVE_MUSICAS_M_ID = os.environ.get("DRIVE_MUSICAS_M_ID_EN", "")
DRIVE_MUSICAS_N_ID = os.environ.get("DRIVE_MUSICAS_N_ID_EN", "")

# Timing
DURACAO_BLOCO_SEG    = 20 * 60
DURACAO_SUPLICA_SEG  = 160
SUPLICA_GERAR_OFFSET = 22 * 60
ROLLING_INICIAIS     = 50
ROLLING_ANTECIPACAO  = 1500
SUPLICA_INTERVAL     = 30 * 60
SUPLICA_MAX_READY    = 8              # max ready supplications (CPU cap)
ASSEMBLER_BLOCOS_MAX = 8             # max ready H blocks — assembler sleeps above this
DURACAO_CICLO_SEG    = 12 * 3600     # 12h per broadcast (2x/day)
BLOCOS_MINIMOS       = 1

# TTS and Gemini
VOZ          = "en-US-JennyNeural"
VOZ_RATE     = "-30%"
VOZ_PITCH    = "-8Hz"
MODELOS_LIVE = ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]

CHAVES_CONTEUDO = [c for c in [
    os.environ.get("GEMINI_KEY_LIVE_CONTENT_1_EN", ""),
    os.environ.get("GEMINI_KEY_LIVE_CONTENT_2_EN", ""),
] if c]

CHAVES_CHAT = [c for c in [
    os.environ.get("GEMINI_KEY_LIVE_CHAT_1_EN", ""),
    os.environ.get("GEMINI_KEY_LIVE_CHAT_2_EN", ""),
    os.environ.get("GEMINI_KEY_LIVE_CHAT_3_EN", ""),
] if c]

PILARES = {
    0: "Spiritual Warfare and Divine Protection",
    1: "Liberation from Addictions and Bondage",
    2: "Family Restoration and Reconciliation",
    3: "Divine Providence and Open Doors",
    4: "Divine Mercy and Physical Healing",
    5: "The Blessed Virgin's Mantle",
    6: "Miracles and Gratitude",
}

RTMP_BASE = "rtmp://a.rtmp.youtube.com/live2"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_ALT  = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

_THUMB_LINHAS = {
    "manha": ["STRENGTH AND", "RESTORATION", "WITH OUR LADY"],
    "tarde":  ["DIVINE", "PROTECTION", "WITH OUR LADY"],
    "noite":  ["REST", "AND HEALING", "WITH OUR LADY"],
}

TITULOS_LIVE = {
    0: "🔴 Our Lady Protects You NOW from Every Attack — Powerful Prayer LIVE",
    1: "🔴 Our Lady Breaks This Bondage TODAY — Powerful Liberation LIVE",
    2: "🔴 Our Lady Restores Your Family TODAY — Miracle of Reconciliation LIVE",
    3: "🔴 Our Lady Opens Closed Doors TODAY — Miracle of Providence LIVE",
    4: "🔴 Our Lady Heals Your Body RIGHT NOW — Miracle of Healing LIVE",
    5: "🔴 The Mantle of Our Lady Covers You NOW — Protection and Miracles LIVE",
    6: "🔴 Our Lady Has a Miracle for You TODAY — Receive It LIVE",
}

DESCRICAO_LIVE = (
    "🙏 Continuous prayer broadcast with the Blessed Virgin Mary — Our Lady of Guadalupe.\n\n"
    "Leave your prayer request in the comments — your Heavenly Mother is listening to you.\n\n"
    "💝 Support this mission of continuous prayer:\n"
    "👉 https://www.paypal.com/donate/?hosted_button_id=P5E5EBVM2HWGS\n\n"
    "📿 Blessed items:\n"
    "• Rosary of Our Lady → https://amzn.to/40ewSZU\n"
    "• Large Print Bible → https://amzn.to/4afDGLy\n\n"
    "🔔 Hit the bell · 👍 Like · ➡️ Visit the channel"
)

# Global state
_estado = {
    "live_id_h": None,
    "proc_h": None,
}
_lock = threading.Lock()
_lock_suplica = threading.Lock()
_suplica_caminhos = {"h": None}

_ev_suplica_gerar = threading.Event()
_ev_suplica_pronta = threading.Event()
_ev_parar = threading.Event()

_rotation_idx = 0

MIN_BLOCO_BYTES = 10 * 1024 * 1024

_stream_id_cache = {"id": None}


# ═══════════════════════════════════════════════════════════════════════
# LITURGICAL CALENDAR
# ═══════════════════════════════════════════════════════════════════════

def _easter(year: int) -> datetime:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return datetime(year, month, day)

def calcular_contexto_sazonal(data: datetime) -> str:
    ano = data.year
    p   = _easter(ano)
    fixas = {
        (1, 1):   "New Year — Solemnity of Mary, Mother of God",
        (2, 2):   "Presentation of the Lord — Candlemas",
        (3, 19):  "Saint Joseph — Patron of the Universal Church",
        (5, 13):  "Our Lady of Fatima",
        (8, 15):  "Assumption of the Blessed Virgin Mary",
        (12, 8):  "Immaculate Conception of the Blessed Virgin Mary",
        (12, 12): "Our Lady of Guadalupe — Patroness of the Americas",
        (12, 24): "Christmas Eve",
        (12, 25): "Christmas — Birth of Our Lord",
    }
    if (data.month, data.day) in fixas:
        return fixas[(data.month, data.day)]
    diff = (data.date() - p.date()).days
    moveis = {
        -46: "Ash Wednesday — Beginning of Lent",
        -7:  "Palm Sunday",
        -2:  "Good Friday — Passion and Death of Our Lord",
         0:  "Alleluia! Easter Sunday — Resurrection!",
        49:  "Pentecost Sunday",
        60:  "Corpus Christi",
    }
    if diff in moveis:
        return moveis[diff]
    if data.weekday() == 4:
        return "Friday — Journey of Mercy and Forgiveness"
    return PILARES.get(data.weekday(), "Journey of Prayer and Intercession")


# ═══════════════════════════════════════════════════════════════════════
# GEMINI
# ═══════════════════════════════════════════════════════════════════════

def rodar_gemini(prompt: str, usa_chat: bool = False) -> str:
    chaves = CHAVES_CHAT if usa_chat else CHAVES_CONTEUDO
    for modelo in MODELOS_LIVE:
        modelo_morto = False
        for chave in chaves:
            try:
                client = genai.Client(api_key=chave)
                resp = client.models.generate_content(model=modelo, contents=prompt)
                return resp.text.strip()
            except Exception as e:
                msg = str(e)
                log.warning(f"Gemini {modelo} [{chave[-6:]}]: {msg[:100]}")
                if "404" in msg or "no longer" in msg.lower() or "not found" in msg.lower():
                    log.warning(f"Model {modelo} deprecated — skipping.")
                    modelo_morto = True
                    break
                if "503" in msg or "unavailable" in msg.lower():
                    break
        if modelo_morto:
            continue
    log.error("All Gemini models/keys failed.")
    return ""


# ═══════════════════════════════════════════════════════════════════════
# GOOGLE APIS
# ═══════════════════════════════════════════════════════════════════════

def _load_gcp_info() -> dict:
    if GCP_CREDS_FILE.exists():
        return json.loads(GCP_CREDS_FILE.read_text())
    return json.loads(os.environ["GOOGLE_CREDENTIALS_EN"])

def _creds_drive() -> SACredentials:
    creds = SACredentials.from_service_account_info(
        _load_gcp_info(),
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    creds.refresh(Request())
    return creds

def _creds_youtube() -> OAuthCredentials:
    raw = os.environ.get("YOUTUBE_TOKEN_EN") or YT_TOKEN_FILE.read_text()
    data = json.loads(raw)
    creds = OAuthCredentials.from_authorized_user_info(
        data, scopes=["https://www.googleapis.com/auth/youtube"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        YT_TOKEN_FILE.write_text(creds.to_json())
        log.info("YouTube token EN renewed.")
    return creds

def get_drive():
    return build("drive", "v3", credentials=_creds_drive())

def get_youtube():
    return build("youtube", "v3", credentials=_creds_youtube())


# ═══════════════════════════════════════════════════════════════════════
# DRIVE — ASSET DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════

def _baixar_pasta_drive(drive, folder_id: str, dest: Path, exts=(".mp3", ".jpg", ".png", ".jpeg")):
    if not folder_id:
        return
    dest.mkdir(parents=True, exist_ok=True)
    existentes = {f.name for f in dest.iterdir()}
    page_token = None
    n = 0
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
            pageSize=100,
        ).execute()
        for arq in resp.get("files", []):
            nome = arq["name"]
            if not any(nome.lower().endswith(e) for e in exts):
                continue
            if nome in existentes:
                continue
            dest_arq = dest / nome
            for tentativa in range(4):
                try:
                    req = drive.files().get_media(fileId=arq["id"])
                    buf = BytesIO()
                    dl = MediaIoBaseDownload(buf, req, chunksize=16 * 1024 * 1024)
                    done = False
                    while not done:
                        _, done = dl.next_chunk()
                    dest_arq.write_bytes(buf.getvalue())
                    n += 1
                    break
                except Exception as e:
                    log.warning(f"  attempt {tentativa+1}/4 for {nome}: {e}")
                    time.sleep(5 * (tentativa + 1))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    log.info(f"Drive ↓ {n} file(s) in {dest.name}")

def garantir_assets_vps():
    try:
        drive = get_drive()
        imgs_h = list(DIR_INSUMOS_H.glob("*.jpg")) + list(DIR_INSUMOS_H.glob("*.png"))
        if len(imgs_h) < 5:
            log.info("Downloading Our Lady horizontal images...")
            _baixar_pasta_drive(drive, DRIVE_INSUMOS_H_ID, DIR_INSUMOS_H, (".jpg", ".png", ".jpeg"))
        if DRIVE_MUSICAS_M_ID and not list(DIR_MUSICAS_M.glob("*.mp3")):
            log.info("Downloading morning music EN...")
            _baixar_pasta_drive(drive, DRIVE_MUSICAS_M_ID, DIR_MUSICAS_M)
        if DRIVE_MUSICAS_N_ID and not list(DIR_MUSICAS_N.glob("*.mp3")):
            log.info("Downloading evening music EN...")
            _baixar_pasta_drive(drive, DRIVE_MUSICAS_N_ID, DIR_MUSICAS_N)
        log.info("VPS EN assets: OK")
    except Exception as e:
        log.warning(f"garantir_assets_vps: {e} — continuing without Drive assets")


# ═══════════════════════════════════════════════════════════════════════
# BLOCKS — ROTATION AND PLAYLIST
# ═══════════════════════════════════════════════════════════════════════

def listar_blocos() -> list[Path]:
    resultado = []
    for h in sorted(DIR_BLOCOS.glob("*_h.mp4")):
        try:
            if h.stat().st_size < MIN_BLOCO_BYTES:
                continue
        except OSError:
            continue
        resultado.append(h)
    return resultado

def _construir_playlist_rolling(blocos: list, rot_idx: int, n: int) -> tuple:
    playlist = BASE_DIR / "_playlist_h.txt"
    linhas = ["ffconcat version 1.0"]
    dur = 0.0
    for i in range(n):
        h = blocos[(rot_idx + i) % len(blocos)]
        try:
            rel = h.relative_to(BASE_DIR)
        except ValueError:
            rel = h
        linhas.append(f"file '{rel}'")
        dur += DURACAO_BLOCO_SEG
    playlist.write_text("\n".join(linhas))
    log.info(f"Playlist H rolling: {n} blocks, {dur/60:.0f}min buffer")
    return playlist, (rot_idx + n) % len(blocos), dur

def _resetar_playlist(path: Path, primeiro: Path):
    try:
        rel = primeiro.relative_to(path.parent)
    except ValueError:
        rel = primeiro
    path.write_text(f"ffconcat version 1.0\nfile '{rel}'\n")

def _append_playlist(path: Path, arquivo: Path):
    try:
        rel = arquivo.relative_to(path.parent)
    except ValueError:
        rel = arquivo
    with open(path, "a") as f:
        f.write(f"file '{rel}'\n")
    log.info(f"  playlist {path.name} ← {arquivo.name}")

def _limpar_suplicas_antigas(max_age_h: int = 3):
    cutoff = time.time() - max_age_h * 3600
    for f in DIR_SUPLICAS.glob("suplica_*"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# LIVE CHAT
# ═══════════════════════════════════════════════════════════════════════

def buscar_msgs_chat(yt, broadcast_id: str) -> list[dict]:
    if not broadcast_id:
        return []
    try:
        b = yt.liveBroadcasts().list(part="snippet", id=broadcast_id).execute()
        if not b.get("items"):
            return []
        chat_id = b["items"][0]["snippet"].get("liveChatId")
        if not chat_id:
            return []
        resp = yt.liveChatMessages().list(
            part="snippet,authorDetails", liveChatId=chat_id, maxResults=200
        ).execute()
        msgs = []
        for item in resp.get("items", []):
            autor = item["authorDetails"]["displayName"]
            texto = item["snippet"].get("displayMessage", "").strip()
            if texto and len(texto) > 5:
                msgs.append({"autor": autor, "texto": texto})
        return msgs
    except Exception as e:
        log.warning(f"buscar_msgs_chat ({broadcast_id}): {e}")
        return []

def extrair_suplicantes(msgs: list[dict], max_s: int = 6) -> list[dict]:
    palavras = ["pray", "prayer", "heal", "sick", "job", "family", "marriage", "cure",
                "deliverance", "miracle", "help", "pain", "addiction", "Our Lady",
                "please", "intercede", "blessing"]
    resultado = []
    for m in msgs:
        if any(p in m["texto"].lower() for p in palavras):
            resultado.append({"nome": m["autor"], "pedido": m["texto"][:200]})
        if len(resultado) >= max_s:
            break
    return resultado

def nomes_ficticios(n: int = 5) -> list[dict]:
    nomes = ["Mary", "John", "Anna", "Robert", "Patricia", "Carlos",
             "Rose", "Michael", "Elena", "Joseph", "Sandra", "Carmen"]
    pedidos = [
        "the health of their sick mother",
        "urgent employment for their family",
        "the restoration of their marriage",
        "liberation from an addiction",
        "an urgent financial miracle",
        "protection over their home and children",
    ]
    return [{"nome": random.choice(nomes), "pedido": random.choice(pedidos)} for _ in range(n)]


# ═══════════════════════════════════════════════════════════════════════
# SUPPLICATIONS — SCRIPT AND VIDEO
# ═══════════════════════════════════════════════════════════════════════

def _gerar_roteiro_suplica(suplicantes: list[dict]) -> str:
    linhas = "\n".join(f"  - {s['nome']}: {s['pedido']}" for s in suplicantes)

    prompt = (
        f"You are the Blessed Virgin Mary, speaking in first person, in English.\n"
        f"Intercede for these souls for 2-3 minutes.\n\n"
        f"Prayer intentions:\n{linhas}\n\n"
        f"Instructions:\n"
        f"- MENTION each person by name with their specific intention\n"
        f"- Warm and maternal tone, 380-450 words\n"
        f"- Include a brief blessing at the end\n"
        f"- Plain text only, no markdown, no titles\n"
        f"- The last sentence is syntactically incomplete to flow smoothly\n"
        f"  into the next prayer in the broadcast"
    )
    texto = rodar_gemini(prompt, usa_chat=True)
    texto = re.sub(r'\*+', '', texto)
    texto = re.sub(r'#{1,6}\s+', '', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()

async def _tts_async(texto: str, saida: Path):
    comm = edge_tts.Communicate(texto, voice=VOZ, rate=VOZ_RATE, pitch=VOZ_PITCH)
    await comm.save(str(saida))

def _musica_periodo() -> str | None:
    hora  = datetime.now(FUSO).hour
    pasta = DIR_MUSICAS_M if 5 <= hora < 18 else DIR_MUSICAS_N
    musicas = list(pasta.glob("*.mp3"))
    return str(random.choice(musicas)) if musicas else None

def _duracao_audio(audio: Path) -> int:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
            capture_output=True, text=True
        )
        return max(60, int(float(r.stdout.strip())) + 5)
    except Exception:
        return DURACAO_SUPLICA_SEG

def _run_ffmpeg(cmd: list[str], label: str):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg [{label}] failed:\n{r.stderr[-600:]}")
    log.info(f"FFmpeg [{label}] OK")

def _montar_suplica(audio: Path, saida: Path, dur: int, imgs_dir: Path):
    imgs = list(imgs_dir.glob("*.jpg")) + list(imgs_dir.glob("*.png"))
    if not imgs:
        cmd = ["nice", "-n", "19", "ffmpeg", "-y",
               "-f", "lavfi", "-i", "color=c=0x1a0a2e:s=1280x720:r=30",
               "-i", str(audio), "-t", str(dur),
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
               "-g", "60", "-keyint_min", "30", "-threads", "1",
               "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", str(saida)]
        _run_ffmpeg(cmd, f"supplication color {saida.name}")
        return

    random.shuffle(imgs)
    n_imgs = dur // 8 + 3
    imgs_loop = [imgs[i % len(imgs)] for i in range(n_imgs)]

    concat_file = saida.with_suffix(".concat_s.txt")
    linhas = ["ffconcat version 1.0"]
    for img in imgs_loop:
        linhas.append(f"file '{img}'")
        linhas.append("duration 8")
    linhas.append(f"file '{imgs_loop[-1]}'")
    concat_file.write_text("\n".join(linhas))

    musica = _musica_periodo()
    if musica:
        inputs  = ["-i", str(audio), "-i", musica]
        afiltro = (
            "[1:a]volume=1.0[pray];"
            f"[2:a]volume=0.12,aloop=loop=-1:size=2e+09,atrim=duration={dur}[mus];"
            "[pray][mus]amix=inputs=2:duration=first[aout]"
        )
    else:
        inputs  = ["-i", str(audio)]
        afiltro = "[1:a]volume=1.0[aout]"

    vfiltro = "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,fps=30[vout]"
    cmd = [
        "nice", "-n", "19",
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        *inputs,
        "-filter_complex", f"{vfiltro};{afiltro}",
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(dur),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
        "-g", "60", "-keyint_min", "30", "-threads", "1",
        "-c:a", "aac", "-b:a", "128k", "-r", "30", "-pix_fmt", "yuv420p",
        str(saida),
    ]
    _run_ffmpeg(cmd, f"supplication {saida.name}")
    concat_file.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# YOUTUBE — BROADCASTS
# ═══════════════════════════════════════════════════════════════════════

def _titulo_live_do_dia() -> str:
    return TITULOS_LIVE[datetime.now(FUSO).weekday()]

def _stream_id_da_chave(yt) -> str:
    if _stream_id_cache["id"]:
        return _stream_id_cache["id"]
    sid_env = os.environ.get("STREAM_ID_H_EN", "")
    if sid_env:
        _stream_id_cache["id"] = sid_env
        return sid_env
    resp  = yt.liveStreams().list(part="id,cdn", mine=True, maxResults=50).execute()
    itens = resp.get("items", [])
    for item in itens:
        nome = item.get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")
        if nome == STREAM_KEY_H:
            _stream_id_cache["id"] = item["id"]
            return item["id"]
    if len(itens) == 1:
        sid = itens[0]["id"]
        log.warning(f"STREAM_KEY_H_EN not found by name — using single liveStream ({sid})")
        _stream_id_cache["id"] = sid
        return sid
    raise RuntimeError(
        f"liveStream for STREAM_KEY_H_EN not found ({len(itens)} streams) "
        "— set STREAM_ID_H_EN in .env"
    )

def adotar_broadcast_ativo(yt) -> str | None:
    try:
        resp = yt.liveBroadcasts().list(
            part="id,status,contentDetails,snippet",
            broadcastStatus="active", broadcastType="all", maxResults=5,
        ).execute()
        itens = resp.get("items", [])
    except Exception as e:
        log.warning(f"adotar_broadcast_ativo: list ({e})")
        return None
    if not itens:
        return None
    sid = ""
    try:
        sid = _stream_id_da_chave(yt)
    except Exception:
        pass
    alvo = itens[0]
    for item in itens:
        if item.get("contentDetails", {}).get("boundStreamId", "") == sid:
            alvo = item
            break
    bid    = alvo["id"]
    priv   = alvo.get("status", {}).get("privacyStatus", "?")
    titulo = alvo.get("snippet", {}).get("title", "")[:60]
    log.info(f"ACTIVE broadcast adopted: {bid} ({priv}) — {titulo}")
    return bid

def _limpar_orfaos(yt, max_del: int = 15, idade_min_h: int = 3):
    try:
        resp = yt.liveBroadcasts().list(
            part="id,snippet", broadcastStatus="upcoming",
            broadcastType="all", maxResults=50,
        ).execute()
        itens = resp.get("items", [])
    except Exception as e:
        log.warning(f"limpar_orfaos: list ({e})")
        return
    agora = datetime.now(timezone.utc)
    n = 0
    for item in itens:
        if n >= max_del:
            break
        sched = item.get("snippet", {}).get("scheduledStartTime", "")
        try:
            t = datetime.strptime(sched[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if (agora - t).total_seconds() < idade_min_h * 3600:
            continue
        try:
            yt.liveBroadcasts().delete(id=item["id"]).execute()
            log.info(f"Orphan deleted: {item['id']}")
            n += 1
        except Exception as e:
            log.warning(f"limpar_orfaos: delete {item['id']} ({e})")

def criar_broadcast_permanente(yt) -> str:
    titulo = _titulo_live_do_dia()
    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": titulo,
                "description": DESCRICAO_LIVE,
                "scheduledStartTime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "status": {
                "privacyStatus": "unlisted",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,
                "latencyPreference": "normal",
                "monitorStream": {"enableMonitorStream": False},
                "selfDeclaredMadeWithAlteredContent": True,
            },
        },
    ).execute()
    bid = broadcast["id"]
    yt.liveBroadcasts().bind(part="id,contentDetails", id=bid,
                             streamId=_stream_id_da_chave(yt)).execute()
    try:
        snip = yt.videos().list(part="snippet", id=bid).execute()["items"][0]["snippet"]
        snip["defaultLanguage"]      = "en"
        snip["defaultAudioLanguage"] = "en"
        yt.videos().update(part="snippet", body={"id": bid, "snippet": snip}).execute()
    except Exception as e:
        log.warning(f"language for broadcast {bid}: {e}")
    log.info(f"Broadcast EN created (unlisted, autoStart): {bid} — {titulo}")
    return bid

def _finalizar_broadcast(yt, bid: str):
    try:
        yt.liveBroadcasts().transition(broadcastStatus="complete", id=bid,
                                       part="id,status").execute()
        log.info(f"Broadcast {bid} ended — VOD processing.")
    except Exception as e:
        log.warning(f"finalizar {bid}: transition ({e})")
    if PLAYLIST_LIVES:
        for tentativa in range(1, 4):
            try:
                yt.playlistItems().insert(
                    part="snippet",
                    body={"snippet": {
                        "playlistId": PLAYLIST_LIVES,
                        "resourceId": {"kind": "youtube#video", "videoId": bid},
                    }},
                ).execute()
                log.info(f"VOD {bid} added to playlist (attempt {tentativa}).")
                break
            except Exception as e:
                if tentativa < 3:
                    time.sleep(120)
                else:
                    log.warning(f"finalizar {bid}: playlist insert failed ({e})")

def _publicar_apos_golive(yt, bid: str, espera_seg: int = 60, timeout_seg: int = 1800):
    t0 = time.time()
    ao_vivo = False
    while time.time() - t0 < timeout_seg:
        if _ev_parar.wait(timeout=30):
            return
        try:
            itens = yt.liveBroadcasts().list(part="status", id=bid).execute().get("items", [])
            if not itens:
                return
            st = itens[0]["status"]["lifeCycleStatus"]
            if st == "live":
                ao_vivo = True
                break
            if st in ("complete", "revoked"):
                return
        except Exception as e:
            log.warning(f"publicar: poll {bid}: {e}")
    if not ao_vivo:
        return
    if _ev_parar.wait(timeout=espera_seg):
        return
    try:
        yt.liveBroadcasts().update(
            part="status",
            body={"id": bid, "status": {"privacyStatus": "public",
                                        "selfDeclaredMadeForKids": False}},
        ).execute()
        log.info(f"Broadcast {bid} now PUBLIC")
        _aplicar_thumbnail(yt, bid)
        _ativar_transmissao_dupla(yt, bid)
    except Exception as e:
        log.error(f"publicar: failed to make {bid} public: {e}")


# ═══════════════════════════════════════════════════════════════════════
# THUMBNAIL
# ═══════════════════════════════════════════════════════════════════════

def _fonte(size: int):
    if not _PIL_OK:
        return None
    for path in (FONT_PATH, FONT_ALT):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _aplicar_thumbnail(yt, bid: str):
    if not _PIL_OK:
        return
    try:
        hora = datetime.now(FUSO).hour
        if 5 <= hora < 12:
            periodo = "manha"
        elif 12 <= hora < 19:
            periodo = "tarde"
        else:
            periodo = "noite"
        linhas = _THUMB_LINHAS[periodo]

        fotos = list(DIR_INSUMOS_H.glob("*.jpg")) + list(DIR_INSUMOS_H.glob("*.jpeg"))
        if not fotos:
            return
        bg = Image.open(random.choice(fotos)).convert("RGB")
        w, h = 1280, 720

        bg_ratio = bg.width / bg.height
        tgt_ratio = w / h
        if bg_ratio > tgt_ratio:
            new_h = h
            new_w = int(bg.width * h / bg.height)
        else:
            new_w = w
            new_h = int(bg.height * w / bg.width)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - w) // 2
        top  = (new_h - h) // 2
        bg   = bg.crop((left, top, left + w, top + h))

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        grad_start = int(h * 0.42)
        for y_line in range(grad_start, h):
            t = (y_line - grad_start) / (h - grad_start)
            alpha = int(t * 200)
            ov_draw.line([(0, y_line), (w, y_line)], fill=(0, 0, 0, alpha))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(bg, "RGBA")

        f_vivo = _fonte(26)
        badge_txt = " ● LIVE NOW "
        bb = draw.textbbox((0, 0), badge_txt, font=f_vivo)
        bh_badge = bb[3] - bb[1]
        draw.rectangle([(14, 14), (14 + bb[2] + 6, 14 + bh_badge + 8)], fill=(210, 20, 20, 240))
        draw.text((18, 18), badge_txt, font=f_vivo, fill=(255, 255, 255, 255))

        f_titulo = _fonte(74)
        total_h_px = sum(draw.textbbox((0, 0), l, font=f_titulo)[3] for l in linhas) + 12 * (len(linhas) - 1)
        y = int(h * 0.52)
        for linha in linhas:
            bbox = draw.textbbox((0, 0), linha, font=f_titulo)
            lw   = bbox[2] - bbox[0]
            lh   = bbox[3] - bbox[1]
            draw.text(((w - lw) // 2 + 2, y + 2), linha, font=f_titulo, fill=(0, 0, 0, 180))
            draw.text(((w - lw) // 2, y), linha, font=f_titulo, fill=(255, 255, 255, 255))
            y += lh + 12

        draw.rectangle([(w // 10, h - 56), (w - w // 10, h - 53)], fill=(212, 175, 55, 230))
        brand = "Blessed Virgin Mary · Prayer 24 Hours"
        f_brand = _fonte(34)
        bbox  = draw.textbbox((0, 0), brand, font=f_brand)
        bw    = bbox[2] - bbox[0]
        draw.text(((w - bw) // 2, h - 48), brand, font=f_brand, fill=(212, 175, 55, 255))

        buf = BytesIO()
        bg.save(buf, format="JPEG", quality=90)
        img_bytes = buf.getvalue()

        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        with open(tmp, "wb") as f:
            f.write(img_bytes)
        yt.thumbnails().set(
            videoId=bid,
            media_body=MediaFileUpload(tmp, mimetype="image/jpeg"),
        ).execute()
        log.info(f"Thumbnail EN applied to broadcast {bid}")
        os.remove(tmp)
    except Exception as e:
        log.warning(f"thumbnail EN: {e}")


def _ativar_transmissao_dupla(yt, bid: str):
    """Activates dual streaming (MULTI_ASPECT_MODE_CROP) via YouTube's internal API.
    YouTube automatically generates the 9:16 version from the horizontal stream."""
    try:
        items = yt.liveBroadcasts().list(part="snippet", id=bid).execute().get("items", [])
        if not items:
            log.warning(f"[DUPLA] Broadcast {bid} not found")
            return
        video_id = items[0]["snippet"].get("videoId", "") or bid
        if not video_id:
            log.warning(f"[DUPLA] videoId not found for broadcast {bid}")
            return
        creds = yt._http.credentials
        token = getattr(creds, "token", None)
        if not token:
            log.warning("[DUPLA] OAuth token not available for dual streaming")
            return
        payload = json.dumps({
            "encryptedVideoId": video_id,
            "multiAspectCreatorSettings": {"mode": "MULTI_ASPECT_MODE_CROP"},
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://www.youtube.com/youtubei/v1/video_manager/metadata_update",
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
        if status == 200:
            log.info(f"[DUPLA] Dual streaming activated: broadcast {bid} → video {video_id}")
        else:
            log.warning(f"[DUPLA] Unexpected response {status} activating dual streaming")
    except Exception as e:
        log.warning(f"[DUPLA] Error activating dual streaming: {e}")


# ═══════════════════════════════════════════════════════════════════════
# FFMPEG — STREAMING
# ═══════════════════════════════════════════════════════════════════════

def _iniciar_proc_playlist(playlist: Path, sk: str, nome: str) -> subprocess.Popen:
    try:
        rel_playlist = str(playlist.relative_to(BASE_DIR))
    except ValueError:
        rel_playlist = str(playlist)

    cmd = [
        "ffmpeg",
        "-re",
        "-fflags", "+genpts",
        "-f", "concat", "-safe", "0",
        "-i", rel_playlist,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
        "-b:v", "2000k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-g", "60", "-keyint_min", "30",
        "-c:a", "copy",
        "-f", "flv", f"{INGEST_URL}/{sk}",
    ]
    log_ffmpeg = BASE_DIR / f"ffmpeg_{nome.lower()}.log"
    stderr_f   = open(log_ffmpeg, "wb", buffering=0)
    p = subprocess.Popen(cmd, cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=stderr_f)
    p._stderr_f = stderr_f
    log.info(f"FFmpeg {nome} (playlist) PID {p.pid} → {log_ffmpeg.name}")
    with _lock:
        _estado[f"proc_{nome.lower()}"] = p
    return p

def _matar_proc(proc: subprocess.Popen | None, nome: str):
    if not proc or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
        proc.kill()
    try:
        f = getattr(proc, "_stderr_f", None)
        if f: f.close()
    except Exception: pass
    log.info(f"FFmpeg {nome} terminated.")


# ═══════════════════════════════════════════════════════════════════════
# THREAD: SUPPLICATIONS
# ═══════════════════════════════════════════════════════════════════════

def loop_suplicas():
    yt = get_youtube()
    DIR_SUPLICAS.mkdir(parents=True, exist_ok=True)

    while not _ev_parar.is_set():
        _ev_suplica_gerar.wait(timeout=60)
        if _ev_parar.is_set():
            break
        if not _ev_suplica_gerar.is_set():
            continue
        _ev_suplica_gerar.clear()

        log.info("Supplications EN: starting generation...")
        try:
            with _lock:
                bid_h = _estado.get("live_id_h")

            msgs = buscar_msgs_chat(yt, bid_h) if bid_h else []
            suplicantes = extrair_suplicantes(msgs) or nomes_ficticios(5)

            roteiro = _gerar_roteiro_suplica(suplicantes)
            if not roteiro:
                log.warning("Supplication EN: empty script — skipping")
                _ev_suplica_pronta.set()
                continue

            ts = datetime.now(FUSO).strftime("%Y%m%d_%H%M%S")
            audio_path = DIR_SUPLICAS / f"suplica_{ts}.mp3"
            asyncio.run(_tts_async(roteiro, audio_path))

            if not audio_path.exists() or audio_path.stat().st_size < 1024:
                log.warning("Supplication EN: invalid audio — skipping")
                _ev_suplica_pronta.set()
                continue

            dur = _duracao_audio(audio_path)
            sh  = DIR_SUPLICAS / f"suplica_{ts}_h.mp4"
            _montar_suplica(audio_path, sh, dur, DIR_INSUMOS_H)
            audio_path.unlink(missing_ok=True)

            with _lock_suplica:
                _suplica_caminhos["h"] = sh

            _ev_suplica_pronta.set()
            log.info(f"Supplication EN ready: {sh.name} ({dur}s)")

        except Exception as e:
            log.error(f"Supplication EN: error: {e}")
            _ev_suplica_pronta.set()


# ═══════════════════════════════════════════════════════════════════════
# THREAD: ASSEMBLER
# ═══════════════════════════════════════════════════════════════════════

def _montar_bloco_h(audio: Path) -> Path:
    ts    = audio.stem.replace("audio_", "")
    saida = DIR_BLOCOS / f"bloco_{ts}_h.mp4"
    if saida.exists():
        return saida

    videos = sorted(DIR_VIDEOS_BASE.glob("*.mp4"))
    if not videos:
        raise RuntimeError(f"No videos in {DIR_VIDEOS_BASE}")

    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
            capture_output=True, text=True, timeout=15
        )
        dur = max(int(float(r.stdout.strip())), 1200)
    except Exception:
        dur = DURACAO_BLOCO_SEG

    vids_shuffled = list(videos)
    random.shuffle(vids_shuffled)
    concat_file = saida.with_suffix(".vconcat.txt")
    linhas = ["ffconcat version 1.0"]
    total  = 0
    idx    = 0
    while total < dur + 300:
        linhas.append(f"file '{vids_shuffled[idx % len(vids_shuffled)]}'")
        total += 600
        idx   += 1
    concat_file.write_text("\n".join(linhas))

    musica    = _musica_periodo()
    extra_inp = ["-i", musica] if musica else []
    if musica:
        afiltro = (
            "[1:a]volume=1.0[pray];"
            f"[2:a]volume=0.13,aloop=loop=-1:size=2e+09,atrim=duration={dur}[mus];"
            "[pray][mus]amix=inputs=2:duration=first:dropout_transition=3[aout]"
        )
    else:
        afiltro = "[1:a]volume=1.0[aout]"

    vfiltro = (
        "[0:v]scale=1280:720:force_original_aspect_ratio=increase,"
        "crop=1280:720,setsar=1,fps=30[vout]"
    )

    saida_tmp = saida.with_suffix(".tmp.mp4")
    cmd = [
        "nice", "-n", "19",
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(audio),
        *extra_inp,
        "-filter_complex", f"{vfiltro};{afiltro}",
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(dur),
        "-c:v", "libx264", "-preset", "ultrafast",
        "-b:v", "2000k", "-minrate", "2000k", "-maxrate", "2000k", "-bufsize", "2000k",
        "-x264opts", "nal-hrd=cbr:sync-lookahead=0",
        "-bf", "0", "-sc_threshold", "0",
        "-g", "60", "-keyint_min", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-r", "30", "-pix_fmt", "yuv420p",
        "-threads", "1",
        str(saida_tmp),
    ]
    log.info(f"Assembler EN: building {saida.name} ({dur//60}min)...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=4500)
    concat_file.unlink(missing_ok=True)
    if result.returncode != 0:
        saida_tmp.unlink(missing_ok=True)
        raise RuntimeError(f"FFmpeg assembler EN failed: {result.stderr[-600:]}")
    saida_tmp.rename(saida)
    mb = saida.stat().st_size // (1024 * 1024)
    log.info(f"Assembler EN: {saida.name} ready ({mb} MB)")
    return saida

def loop_assembler():
    log.info("Assembler EN started — waiting for audio_*.mp3 in blocos/")
    while not _ev_parar.is_set():
        try:
            blocos_h = len(list(DIR_BLOCOS.glob("bloco_*_h.mp4")))
            if blocos_h >= ASSEMBLER_BLOCOS_MAX:
                log.info(f"Assembler EN: cap reached ({blocos_h}/{ASSEMBLER_BLOCOS_MAX}) — waiting for slot")
                now = time.time()
                for audio in list(DIR_BLOCOS.glob("audio_*.mp3")):
                    ts = audio.stem.replace("audio_", "")
                    bloco_existe = (DIR_BLOCOS / f"bloco_{ts}_h.mp4").exists()
                    audio_antigo = (now - audio.stat().st_mtime) > 86400
                    if bloco_existe or audio_antigo:
                        audio.unlink(missing_ok=True)
                _ev_parar.wait(timeout=300)
                continue
            for audio in sorted(DIR_BLOCOS.glob("audio_*.mp3")):
                ts      = audio.stem.replace("audio_", "")
                bloco_h = DIR_BLOCOS / f"bloco_{ts}_h.mp4"
                if bloco_h.exists():
                    audio.unlink(missing_ok=True)
                    continue
                try:
                    _montar_bloco_h(audio)
                    log.info(f"Assembler EN: {bloco_h.name} added to rotation.")
                    if bloco_h.exists():
                        audio.unlink(missing_ok=True)
                except Exception as e:
                    log.error(f"Assembler EN error ({audio.name}): {e}")
        except Exception as e:
            log.error(f"loop_assembler EN error: {e}")
        _ev_parar.wait(timeout=60)
    log.info("Assembler EN terminated.")


# ═══════════════════════════════════════════════════════════════════════
# THREAD: TRANSMITTER
# ═══════════════════════════════════════════════════════════════════════

def loop_transmissor():
    global _rotation_idx
    ciclo = 0

    if MODO_PERMANENTE:
        log.info("PERMANENT mode EN: using fixed stream key (no broadcasts via API)")
        log.info(f"  sk_h={STREAM_KEY_H[:8]}...")
        with _lock:
            _estado["live_id_h"] = BROADCAST_ID_H

        yt = None
        try:
            yt = get_youtube()
            log.info("YouTube API EN OK — new broadcast every 12h cycle.")
        except Exception as e:
            log.error(f"YouTube API EN unavailable ({e}) — NO auto-broadcast!")

        while not _ev_parar.is_set():
            ciclo += 1
            log.info(f"Transmitter EN — cycle {ciclo} of 12h")
            proc_h = None

            blocos = listar_blocos()
            while not blocos and not _ev_parar.is_set():
                log.warning("No EN blocks available — waiting 60s...")
                _ev_parar.wait(timeout=60)
                blocos = listar_blocos()
            if _ev_parar.is_set():
                break

            bid_h = None
            if yt:
                try:
                    _limpar_orfaos(yt)
                    bid_h = adotar_broadcast_ativo(yt)
                    if not bid_h:
                        bid_h = criar_broadcast_permanente(yt)
                    with _lock:
                        _estado["live_id_h"] = bid_h
                    threading.Thread(target=_publicar_apos_golive, args=(yt, bid_h),
                                     name="PublicaLiveEN", daemon=True).start()
                except Exception as e:
                    log.error(f"broadcast EN cycle: {e}")

            rot_idx_h = _rotation_idx % len(blocos)
            playlist_h, rot_idx_h, buf_h = _construir_playlist_rolling(
                blocos, rot_idx_h, ROLLING_INICIAIS)
            proc_h = _iniciar_proc_playlist(playlist_h, STREAM_KEY_H, "H")

            ciclo_start     = time.time()
            ultimo_check_bc = time.time()
            ultimo_suplica  = ciclo_start - (SUPLICA_INTERVAL - 5 * 60)
            ultimo_refresh_rtmp = ciclo_start - 1800  # offset -30min vs PL: EN dispara 3.5h após start, PL dispara 4h → nunca simultaneamente

            try:
                while not _ev_parar.is_set():
                    elapsed = time.time() - ciclo_start
                    if elapsed >= DURACAO_CICLO_SEG:
                        log.info(f"Cycle {ciclo}: 12h complete — stopping FFmpeg.")
                        break

                    if proc_h.poll() is not None:
                        rc = proc_h.returncode
                        log.warning(f"FFmpeg H EN stopped (rc={rc}) — rebuilding and restarting")
                        blocos_atuais = listar_blocos()
                        if blocos_atuais:
                            playlist_h, rot_idx_h, buf_nova = _construir_playlist_rolling(
                                blocos_atuais, rot_idx_h, ROLLING_INICIAIS)
                            buf_h = elapsed + buf_nova
                        proc_h = _iniciar_proc_playlist(playlist_h, STREAM_KEY_H, "H")

                    # Refresh periódico RTMP a cada 2h: previne degradação de sinal pelo YouTube
                    if (time.time() - ultimo_refresh_rtmp) >= 2 * 3600:
                        log.info("Periodic RTMP refresh EN: restarting FFmpeg H to maintain Excellent signal")
                        _matar_proc(proc_h, "H")
                        time.sleep(2)  # wait for YouTube to register disconnect before reconnecting
                        blocos_atuais = listar_blocos()
                        if blocos_atuais:
                            playlist_h, rot_idx_h, buf_nova = _construir_playlist_rolling(
                                blocos_atuais, rot_idx_h, ROLLING_INICIAIS)
                            buf_h = elapsed + buf_nova
                        proc_h = _iniciar_proc_playlist(playlist_h, STREAM_KEY_H, "H")
                        ultimo_refresh_rtmp = time.time()

                    if not _ev_suplica_gerar.is_set() and (time.time() - ultimo_suplica) >= SUPLICA_INTERVAL:
                        sups_prontas = len(list(DIR_SUPLICAS.glob("suplica_*_h.mp4")))
                        if sups_prontas < SUPLICA_MAX_READY:
                            _ev_suplica_gerar.set()
                            _ev_suplica_pronta.clear()
                            log.info(f"Supplications EN: triggering generation ({sups_prontas} ready)")
                        else:
                            log.info(f"Supplications EN: cap reached ({sups_prontas}/{SUPLICA_MAX_READY}) — skip")
                        ultimo_suplica = time.time()

                    if _ev_suplica_pronta.is_set():
                        with _lock_suplica:
                            sh = _suplica_caminhos.get("h")
                            _suplica_caminhos["h"] = None
                        _ev_suplica_pronta.clear()
                        if sh and sh.exists():
                            _append_playlist(playlist_h, sh)
                            buf_h += DURACAO_SUPLICA_SEG
                            h_next = blocos[rot_idx_h % len(blocos)]
                            _append_playlist(playlist_h, h_next)
                            buf_h += DURACAO_BLOCO_SEG
                            rot_idx_h = (rot_idx_h + 1) % len(blocos)
                            log.info(f"Supplication EN inserted | buf_remaining={buf_h - elapsed:.0f}s")

                    buf_restante = buf_h - elapsed
                    if buf_restante < ROLLING_ANTECIPACAO:
                        h_next = blocos[rot_idx_h % len(blocos)]
                        _append_playlist(playlist_h, h_next)
                        buf_h += DURACAO_BLOCO_SEG
                        rot_idx_h = (rot_idx_h + 1) % len(blocos)
                        log.info(f"Block EN appended (maintenance): {h_next.name} ({buf_h - elapsed:.0f}s)")

                    if yt and bid_h and (time.time() - ultimo_check_bc) >= 120:
                        ultimo_check_bc = time.time()
                        st = None
                        for _tentativa in range(3):
                            try:
                                itens = yt.liveBroadcasts().list(part="status", id=bid_h).execute().get("items", [])
                                st = itens[0].get("status", {}).get("lifeCycleStatus", "revoked") if itens else "revoked"
                                break
                            except Exception as e:
                                log.warning(f"watchdog broadcast EN (attempt {_tentativa+1}/3): {e}")
                                if _tentativa < 2:
                                    time.sleep(10)
                        if st in ("complete", "revoked"):
                            log.warning(f"Broadcast EN {bid_h} ended — creating new one")
                            _finalizar_broadcast(yt, bid_h)
                            bid_h = criar_broadcast_permanente(yt)
                            with _lock:
                                _estado["live_id_h"] = bid_h
                            threading.Thread(target=_publicar_apos_golive, args=(yt, bid_h),
                                             name="PublicaLiveEN", daemon=True).start()

                    _ev_parar.wait(timeout=10)
            finally:
                _matar_proc(proc_h, "H")
                with _lock:
                    _estado["proc_h"] = None

            if yt:
                try:
                    bid_fim = adotar_broadcast_ativo(yt) or bid_h
                except Exception:
                    bid_fim = bid_h
                if bid_fim:
                    _finalizar_broadcast(yt, bid_fim)
                with _lock:
                    _estado["live_id_h"] = None

            if _ev_parar.is_set():
                break
            log.info("EN 12h cycle complete — waiting 60s for YouTube to save VOD...")
            if _ev_parar.wait(timeout=60):
                break
            log.info(f"Restarting EN stream (cycle {ciclo + 1})...")
        return

    # Dynamic mode (no fixed stream key)
    yt = get_youtube()
    while not _ev_parar.is_set():
        ciclo += 1
        log.info(f"══════ EN CYCLE {ciclo} ══════")
        blocos = listar_blocos()
        while not blocos:
            log.warning("Waiting for EN blocks from GitHub Actions... retry in 60s")
            if _ev_parar.wait(timeout=60):
                return
            blocos = listar_blocos()
        log.error("DYNAMIC MODE EN not supported — set STREAM_KEY_H_EN in .env")
        _ev_parar.wait(timeout=600)


# ═══════════════════════════════════════════════════════════════════════
# THREAD: MONITOR
# ═══════════════════════════════════════════════════════════════════════

def loop_monitor():
    while not _ev_parar.is_set():
        try:
            blocos = listar_blocos()
            sups   = list(DIR_SUPLICAS.glob("suplica_*_h.mp4"))
            log.info(f"MONITOR EN | blocks={len(blocos)} | supplications_ready={len(sups)}")

            if len(blocos) < BLOCOS_MINIMOS:
                log.warning(f"ALERT EN: only {len(blocos)} block(s) available.")

            stat = os.statvfs(str(BASE_DIR))
            livre_gb = stat.f_bavail * stat.f_frsize / 1e9
            if livre_gb < 5:
                log.warning(f"DISK: only {livre_gb:.1f} GB free!")
        except Exception as e:
            log.warning(f"MONITOR EN: {e}")
        _ev_parar.wait(timeout=300)


# ═══════════════════════════════════════════════════════════════════════
# RESPOSTA AO CHAT AO VIVO
# ═══════════════════════════════════════════════════════════════════════

_CHAT_GEMINI_KEYS_EN = [k for k in [
    os.environ.get("GEMINI_KEY_LIVE_CONTENT_1_EN", ""),
    os.environ.get("GEMINI_KEY_LIVE_CONTENT_2_EN", ""),
] if k]

def _eh_mensagem_respondivel_en(texto: str) -> bool:
    import re
    if len(texto) < 6:
        return False
    if re.fullmatch(r'[\W\d\s]+', texto):
        return False
    if len(texto.split()) == 1 and len(texto) < 15:
        return False
    return True

def _gerar_resposta_chat_en(autor: str, texto: str) -> str | None:
    chaves = _CHAT_GEMINI_KEYS_EN
    if not chaves:
        return None
    t = texto.lower()
    if any(p in t for p in ["i'm the only", "im the only", "only one here",
                              "alone here", "i'm alone", "im alone"]):
        return ("You're not alone! 🙏 Our Lady watches over everyone who joins us in prayer. "
                "Share this blessing with someone who needs a miracle today! ❤️")
    prompt = (
        f"You are the Our Lady prayer channel, responding in the 24/7 live chat.\n\n"
        f"A viewer named @{autor} wrote: \"{texto}\"\n\n"
        f"Reply in English with 1 short sentence (max 180 characters): "
        f"warm, devout, welcoming. Mention Our Lady / Blessed Virgin Mary if natural. "
        f"If it's a prayer request, confirm it will be lifted. "
        f"No markdown, asterisks, or hashtags."
    )
    for chave in chaves:
        try:
            from google.genai import Client as GClient
            gc = GClient(api_key=chave, http_options={'api_version': 'v1'})
            return gc.models.generate_content(model='gemini-2.5-flash-lite', contents=prompt).text.strip()[:200]
        except Exception as e:
            if "429" in str(e) and chave != chaves[-1]:
                continue
            log.warning(f"chat_gemini EN: {e}")
            return None
    return None

def loop_respostas_chat():
    yt = get_youtube()
    ids_vistos: set = set()
    INTERVALO = 5 * 60
    MAX_POR_HORA = 12
    respostas_hora = 0
    hora_inicio = time.time()

    while not _ev_parar.is_set():
        _ev_parar.wait(timeout=INTERVALO)
        if _ev_parar.is_set():
            break

        if time.time() - hora_inicio >= 3600:
            respostas_hora = 0
            hora_inicio = time.time()
        if respostas_hora >= MAX_POR_HORA:
            continue

        with _lock:
            bid_h = _estado.get("live_id_h")
        if not bid_h:
            continue

        try:
            b = yt.liveBroadcasts().list(part="snippet", id=bid_h).execute()
            if not b.get("items"):
                continue
            chat_id = b["items"][0]["snippet"].get("liveChatId")
            if not chat_id:
                continue

            resp = yt.liveChatMessages().list(
                part="snippet,authorDetails", liveChatId=chat_id, maxResults=50
            ).execute()

            respondeu = False
            for item in resp.get("items", []):
                msg_id = item["id"]
                if msg_id in ids_vistos:
                    continue
                ids_vistos.add(msg_id)
                if respondeu:
                    continue
                texto = item["snippet"].get("displayMessage", "").strip()
                autor = item["authorDetails"].get("displayName", "friend")
                if not _eh_mensagem_respondivel_en(texto):
                    continue
                resposta = _gerar_resposta_chat_en(autor, texto)
                if resposta:
                    try:
                        yt.liveChatMessages().insert(
                            part="snippet",
                            body={"snippet": {"liveChatId": chat_id, "type": "textMessageEvent",
                                              "textMessageDetails": {"messageText": resposta}}},
                        ).execute()
                        log.info(f"Chat EN respondido: @{autor} → {resposta[:60]}...")
                        respondeu = True
                        respostas_hora += 1
                    except Exception as e:
                        log.warning(f"Chat EN insert: {e}")

            if len(ids_vistos) > 2000:
                ids_vistos = set(list(ids_vistos)[-500:])
        except Exception as e:
            log.warning(f"loop_respostas_chat EN: {e}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    log.info("═══════════════════════════════════════════════════════")
    log.info(" ao_vivo_en.py — Canal EN — Blessed Virgin Mary")
    log.info("═══════════════════════════════════════════════════════")

    for d in [DIR_BLOCOS, DIR_SUPLICAS, DIR_INSUMOS_H,
              DIR_MUSICAS_M, DIR_MUSICAS_N]:
        d.mkdir(parents=True, exist_ok=True)

    for tmp in DIR_BLOCOS.glob("*.tmp.mp4"):
        tmp.unlink(missing_ok=True)
        log.info(f"Startup: removed incomplete block {tmp.name}")

    log.info("Checking assets for EN supplications...")
    garantir_assets_vps()

    threads = [
        threading.Thread(target=loop_suplicas,        name="Suplicas",   daemon=True),
        threading.Thread(target=loop_transmissor,     name="Transmissor", daemon=True),
        threading.Thread(target=loop_monitor,         name="Monitor",     daemon=True),
        threading.Thread(target=loop_assembler,       name="Assembler",   daemon=True),
        threading.Thread(target=loop_respostas_chat,  name="ChatBot",     daemon=True),
    ]
    for t in threads:
        t.start()
    log.info("EN threads started. System operational.")

    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Shutting down ao_vivo_en...")
        _ev_parar.set()
        _ev_suplica_gerar.set()
        with _lock:
            _matar_proc(_estado.get("proc_h"), "H")
        for t in threads:
            t.join(timeout=15)
        log.info("ao_vivo_en.py terminated.")


if __name__ == "__main__":
    main()
