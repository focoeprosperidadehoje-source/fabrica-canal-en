import os, sys, json, time, re, datetime
from google.genai import Client
from google.oauth2.service_account import Credentials
import gspread

CHAVE_API = os.environ.get("GEMINI_API_KEY")
GOOGLE_JSON = os.environ.get("GOOGLE_CREDENTIALS_EN")

print("🔐 Authenticating with Google Sheets (SHORTS EN)...")
credenciais_dict = json.loads(GOOGLE_JSON)
escopos = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
credenciais = Credentials.from_service_account_info(credenciais_dict, scopes=escopos)
gc = gspread.authorize(credenciais)

client = Client(api_key=CHAVE_API, http_options={'api_version': 'v1'})

def obter_modelo_lite():
    try:
        modelos = client.models.list()
        lite_models = [m.name for m in modelos if 'generateContent' in m.supported_generation_methods and 'flash-lite' in m.name]
        return sorted(lite_models, reverse=True)[0] if lite_models else 'gemini-2.5-flash'
    except:
        return 'gemini-2.5-flash'

modelo_usina = obter_modelo_lite()

ID_PLANILHA = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"
PILARES = {
    0: "Spiritual Warfare and Protection", 1: "Freedom from Addictions and Bondage",
    2: "Family and Marriage Restoration", 3: "Providence and Open Doors",
    4: "Mercy and Physical Healing", 5: "The Mantle of Mary", 6: "Miracles and Gratitude"
}
GRADE_SHORTS = [
    {"horario": "14:00", "personagem": "Maria", "idioma": "EN", "foco": "Afternoon: Intercession, healing and miracles.", "ref": "18:00"}
]

aba_shorts = gc.open_by_key(ID_PLANILHA).worksheet("EN_SHORTS")
aba_longos = gc.open_by_key(ID_PLANILHA).worksheet("EN")

todas_linhas = aba_shorts.get_all_values()
if len(todas_linhas) > 500:
    aba_shorts.delete_rows(2, 100)
    todas_linhas = aba_shorts.get_all_values()

proxima_linha_vazia = len(todas_linhas) + 1
valores_coluna_a = [linha[0].strip() for linha in todas_linhas[1:] if len(linha) > 0]
valores_coluna_b = [linha[1].strip() for linha in todas_linhas[1:] if len(linha) > 1]

dias_existentes = {}
hoje = datetime.date.today()
limite_passado = hoje - datetime.timedelta(days=2)

for d_str, h_str in zip(valores_coluna_a, valores_coluna_b):
    if d_str and h_str:
        try:
            d_obj = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
            if d_obj >= limite_passado:
                if d_obj not in dias_existentes: dias_existentes[d_obj] = []
                dias_existentes[d_obj].append(h_str)
        except: pass

meta_estoque = hoje + datetime.timedelta(days=5)
data_alvo = None
grade_para_processar = []

data_check = limite_passado
while data_check <= meta_estoque:
    horarios_presentes = dias_existentes.get(data_check, [])
    if len(horarios_presentes) < 1:
        data_alvo = data_check
        grade_para_processar = [v for v in GRADE_SHORTS if v["horario"] not in horarios_presentes]
        break
    data_check += datetime.timedelta(days=1)

if not data_alvo:
    print(f"✅ SHORTS STOCK REACHED through {meta_estoque}. Sleeping.")
    sys.exit(0)

pilar_do_dia = PILARES[data_alvo.weekday()]
print(f"\n📅 TARGET DATE SHORTS: {data_alvo} | Pillar: {pilar_do_dia}")

dados_longos = aba_longos.get_all_values()

