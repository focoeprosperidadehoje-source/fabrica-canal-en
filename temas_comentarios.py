# -*- coding: utf-8 -*-
"""
temas_comentarios.py — Ranking semanal das dores mais pedidas nos comentários (canal fabrica-canal-en).
Alimenta a escolha do tema das novenas de pedido do slot 06:00 (novenas.py).

Custo YouTube API: ~1 unidade por página de 100 comentários (máx. 5 páginas).
Grava na aba TEMAS_COMENTARIOS: [Canal, Data, Categoria, Contagem].
Somente leitura no YouTube — não responde, não curte, não altera nada.
"""
import os, json, re, datetime, gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.genai import Client
import novenas

ID_PLANILHA = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"
MAX_PAGINAS = 5
DIAS_JANELA = 30

GOOGLE_JSON = os.environ.get("GOOGLE_CREDENTIALS_EN")
YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_EN")
CHAVES = [k for k in [os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_API_KEY_2", "")] if k]

creds_sheets = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=['https://www.googleapis.com/auth/spreadsheets'])
planilha = gspread.authorize(creds_sheets).open_by_key(ID_PLANILHA)

creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON.lstrip('﻿')))
if creds_yt and creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)

canal_id = youtube.channels().list(part='id', mine=True).execute()['items'][0]['id']
limite = datetime.datetime.utcnow() - datetime.timedelta(days=DIAS_JANELA)

comentarios, token = [], None
for _ in range(MAX_PAGINAS):
    resp = youtube.commentThreads().list(part='snippet', allThreadsRelatedToChannelId=canal_id,
                                         maxResults=100, order='time', textFormat='plainText',
                                         pageToken=token).execute()
    parar = False
    for it in resp.get('items', []):
        s = it['snippet']['topLevelComment']['snippet']
        if s.get('authorChannelId', {}).get('value') == canal_id:
            continue  # ignora respostas/comentários do próprio canal
        pub = datetime.datetime.strptime(s['publishedAt'][:19], "%Y-%m-%dT%H:%M:%S")
        if pub < limite:
            parar = True; break
        txt = re.sub(r'\s+', ' ', s.get('textDisplay', '')).strip()
        if len(txt) >= 8:
            comentarios.append(txt[:220])
    token = resp.get('nextPageToken')
    if parar or not token: break

print(f"💬 {len(comentarios)} comentários dos últimos {DIAS_JANELA} dias.")
if len(comentarios) < novenas.MIN_COMENTARIOS_RANKING:
    print("Volume insuficiente — a usina usará a rotação de fallback. Nada gravado.")
    raise SystemExit(0)

cats = "\n".join(f"- {k}: {v[1]}" for k, v in novenas.CATEGORIAS.items())
lista = "\n".join(f"{i+1}. {c}" for i, c in enumerate(comentarios))
prompt = f"""Classifique cada comentário abaixo (fiéis de um canal católico) em NO MÁXIMO UMA categoria de pedido de oração.
Comentários sem pedido de oração (só "amém", elogios, spam) NÃO entram na contagem.
CATEGORIAS:
{cats}

COMENTÁRIOS:
{lista}

Responda APENAS com linhas no formato chave=quantidade, uma por categoria, usando exatamente as chaves acima. Exemplo:
saude=12
familia=7"""

texto = None
for chave in CHAVES:
    try:
        c = Client(api_key=chave, http_options={'api_version': 'v1'})
        try:
            nomes = [m.name.replace('models/', '') for m in c.models.list() if 'generateContent' in (m.supported_generation_methods or [])]
        except Exception:
            nomes = []
        lites = sorted([n for n in nomes if 'flash' in n and 'lite' in n], reverse=True)
        flashes = sorted([n for n in nomes if 'flash' in n and 'lite' not in n], reverse=True)
        candidatos = (lites[:2] + flashes[:1]) or ['gemini-2.5-flash']
        for modelo in candidatos:
            try:
                texto = c.models.generate_content(model=modelo, contents=prompt).text
                break
            except Exception as e:
                print(f"[WARN] {modelo}: {e}")
        if texto: break
    except Exception as e:
        print(f"[WARN] chave ...{chave[-6:]}: {e}")
if not texto:
    print("❌ Gemini indisponível — nada gravado (fallback continua valendo).")
    raise SystemExit(0)

contagem = {}
for k, v in re.findall(r'([a-z_]+)\s*[=:]\s*(\d+)', texto.lower()):
    if k in novenas.CATEGORIAS:
        contagem[k] = contagem.get(k, 0) + int(v)
if not contagem:
    print(f"❌ Resposta não interpretável: {texto[:300]}")
    raise SystemExit(0)

hoje = datetime.date.today().isoformat()
try:
    ws = planilha.worksheet(novenas.ABA_TEMAS)
except Exception:
    ws = planilha.add_worksheet(title=novenas.ABA_TEMAS, rows=1000, cols=4)
    ws.update(values=[["Canal", "Data", "Categoria", "Contagem"]], range_name="A1")
linhas = [[novenas.CANAL, hoje, k, v] for k, v in sorted(contagem.items(), key=lambda x: -x[1])]
ws.append_rows(linhas)
print("📊 Ranking gravado:", ", ".join(f"{k}={v}" for k, v in sorted(contagem.items(), key=lambda x: -x[1])))
