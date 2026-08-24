import os, json, time, datetime, gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.genai import Client

GOOGLE_JSON = os.environ.get("GOOGLE_CREDENTIALS_EN")
YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_EN")
CHAVE_API_GEMINI = os.environ.get("GEMINI_API_KEY", "")
CHAVE_API_GEMINI_2 = os.environ.get("GEMINI_API_KEY_2", "")
CHAVES_GEMINI = [k for k in [CHAVE_API_GEMINI, CHAVE_API_GEMINI_2] if k]

MAX_RESPOSTAS = 30

creds_sheets = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=['https://www.googleapis.com/auth/spreadsheets'])
gc = gspread.authorize(creds_sheets)
configs = gc.open_by_key("1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU").worksheet("Configuracoes").get_all_records()

creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON))
if creds_yt and creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)
gemini_client = Client(api_key=CHAVES_GEMINI[0], http_options={'api_version': 'v1'})

def _gerar_comunidade(prompt):
    for chave in CHAVES_GEMINI:
        try:
            c = Client(api_key=chave, http_options={'api_version': 'v1'})
            return c.models.generate_content(model=modelo_comunidade, contents=prompt).text.strip()
        except Exception as e:
            if "429" in str(e) and chave != CHAVES_GEMINI[-1]:
                print(f"[WARN] 429 on key ...{chave[-6:]}. Trying key 2...")
                continue
            raise
    raise RuntimeError("All Gemini keys failed.")

