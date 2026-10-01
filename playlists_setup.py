# -*- coding: utf-8 -*-
"""
playlists_setup.py — garante que as playlists das Novenas existam ANTES do 1º upload
(e, no ES, cria/atualiza a playlist curada de maior retenção).

Fontes dos nomes (exatamente os mesmos que o publicador procura em _playlist_novena):
  1) coluna Tema da aba do canal: linhas "NOVENA|<playlist>|<dia>|<tipo>|<chave>"
  2) festas tradicionais dos próximos 100 dias (novenas.plano_do_dia -> nome_playlist)

Idempotente: só cria o que não existe; só adiciona à curada o vídeo que ainda não está nela.
Env: CANAL (ES/PT/EN/PL/FR/IT), GOOGLE_CREDENTIALS[_XX], YOUTUBE_TOKEN_XX, CURADA_TITULO, CURADA_IDS (opcionais)
"""
import os, json, datetime, sys, traceback

def _anotar(e):
    msg = str(e).replace("\n", " ")[:400]
    print(f"::error::playlists_setup falhou: {type(e).__name__}: {msg}")

sys.excepthook = lambda t, v, tb: (traceback.print_exception(t, v, tb), _anotar(v))
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CANAL = os.environ["CANAL"].upper()
PLANILHA = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"

DESC = {
    "PT": "{n} — todos os dias da novena em ordem. Reze conosco e deixe sua intenção nos comentários.",
    "ES": "{n} — todos los días de la novena en orden. Reza con nosotros y deja tu intención en los comentarios.",
    "EN": "{n} — every day of the novena in order. Pray with us and leave your intention in the comments.",
    "PL": "{n} — wszystkie dni nowenny po kolei. Módl się z nami i zostaw swoją intencję w komentarzu.",
    "FR": "{n} — tous les jours de la neuvaine dans l'ordre. Priez avec nous et laissez votre intention en commentaire.",
    "IT": "{n} — tutti i giorni della novena in ordine. Prega con noi e lascia la tua intenzione nei commenti.",
}
LANG = {"PT": "pt-BR", "ES": "es-MX", "EN": "en-US", "PL": "pl", "FR": "fr-FR", "IT": "it-IT"}

