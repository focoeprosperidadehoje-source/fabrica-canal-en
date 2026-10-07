#!/usr/bin/env python3
"""Rotaciona o título do broadcast ao vivo com base no slot do dia."""
import json, os, sys, datetime
import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

TOKEN_JSON_STR = os.environ["YOUTUBE_TOKEN_JSON"]
TZ_NAME = os.environ.get("TZ_NAME", "UTC")
TITULOS_STR = os.environ["TITULOS_JSON"]

try:
    decoder = json.JSONDecoder()
    token, _ = decoder.raw_decode(TOKEN_JSON_STR.lstrip("﻿"))
except Exception as e:
    print(f"Erro ao parsear token: {e}")
    sys.exit(1)

titulos = json.loads(TITULOS_STR)
tz = pytz.timezone(TZ_NAME)
now = datetime.datetime.now(tz)
hour = now.hour

if 6 <= hour < 12:
    slot = "manha"
elif 12 <= hour < 18:
    slot = "tarde"
elif 18 <= hour < 24:
    slot = "noite"
else:
    slot = "madrugada"

titulo = titulos.get(slot)
if not titulo:
    print(f"Slot '{slot}' sem título configurado.")
    sys.exit(0)

print(f"[{now.strftime('%H:%M')} {TZ_NAME}] Slot: {slot} → {titulo}")

creds = Credentials(
    token=token.get("access_token") or token.get("token"),
    refresh_token=token.get("refresh_token"),
    token_uri="https://oauth2.googleapis.com/token",
    client_id=token.get("client_id"),
    client_secret=token.get("client_secret"),
)

if creds.expired and creds.refresh_token:
    try:
        creds.refresh(Request())
    except Exception as e:
        print(f"Aviso refresh: {e}")

yt = build("youtube", "v3", credentials=creds)

try:
    resp = yt.liveBroadcasts().list(
        part="id,snippet,status",
        broadcastStatus="active",
        maxResults=5,
    ).execute()
    items = resp.get("items", [])
except HttpError as e:
    if "quotaExceeded" in str(e):
        print("Cota esgotada — encerrando sem erro.")
        sys.exit(0)
    print(f"Erro ao listar broadcasts: {e}")
    sys.exit(1)

if not items:
    print("Nenhum broadcast ativo encontrado.")
    sys.exit(0)

broadcast = items[0]
bid = broadcast["id"]
snippet = broadcast["snippet"]
current_title = snippet.get("title", "")

if current_title == titulo:
    print(f"Título já correto: {titulo}")
    sys.exit(0)

snippet["title"] = titulo
try:
    yt.liveBroadcasts().update(
        part="snippet",
        body={"id": bid, "snippet": snippet},
    ).execute()
    print(f"✅ '{current_title}' → '{titulo}'")
except HttpError as e:
    print(f"Erro ao atualizar título: {e}")
    sys.exit(1)