def obter_modelo_lite():
    # gemini-2.5-flash-lite: free tier, 15 RPM, ~1000 RPD por projeto
    try:
        modelos = gemini_client.models.list()
        nomes = [m.name for m in modelos if 'generateContent' in m.supported_generation_methods]
        for preferido in ['gemini-2.5-flash-lite', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite']:
            if any(preferido in n for n in nomes):
                return preferido
        return 'gemini-2.5-flash-lite'
    except:
        return 'gemini-2.5-flash-lite'

modelo_comunidade = obter_modelo_lite()
print(f"🤖 AI model selected for Community: {modelo_comunidade}")

canal_response = youtube.channels().list(part='id,contentDetails', mine=True).execute()
MEU_CANAL_ID = canal_response['items'][0]['id']
UPLOADS_PLAYLIST_ID = canal_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

LINK_LIVE = f"https://www.youtube.com/channel/{MEU_CANAL_ID}/live"

# ── ENABLE COMMENTS (videos from last 72h) ───────────────────────────────────
print("🔓 ENABLING COMMENTS on recent videos...")
try:
    limite_72h = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=72)
    video_ids_72h = []
    page_token_72 = None
    for _ in range(2):
        resp = youtube.playlistItems().list(
            part='snippet', playlistId=UPLOADS_PLAYLIST_ID,
            maxResults=50, pageToken=page_token_72
        ).execute()
        for item in resp.get('items', []):
            pub = item['snippet'].get('publishedAt', '')
            try:
                pt = datetime.datetime.strptime(pub, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                if pt >= limite_72h:
                    video_ids_72h.append(item['snippet']['resourceId']['videoId'])
            except: pass
        page_token_72 = resp.get('nextPageToken')
        if not page_token_72: break
    for vid in video_ids_72h:
        try:
            youtube.videos().update(
                part="status",
                body={"id": vid, "status": {"selfDeclaredMadeForKids": False, "selfDeclaredMadeWithAlteredContent": True}}
            ).execute()
            print(f"   🔓 Status updated: {vid}")
            time.sleep(1)
        except Exception as e:
            print(f"   ⚠️ Could not update {vid}: {e}")
except Exception as e:
    print(f"⚠️ Enable comments: {e}")

# ── COMMUNITY MANAGER ─────────────────────────────────────────────────────────
print("\n💬 STARTING THE COMMUNITY MANAGER (PINNED COMMENTS)")
texto_fixo = next((str(c.get('Texto Fixo', c.get('Texto_Fixo', ''))) for c in configs if str(c.get('Idioma', '')).upper() == 'EN'), "")

if texto_fixo:
    limite_24h = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    video_ids = []
    page_token_up = None
    for _ in range(4):
        resp_up = youtube.playlistItems().list(
            part='snippet', playlistId=UPLOADS_PLAYLIST_ID,
            maxResults=50, pageToken=page_token_up
        ).execute()
        video_ids += [item['snippet']['resourceId']['videoId'] for item in resp_up.get('items', [])]
        page_token_up = resp_up.get('nextPageToken')
        if not page_token_up: break

    if video_ids:
        videos_req = youtube.videos().list(part='snippet', id=','.join(video_ids[:50])).execute()
        for video in videos_req.get('items', []):
            v_id, v_titulo = video['id'], video['snippet']['title']
            pub_time = datetime.datetime.strptime(video['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            if pub_time >= limite_24h:
                try:
                    comentarios = youtube.commentThreads().list(part='snippet', videoId=v_id, maxResults=100).execute()
                    if not any(t['snippet']['topLevelComment']['snippet'].get('authorChannelId', {}).get('value') == MEU_CANAL_ID for t in comentarios.get('items', [])):
                        if "#shorts" in v_titulo.lower():
                            comentario_final = f"{texto_fixo}\n\n🙏 May this quick prayer bless your day! Visit our channel for the full prayers.\n\nOur Playlists:\n🌅 Morning Prayers: https://www.youtube.com/playlist?list=PLcBcFg8r0RDmY0zEywQRGDDVEprFvK-QI\n🌌 Evening Prayers: https://www.youtube.com/playlist?list=PLcBcFg8r0RDkgQba8FVPPgHW0NgHEOzSm"
                        else:
                            link_playlist = "https://www.youtube.com/playlist?list=PLcBcFg8r0RDmY0zEywQRGDDVEprFvK-QI"
                            if "morning" in v_titulo.lower(): link_playlist = "https://www.youtube.com/playlist?list=PLcBcFg8r0RDmY0zEywQRGDDVEprFvK-QI"
                            elif "night" in v_titulo.lower() or "sleep" in v_titulo.lower() or "evening" in v_titulo.lower(): link_playlist = "https://www.youtube.com/playlist?list=PLcBcFg8r0RDkgQba8FVPPgHW0NgHEOzSm"
                            comentario_final = f"{texto_fixo}\n\nKeep praying with us here: {link_playlist}\n\n🔴 LIVE NOW — 24/7: your prayers and the names of your loved ones are lifted in continuous intercession. Join us: {LINK_LIVE}"
                        youtube.commentThreads().insert(part="snippet", body={"snippet": {"videoId": v_id, "topLevelComment": {"snippet": {"textOriginal": comentario_final}}}}).execute()
                        print(f"   ✅ Pinned comment posted on: {v_titulo[:30]}")
                        time.sleep(2)
                except Exception as e:
                    print(f"   ⚠️ Error commenting on {v_id}: {e}")

# ── DIGITAL PASTOR ────────────────────────────────────────────────────────────
print("\n🕊️ STARTING THE DIGITAL PASTOR (PERSONALIZED REPLIES)")
try:
    respondidos = 0
    page_token_t = None
    for _pagina in range(10):  # up to 1000 threads per run
        if respondidos >= MAX_RESPOSTAS:
            print(f"   ℹ️ Cap of {MAX_RESPOSTAS} replies reached — next run continues.")
            break
        threads_resp = youtube.commentThreads().list(
            part="snippet,replies",
            allThreadsRelatedToChannelId=MEU_CANAL_ID,
            maxResults=100,
            pageToken=page_token_t
        ).execute()
        for thread in threads_resp.get('items', []):
            if respondidos >= MAX_RESPOSTAS:
                break
            top = thread['snippet']['topLevelComment']['snippet']
            autor_id = top.get('authorChannelId', {}).get('value')
            if autor_id == MEU_CANAL_ID:
                continue
            ja_respondi = any(
                r['snippet'].get('authorChannelId', {}).get('value') == MEU_CANAL_ID
                for r in thread.get('replies', {}).get('comments', [])
            )
            if not ja_respondi:
                nome  = top.get('authorDisplayName', 'Friend')
                texto = top.get('textOriginal', '')
                prompt = (
                    f"Act as an empathetic Catholic digital pastor. A user named '{nome}' commented: '{texto}'. "
                    f"RULE 1 (HATE COMMENTS): If hateful, intolerant or criticizes AI use, respond with extreme politeness, respecting differences, focusing on God's love. "
                    f"RULE 2 (FAITHFUL): If a prayer request, struggle or gratitude, respond HIGHLY PERSONALIZED. Acknowledge their pain/situation and offer specific comfort or prayer. "
                    f"If they mention illness, suffering or intercession, organically invite them to our 24/7 stream: {LINK_LIVE} "
                    f"Maximum 3-4 lines. Warm and human tone. NO quotes."
                )
                try:
                    resposta = _gerar_comunidade(prompt)
                    youtube.comments().insert(
                        part="snippet",
                        body={"snippet": {"parentId": thread['id'], "textOriginal": resposta}}
                    ).execute()
                    print(f"   ✅ Replied to {nome}")
                    respondidos += 1
                    time.sleep(3)
                except Exception as e:
                    print(f"   ⚠️ Error replying to {nome}: {e}")
        page_token_t = threads_resp.get('nextPageToken')
        if not page_token_t:
            break
    print(f"   Total replied in this run: {respondidos}")
except Exception as e:
    print(f"⚠️ DIGITAL PASTOR general error: {e}")
print("🚀 COMMUNITY STAGE COMPLETED!")