gjson = os.environ.get(f"GOOGLE_CREDENTIALS_{CANAL}") or os.environ.get("GOOGLE_CREDENTIALS")
creds = Credentials.from_service_account_info(json.loads(gjson.strip().lstrip("\ufeff")), scopes=[
    "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
gc = gspread.authorize(creds)

yt_creds = YTCredentials.from_authorized_user_info(json.loads(os.environ[f"YOUTUBE_TOKEN_{CANAL}"].strip().lstrip("\ufeff")))
if yt_creds.expired and yt_creds.refresh_token:
    yt_creds.refresh(Request())
youtube = build("youtube", "v3", credentials=yt_creds)

# ---------- 1) nomes necessários ----------
necessarias = []
try:
    linhas = gc.open_by_key(PLANILHA).worksheet(CANAL).get_all_records(expected_headers=[])
    for l in linhas:
        t = str(l.get("Tema", "")).strip()
        if t.startswith("NOVENA|"):
            partes = t.split("|")
            if len(partes) > 1 and partes[1].strip() and partes[1].strip() != "None":
                necessarias.append(partes[1].strip()[:150])
except Exception as e:
    print(f"⚠️ Falha lendo planilha: {e}")

try:
    import novenas
    d = datetime.date.today()
    for _ in range(100):
        p = novenas.plano_do_dia(d)
        if p and p.get("tipo") == "festa":
            necessarias.append(novenas.nome_playlist(p).strip()[:150])
        d += datetime.timedelta(days=1)
except Exception as e:
    print(f"⚠️ Falha calculando festas: {e}")

necessarias = list(dict.fromkeys(necessarias))
print(f"📋 Playlists de novena necessárias ({len(necessarias)}):")
for n in necessarias:
    print("   -", n)

# ---------- 2) playlists existentes ----------
existentes = {}
token = None
while True:
    r = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
    for p in r.get("items", []):
        existentes[p["snippet"]["title"].strip()] = p["id"]
    token = r.get("nextPageToken")
    if not token:
        break
print(f"📂 Playlists já existentes no canal: {len(existentes)}")


def garantir(nome, descricao):
    if nome in existentes:
        print(f"   ✔ já existe: {nome} ({existentes[nome]})")
        return existentes[nome]
    novo = youtube.playlists().insert(part="snippet,status", body={
        "snippet": {"title": nome, "description": descricao, "defaultLanguage": LANG[CANAL]},
        "status": {"privacyStatus": "public"}}).execute()
    existentes[nome] = novo["id"]
    print(f"   ➕ criada: {nome} ({novo['id']})")
    return novo["id"]


for n in necessarias:
    try:
        garantir(n, DESC[CANAL].format(n=n))
    except Exception as e:
        print(f"   ❌ erro em {n}: {e}"); _anotar(e)

# ---------- 3) playlist curada (maior retenção) ----------
titulo_c = os.environ.get("CURADA_TITULO", "").strip()
ids_c = [i.strip() for i in os.environ.get("CURADA_IDS", "").split(",") if i.strip()]
if titulo_c and ids_c:
    print(f"\n⭐ Playlist curada: {titulo_c}")
    try:
        pid = garantir(titulo_c, os.environ.get("CURADA_DESC", titulo_c))
        ja = set()
        token = None
        while True:
            r = youtube.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50, pageToken=token).execute()
            ja.update(i["contentDetails"]["videoId"] for i in r.get("items", []))
            token = r.get("nextPageToken")
            if not token:
                break
        for pos, vid in enumerate(ids_c):
            if vid in ja:
                print(f"   ✔ {vid} já está")
                continue
            try:
                youtube.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": pid,
                    "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
                print(f"   ➕ {vid} adicionado (pos {pos})")
            except Exception as e:
                print(f"   ❌ {vid}: {e}")
        print(f"   🔗 https://www.youtube.com/playlist?list={pid}")
    except Exception as e:
        print(f"   ❌ curada: {e}")

print(f"::notice::playlists_setup OK — {len(necessarias)} playlists de novena verificadas")
# ---------- 4) vídeos de novena dentro das playlists (corrige falha de cota no upload) ----------
try:
    import re as _re
    _novena_ids = {existentes[n] for n in necessarias if n in existentes}
    if _novena_ids:
        _ch = youtube.channels().list(part="contentDetails", mine=True).execute()
        _up = _ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        _r = youtube.playlistItems().list(part="snippet,contentDetails", playlistId=_up, maxResults=50).execute()
        _limite = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        _pend = []
        for _it in _r.get("items", []):
            _sn = _it["snippet"]
            try:
                _pub = datetime.datetime.strptime(_sn.get("publishedAt", "")[:19], "%Y-%m-%dT%H:%M:%S")
                if _pub < _limite:
                    continue
            except Exception:
                pass
            _m = _re.search(r"playlist\?list=([A-Za-z0-9_-]+)", _sn.get("description", "") or "")
            _pid_v = _m.group(1) if (_m and _m.group(1) in _novena_ids) else None
            if not _pid_v:
                # sem link na descrição (playlist indisponível no upload): casa pelo título
                _chave = _re.split(r"\s[–—-]\s|\s\d+º\s*Dia", _sn.get("title", ""))[0].strip().lower()
                _cands = [existentes[n] for n in necessarias if n in existentes and len(_chave) >= 10
                          and n.lower().startswith(_chave)]
                if _cands:
                    _pid_v = _cands[-1]
            if _pid_v:
                _pend.append((_it["contentDetails"]["videoId"], _pid_v, _sn.get("title", "")))
        _cache = {}
        for _vid, _pid, _tit in reversed(_pend):  # mais antigo primeiro = ordem dos dias
            if _pid not in _cache:
                _ja, _tok = set(), None
                while True:
                    _rr = youtube.playlistItems().list(part="contentDetails", playlistId=_pid, maxResults=50, pageToken=_tok).execute()
                    _ja.update(i["contentDetails"]["videoId"] for i in _rr.get("items", []))
                    _tok = _rr.get("nextPageToken")
                    if not _tok:
                        break
                _cache[_pid] = _ja
            if _vid in _cache[_pid]:
                continue
            try:
                youtube.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": _pid, "resourceId": {"kind": "youtube#video", "videoId": _vid}}}).execute()
                _cache[_pid].add(_vid)
                print(f"   ➕ novena na playlist: {_tit[:70]} ({_vid}) -> {_pid}")
            except Exception as e:
                print(f"   ❌ novena {_vid}: {e}")
        print(f"🔁 Vídeos de novena verificados: {len(_pend)}")
except Exception as e:
    print(f"⚠️ Sincronização de vídeos da novena: {e}")

print("\n✅ FIM")