for video in grade_para_processar:
    horario, persona, idioma, foco_teologico = video["horario"], video["personagem"].upper(), video["idioma"], video["foco"]
    print(f"🎬 PRODUCING SHORT: {horario} | {persona}")

    horario_longo_ref = video["ref"]
    titulo_referencia = ""
    for linha in dados_longos[1:]:
        if len(linha) > 6 and linha[0].strip() == str(data_alvo) and linha[1].strip() == horario_longo_ref:
            titulo_referencia = linha[6].strip()
            break

    contexto_eco = f"The corresponding long video for today has the title: '{titulo_referencia}'. The Short MUST be an echo of this theme." if titulo_referencia else ""

    persona_prompt = "the Blessed Virgin Mary"

    # Hail Mary — pause comes AFTER Jesus, never before
    oracao_padrao = "Hail Mary, full of grace... the Lord is with thee... Blessed art thou among women... and blessed is the fruit of thy womb Jesus... Holy Mary, Mother of God... pray for us sinners... now and at the hour of our death... Amen."

    prompt_principal = f"""
    Act as a Catholic spiritual guide. Create a script for a YouTube SHORT video (maximum 35 seconds of speech).
    Theme of the day: {pilar_do_dia}. Focus: {foco_teologico}. Directed to: {persona_prompt}.
    {contexto_eco}

    MANDATORY SCRIPT STRUCTURE (PERFECT LOOP):
    1. HOOK (Beginning): The first sentence of the video. MANDATORY to start with lowercase ellipsis ("..."). It is the SYNTACTIC COMPLEMENT of the final sentence — together they form a single continuous and complete sentence.
    2. PRAYER: Write EXACTLY this prayer: "{oracao_padrao}"
    3. LOOP SENTENCE (End): The last sentence of the video. MANDATORY to end with ellipsis ("..."). It must be SYNTACTICALLY INCOMPLETE — an open clause whose natural complement is exactly the opening sentence. The listener does not perceive the cut because the brain joins end and beginning as a single continuous sentence.

    EXAMPLE OF PERFECT SYNTACTIC LOOP:
    End (incomplete): "...that is why today you need to receive..."
    Beginning (complement): "...the grace that Mary kept especially for you."
    Read in sequence they form: "that is why today you need to receive the grace that Mary kept especially for you."

    FLUENCY RULES:
    - Write fluid, natural sentences. Use ellipses (...) for breathing pauses.
    - The title must start with "Quick Prayer: " followed by the theme, and end with the hashtag #Shorts.
    - NO time markers, NO asterisks, NO emojis in the script.

    EXACT FORMAT:
    TITLE: [Quick Prayer: Theme - #Shorts]
    SCRIPT: [Complete script with the loop effect]
    DESC: [Short description inviting viewers to visit the channel and playlists]
    TAGS: [Tags separated by commas]
    """

    texto_ia = None
    for _ in range(3):
        try:
            texto_ia = client.models.generate_content(model=modelo_usina, contents=prompt_principal).text
            break
        except Exception as gemini_err: print(f"   ⚠️ Gemini error (attempt {i+1}/5): {gemini_err}"); time.sleep(10)

    if not texto_ia: continue

    try:
        t_match = re.search(r'TITLE:\s*(.*?)(?=SCRIPT:|DESC:|TAGS:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        g_match = re.search(r'SCRIPT:\s*(.*?)(?=DESC:|TAGS:|TITLE:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        d_match = re.search(r'DESC:\s*(.*?)(?=TAGS:|TITLE:|SCRIPT:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        tg_match = re.search(r'TAGS:\s*(.*?)(?=TITLE:|SCRIPT:|DESC:|$)', texto_ia, re.IGNORECASE | re.DOTALL)

        titulo_final = re.sub(r'[*"\[\]]', '', t_match.group(1)).strip() if t_match else "Quick Prayer #Shorts"
        roteiro_final = g_match.group(1).strip() if g_match else texto_ia
        desc_final = d_match.group(1).strip() if d_match else "Watch the full prayer on our channel!"
        tags_final = re.sub(r'[*\[\]]', '', tg_match.group(1)).strip() if tg_match else "shorts, prayer, faith"

        nova_linha = [str(data_alvo), horario, "Ready for Audio", persona, idioma, pilar_do_dia, titulo_final, roteiro_final, tags_final, desc_final, "N/A", "N/A"]
        aba_shorts.update(values=[nova_linha], range_name=f"A{proxima_linha_vazia}:L{proxima_linha_vazia}")
        print(f"   ✅ SUCCESS! Short row {proxima_linha_vazia} filled.")
        proxima_linha_vazia += 1
        time.sleep(3)
    except Exception as e: print(f"   ❌ Failed to save: {e}")

