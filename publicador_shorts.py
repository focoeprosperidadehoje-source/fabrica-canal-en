import os, random, re, datetime, time, subprocess, pytz, json, gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as YTCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
import textwrap
from googleapiclient.discovery import build as build_drive

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

GOOGLE_JSON = os.environ.get("GOOGLE_CREDENTIALS_EN")
YT_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_EN_SHORTS")
HORARIO_ALVO = os.environ.get("HORARIO_ALVO")

print(f"🚀 STARTING MATRIX SERVER SHORTS (EN) FOR: {HORARIO_ALVO}")

credenciais_dict = json.loads(GOOGLE_JSON)
creds_sheets = Credentials.from_service_account_info(credenciais_dict, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
gc = gspread.authorize(creds_sheets)

aba_shorts = gc.open_by_key("1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU").worksheet("EN_SHORTS")

creds_yt = YTCredentials.from_authorized_user_info(json.loads(YT_TOKEN_JSON))
if creds_yt and creds_yt.expired and creds_yt.refresh_token: creds_yt.refresh(Request())
youtube = build('youtube', 'v3', credentials=creds_yt)
drive_service = build_drive('drive', 'v3', credentials=creds_sheets)

PASTA_TEMP = "/tmp/fabrica_shorts_en"
os.makedirs(PASTA_TEMP, exist_ok=True)

# Maria Universal — vertical images (shared across EN/PL and future channels)
ID_PASTA_MARIA_VERT = "1QSUf1NYJbw8M_AOXiX50R_IZ8sPyXrHz"
ID_PASTA_MUSICAS = "1gxZA1TlQPzuf737XOo_n8blfOThnddgm"

def baixar_arquivo(file_id, destino):
    for tentativa in range(4):
        try:
            request = drive_service.files().get_media(fileId=file_id)
            with open(destino, 'wb') as f: f.write(request.execute())
            return destino
        except Exception as e:
            print(f"   ⚠️ Google Drive failed. Retrying... ({tentativa+1}/4)")
            time.sleep(5)
    raise Exception(f"Definitive failure downloading file {file_id}")

def listar_arquivos(folder_id, extensoes=None):
    res = []
    page_token = None
    while True:
        for tentativa in range(4):
            try:
                response = drive_service.files().list(q=f"'{folder_id}' in parents and trashed=false", spaces='drive', fields='nextPageToken, files(id, name)', pageToken=page_token).execute()
                break
            except Exception as e:
                print(f"   ⚠️ Error reading folder {folder_id}. Retrying... ({tentativa+1}/4)")
                time.sleep(5)
        else:
            print(f"   ❌ Definitive failure reading folder {folder_id}.")
            return res

        for f in response.get('files', []):
            if extensoes:
                if f['name'].lower().endswith(extensoes): res.append(f)
            else: res.append(f)
        page_token = response.get('nextPageToken', None)
        if not page_token: break
    return res

def obter_duracao(arquivo):
    try: return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', arquivo], capture_output=True, text=True).stdout.strip())
    except: return 60

def formatar_vtt(caminho_vtt):
    if not os.path.exists(caminho_vtt): return
    with open(caminho_vtt, 'r', encoding='utf-8') as f: linhas = f.readlines()
    with open(caminho_vtt, 'w', encoding='utf-8') as f:
        for l in linhas:
            if '-->' in l:
                f.write(l.strip() + ' line:75% align:center\n')
            elif l.strip() == '' or l.startswith('WEBVTT'):
                f.write(l)
            else:
                f.write(textwrap.fill(l.strip(), width=30) + '\n')

dados = aba_shorts.get_all_records()
col_status = aba_shorts.row_values(1).index('Status') + 1

for index, linha in enumerate(dados, start=2):
    if str(linha.get('Status', '')).strip() == 'Ready for Audio' and str(linha.get('Horario', '')).strip() == HORARIO_ALVO:
        data_str = str(linha.get('Data', ''))
        horario_str = str(linha.get('Horario', ''))
        titulo = str(linha.get('Titulo', ''))
        descricao_ia = str(linha.get('Descricao', ''))
        tags_str = str(linha.get('Tags', ''))
        persona = str(linha.get('Personagem', '')).upper()
        roteiro = str(linha.get('Roteiro', ''))

        print(f"🎬 STARTING SHORT: Row {index} - {persona} at {horario_str}")

        # EN channel: only Maria (Maria Universal)
        voz_escolhida = "en-US-JennyNeural"

        print("   📥 Downloading vertical images (Maria Universal)...")
        arquivos_img = listar_arquivos(ID_PASTA_MARIA_VERT, ('.jpg', '.jpeg', '.png'))
        if not arquivos_img: continue

        random.shuffle(arquivos_img)
        imgs_locais = [baixar_arquivo(arquivos_img[i]['id'], f"{PASTA_TEMP}/img_{i}.jpg") for i in range(min(6, len(arquivos_img)))]

        arquivos_musica = listar_arquivos(ID_PASTA_MUSICAS, ('.mp3', '.wav'))
        musica_local = baixar_arquivo(random.choice(arquivos_musica)['id'], f"{PASTA_TEMP}/musica.mp3")

        caminho_mp3 = f"{PASTA_TEMP}/audio.mp3"
        caminho_vtt = f"{PASTA_TEMP}/legenda.vtt"
        caminho_txt = f"{PASTA_TEMP}/roteiro.txt"
        with open(caminho_txt, "w", encoding="utf-8") as f:
            f.write(roteiro.replace('*', '').replace('_', '').replace('"', ''))

        print(f"   🎙️ Generating Neural Voice and Captions ({voz_escolhida})...")
        subprocess.run(["edge-tts", "--voice", voz_escolhida, "--rate=-20%", "--pitch=-10Hz", "--file", caminho_txt, "--write-media", caminho_mp3, "--write-subtitles", caminho_vtt], capture_output=True)
        formatar_vtt(caminho_vtt)

        print("   ✂️ Trimming final silence for the Loop...")
        caminho_mp3_trimmed = f"{PASTA_TEMP}/audio_trimmed.mp3"
        subprocess.run(f'ffmpeg -y -i "{caminho_mp3}" -af "areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB,areverse" "{caminho_mp3_trimmed}"', shell=True, capture_output=True)

        duracao_audio = obter_duracao(caminho_mp3_trimmed)

        print("   🎞️ Assembling vertical visual blocks (1080x1920)...")
        tempo_acumulado = 0
        lista_ts = []
        contador_chunk = 0

        while tempo_acumulado < duracao_audio:
            arquivo_ts = f"{PASTA_TEMP}/chunk_{contador_chunk}.ts"
            duracao_padrao = random.randint(6, 9)
            ativo = random.choice(imgs_locais)

            efeito_zoom = random.choice(['in', 'out'])
            zoom_cmd = "zoompan=z='1.0+0.0008*on':d=400:x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':s=1080x1920:fps=24" if efeito_zoom == 'in' else "zoompan=z='1.15-0.0008*on':d=400:x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':s=1080x1920:fps=24"

            subprocess.run(f'ffmpeg -y -loop 1 -framerate 24 -i "{ativo}" -t {duracao_padrao} -vf "scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,{zoom_cmd}" -c:v libx264 -preset ultrafast -pix_fmt yuv420p -an "{arquivo_ts}"', shell=True, capture_output=True)

            tempo_acumulado += duracao_padrao
            lista_ts.append(arquivo_ts)
            contador_chunk += 1

        print("   🔥 Mixing audio and finalizing the Short...")
        arquivo_concat = f"{PASTA_TEMP}/concat.txt"
        with open(arquivo_concat, "w") as f:
            for ts in lista_ts: f.write(f"file '{ts}'\n")
        video_mudo = f"{PASTA_TEMP}/mudo.mp4"
        subprocess.run(f'ffmpeg -y -f concat -safe 0 -i "{arquivo_concat}" -c copy "{video_mudo}"', shell=True, capture_output=True)

        video_final = f"{PASTA_TEMP}/final_short.mp4"
        subprocess.run(f'ffmpeg -y -i "{video_mudo}" -i "{caminho_mp3_trimmed}" -stream_loop -1 -i "{musica_local}" -filter_complex "[1:a]apad[v_pad];[2:a]volume=0.15[bgm];[v_pad][bgm]amix=inputs=2:duration=longest[aout]" -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k -t {duracao_audio} "{video_final}"', shell=True, capture_output=True)

        tags_limpas = re.sub(r'[^a-zA-Z0-9 ,]', '', tags_str)
        tags_lista = [t.strip()[:30] for t in tags_limpas.split(',') if t.strip()][:15]

        texto_convite = "\n\n🙏 For the full, deep prayer, visit our channel. We publish powerful prayers every day.\n\nOur Playlists:\nMorning Prayers: https://www.youtube.com/playlist?list=PLcBcFg8r0RDmY0zEywQRGDDVEprFvK-QI\nEvening Prayers: https://www.youtube.com/playlist?list=PLcBcFg8r0RDkgQba8FVPPgHW0NgHEOzSm"

        try:
            agora_ny = datetime.datetime.now(pytz.timezone('America/New_York'))
            data_hora_alvo = pytz.timezone('America/New_York').localize(datetime.datetime.strptime(f"{data_str} {horario_str}", "%Y-%m-%d %H:%M"))
            publish_at = data_hora_alvo.isoformat() if data_hora_alvo > agora_ny else None
        except: publish_at = None

        body = {
            "snippet": {
                "title": titulo[:100],
                "description": f"{descricao_ia}{texto_convite}",
                "tags": tags_lista,
                "categoryId": "22",
                "defaultLanguage": "en-US",
                "defaultAudioLanguage": "en-US"
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
                "selfDeclaredMadeWithAlteredContent": True
            }
        }
        if publish_at: body["status"]["publishAt"] = publish_at

        for tentativa in range(3):
            try:
                video_id = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(video_final, chunksize=-1, resumable=True, mimetype="video/mp4")).execute().get("id")
                print(f"   🎉 SUCCESS! Short {video_id} published.")

                try:
                    if os.path.exists(caminho_vtt):
                        youtube.captions().insert(part="snippet", body={"snippet": {"videoId": video_id, "language": "en-US", "name": "English", "isDraft": False}}, media_body=MediaFileUpload(caminho_vtt)).execute()
                except Exception as e: print(f"   ⚠️ Warning: Could not upload captions: {e}")

                try:
                    pid = "PLcBcFg8r0RDmlfPtguqIyIAz4HG1rk1PQ"  # Shorts EN playlist
                    youtube.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
                except Exception as e: print(f"   ⚠️ Warning: Could not add to playlist: {e}")

                aba_shorts.update_cell(index, col_status, 'Published')
                break
            except Exception as e:
                print(f"   ❌ YouTube error (Attempt {tentativa+1}/3): {e}")
                time.sleep(15)
        break

print("\n🚀 MATRIX SERVER SHORTS SHUTTING DOWN.")
