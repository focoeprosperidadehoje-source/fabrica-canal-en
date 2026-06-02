import os, json, time, datetime, gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.genai import Client

GOOGLE_JSON = os.environ.get("GOOGLE_CREDENTIALS_EN")
YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_EN")
CHAVE_API_GEMINI = os.environ.get("GEMINI_API_KEY")

creds_sheets = Credentials.from_service_account_info(json.loads(GOOGLE_JSON), scopes=['https://www.googleapis.com/auth/spreadsheets'])
gc = gspread.authorize(creds_sheets)
configs = gc.open_by_key("1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU").worksheet("Configuracoes").get_all_records()

creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON))
if creds_yt and creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)
gemini_client = Client(api_key=CHAVE_API_GEMINI, http_options={'api_version': 'v1'})

def obter_modelo_lite():
    try:
        modelos = gemini_client.models.list()
        lite_models = [m.name for m in modelos if 'generateContent' in m.supported_generation_methods and 'flash-lite' in m.name]
        return sorted(lite_models, reverse=True)[0] if lite_models else 'gemini-2.5-flash'
    except:
        return 'gemini-2.5-flash-lite'

modelo_comunidade = obter_modelo_lite()
print(f"🤖 AI model selected for Community: {modelo_comunidade}")

canal_response = youtube.channels().list(part='id,contentDetails', mine=True).execute()
MEU_CANAL_ID = canal_response['items'][0]['id']
UPLOADS_PLAYLIST_ID = canal_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

print("💬 STARTING THE COMMUNITY MANAGER (PINNED COMMENTS)")
texto_fixo = next((str(c.get('Texto Fixo', c.get('Texto_Fixo', ''))) for c in configs if str(c.get('Idioma', '')).upper() == 'EN'), "")

if texto_fixo:
    limite_24h = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    playlist_req = youtube.playlistItems().list(part='snippet', playlistId=UPLOADS_PLAYLIST_ID, maxResults=15).execute()
    video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_req.get('items', [])]

    if video_ids:
        videos_req = youtube.videos().list(part='snippet', id=','.join(video_ids)).execute()
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
                            comentario_final = f"{texto_fixo}\n\nKeep praying with us here: {link_playlist}"

                        youtube.commentThreads().insert(part="snippet", body={"snippet": {"videoId": v_id, "topLevelComment": {"snippet": {"textOriginal": comentario_final}}}}).execute()
                        print(f"   ✅ Pinned comment posted on: {v_titulo[:30]}")
                        time.sleep(2)
                except: pass

print("\n🕊️ STARTING THE DIGITAL PASTOR (LIKES AND PERSONALIZED REPLIES)")
try:
    threads = youtube.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=MEU_CANAL_ID, maxResults=20).execute()
    for thread in threads.get('items', []):
        top = thread['snippet']['topLevelComment']['snippet']
        comentario_id = thread['snippet']['topLevelComment']['id']

        if top.get('authorChannelId', {}).get('value') == MEU_CANAL_ID: continue

        try: youtube.comments().rate(id=comentario_id, rating='like').execute()
        except: pass

        ja_respondi = any(r['snippet'].get('authorChannelId', {}).get('value') == MEU_CANAL_ID for r in thread.get('replies', {}).get('comments', []))
        if not ja_respondi:
            nome, texto = top.get('authorDisplayName', 'Friend'), top.get('textOriginal', '')

            prompt = f"""Act as an empathetic Catholic digital pastor. A user named '{nome}' commented: '{texto}'.
            RULE 1 (HATE COMMENTS): If it is a hateful comment, religious intolerance or criticism of AI use, respond with extreme politeness, saying that we respect differences, asking to focus on God's love and let go of small things.
            RULE 2 (FAITHFUL): If it is a prayer request, personal struggle or gratitude, respond in a HIGHLY PERSONALIZED way. Acknowledge the pain or situation the person mentioned and offer a specific word of comfort or prayer for their case.
            Maximum 3 to 4 lines. Warm and human tone. NO quotes."""

            try:
                resposta = gemini_client.models.generate_content(model=modelo_comunidade, contents=prompt).text.strip()
                youtube.comments().insert(part="snippet", body={"snippet": {"parentId": thread['id'], "textOriginal": resposta}}).execute()
                print(f"   ✅ Replied and Liked: {nome}")
                time.sleep(3)
            except: pass
except: pass
print("🚀 COMMUNITY STAGE COMPLETED!")
