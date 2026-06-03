import os, sys, json, time, re, datetime
from google.genai import Client
from google.oauth2.service_account import Credentials
import gspread

CHAVE_API = os.environ.get("GEMINI_API_KEY")
GOOGLE_JSON = os.environ.get("GOOGLE_CREDENTIALS_EN")

print("🔐 Authenticating with Google Sheets via Service Account...")
credenciais_dict = json.loads(GOOGLE_JSON)
escopos = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
credenciais = Credentials.from_service_account_info(credenciais_dict, scopes=escopos)
gc = gspread.authorize(credenciais)

client = Client(api_key=CHAVE_API, http_options={'api_version': 'v1'})

def obter_cascata_de_modelos():
    try:
        modelos_disponiveis = client.models.list()
        flash_models = [m.name for m in modelos_disponiveis if 'generateContent' in m.supported_generation_methods and 'flash' in m.name and '8b' not in m.name]
        pro_models = [m.name for m in modelos_disponiveis if 'generateContent' in m.supported_generation_methods and 'pro' in m.name and 'vision' not in m.name]
        melhor_flash = sorted(flash_models, reverse=True)[0] if flash_models else 'gemini-2.5-flash'
        melhor_pro = sorted(pro_models, reverse=True)[0] if pro_models else 'gemini-2.5-pro'
        return [melhor_flash, melhor_flash, melhor_flash, melhor_pro, melhor_pro]
    except:
        return ['gemini-2.5-flash', 'gemini-2.5-flash', 'gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.5-pro']

modelos_cascata = obter_cascata_de_modelos()

def calcular_contexto_sazonal(data_alvo):
    ano = data_alvo.year
    a = ano % 19; b = ano // 100; c = ano % 100; d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451; mes = (h + l - 7 * m + 114) // 31; dia = ((h + l - 7 * m + 114) % 31) + 1
    easter = datetime.date(ano, mes, dia)

    ash_wednesday = easter - datetime.timedelta(days=46)
    good_friday = easter - datetime.timedelta(days=2)
    pentecost = easter + datetime.timedelta(days=49)
    corpus_christi = easter + datetime.timedelta(days=60)

    may_1 = datetime.date(ano, 5, 1)
    mothers_day = may_1 + datetime.timedelta(days=(6 - may_1.weekday() + 7) % 7 + 7)

    jun_1 = datetime.date(ano, 6, 1)
    fathers_day = jun_1 + datetime.timedelta(days=(6 - jun_1.weekday() + 7) % 7 + 14)

    nov_1 = datetime.date(ano, 11, 1)
    thanksgiving = nov_1 + datetime.timedelta(days=(3 - nov_1.weekday() + 7) % 7 + 21)

    if data_alvo == easter: return "TODAY IS EASTER SUNDAY."
    if data_alvo == ash_wednesday: return "TODAY IS ASH WEDNESDAY."
    if data_alvo == good_friday: return "TODAY IS GOOD FRIDAY."
    if data_alvo == pentecost: return "TODAY IS PENTECOST SUNDAY."
    if data_alvo == corpus_christi: return "TODAY IS THE FEAST OF CORPUS CHRISTI."
    if data_alvo == mothers_day: return "TODAY IS MOTHER'S DAY."
    if data_alvo == fathers_day: return "TODAY IS FATHER'S DAY."
    if data_alvo == thanksgiving: return "TODAY IS THANKSGIVING DAY."
    if data_alvo.month == 8 and data_alvo.day == 15: return "TODAY IS THE FEAST OF THE ASSUMPTION OF MARY."
    if data_alvo.month == 11 and data_alvo.day == 1: return "TODAY IS ALL SAINTS' DAY."
    if data_alvo.month == 11 and data_alvo.day == 2: return "TODAY IS ALL SOULS' DAY."
    if data_alvo.month == 12 and data_alvo.day == 8: return "TODAY IS THE FEAST OF THE IMMACULATE CONCEPTION."
    if data_alvo.month == 12 and data_alvo.day == 25: return "TODAY IS CHRISTMAS DAY."
    if data_alvo.month == 12 and data_alvo.day == 31: return "TODAY IS NEW YEAR'S EVE."
    if data_alvo.month == 1 and data_alvo.day == 1: return "TODAY IS NEW YEAR'S DAY."
    return ""

ID_PLANILHA = "1KgIjWrLUVlllhlZB1R9fkHGxxZlLsax1aOVGZrYwgnU"
PILARES = {
    0: "Spiritual Warfare and Protection", 1: "Freedom from Addictions and Bondage",
    2: "Family and Marriage Restoration", 3: "Providence and Open Doors",
    4: "Mercy and Physical Healing", 5: "The Mantle of Mary", 6: "Miracles and Gratitude"
}
GRADE_DIARIA = [
    {"horario": "06:00", "personagem": "Jesus", "idioma": "EN", "foco": "Morning: Consecration, divine wisdom and guidance for the day.", "periodo": "this morning"},
    {"horario": "18:00", "personagem": "Maria", "idioma": "EN", "foco": "HYBRID: Address the pain of the Pillar of the Day and, at the end, transition into the evening prayer, asking for deep sleep, relief from anxiety and night protection.", "periodo": "tonight"}
]

aba = gc.open_by_key(ID_PLANILHA).worksheet("EN")

todas_linhas = aba.get_all_values()
if len(todas_linhas) > 500:
    aba.delete_rows(2, 100)
    todas_linhas = aba.get_all_values()

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
    if len(horarios_presentes) < 2:
        data_alvo = data_check
        grade_para_processar = [v for v in GRADE_DIARIA if v["horario"] not in horarios_presentes]
        break
    data_check += datetime.timedelta(days=1)

if not data_alvo:
    print(f"✅ STOCK REACHED through {meta_estoque}. Sleeping.")
    sys.exit(0)

pilar_do_dia = PILARES[data_alvo.weekday()]
contexto_sazonal = calcular_contexto_sazonal(data_alvo)
print(f"\n📅 TARGET DATE: {data_alvo} | Pillar: {pilar_do_dia}")

esperas_exponenciais = [10, 20, 40, 80, 120]

for video in grade_para_processar:
    horario, persona, idioma, foco_teologico, periodo = video["horario"], video["personagem"].upper(), video["idioma"], video["foco"], video["periodo"]
    print(f"🎬 PRODUCING: {horario} | {persona}")

    if data_alvo.weekday() == 4:
        foco_teologico += " MANDATORY: Deepen the theme of Mercy and Forgiveness." if horario == "06:00" else " MANDATORY: Connect the theme with the Passion of Christ and the Sacrament of Reconciliation."

    persona_prompt = "Jesus Christ" if persona == 'JESUS' else "the Blessed Virgin Mary"

    prompt_tema = f"Act as a Theologian. Create a short theme (max 8 words) for a prayer. Pillar: '{pilar_do_dia}', directed to '{persona_prompt}', moment: '{foco_teologico}'. Seasonality: '{contexto_sazonal}'. ONLY the theme, no quotes or asterisks."
    tema_gerado = None
    for i in range(5):
        try:
            tema_gerado = client.models.generate_content(model=modelos_cascata[i], contents=prompt_tema).text.replace('*', '').replace('"', '').replace('[', '').replace(']', '').strip()
            break
        except Exception as gemini_err: print(f"   ⚠️ Gemini error (attempt {i+1}/5): {gemini_err}"); time.sleep(esperas_exponenciais[i])

    if not tema_gerado: continue
    time.sleep(5)

    regra_meditacao = "MANDATORY: In the description (DESC), add a highlighted notice saying that at the end of the video there are 5 minutes of celestial music for sleeping/meditating." if horario == "18:00" else ""
    cta_comentarios = "At the end, ask the listener to write a reason for gratitude in the comments." if horario == "18:00" else "At the beginning, naturally ask: 'If you believe, type Amen in the comments right now'."
    regra_persona = "MANDATORY: As you are addressing Jesus Christ, it is STRICTLY FORBIDDEN to mention Mary or the Virgin." if persona == 'JESUS' else "MANDATORY: As you are addressing Mary, you MUST use the invocations 'Blessed Virgin Mary', 'Mother Mary' or 'Our Lady'."

    prompt_principal = f"""
    Act as an empathetic spiritual guide and brother in faith. Write an extensive prayer of 1500 to 1800 words about "{tema_gerado}" directed to {persona_prompt}.
    CONTEXT: Period of the day: "{periodo}". Focus: "{foco_teologico}". Seasonality: "{contexto_sazonal}".

    RETENTION AND COPYWRITING RULES (VERY IMPORTANT):
    1. TITLE FORMULA: The title MUST follow the formula: [Believer's Pain] + [Solution/Miracle]. It is STRICTLY FORBIDDEN to start the title with the word "Prayer".
    2. THUMB FORMULA: Maximum 4 words. MUST be an urgency trigger connected to the theme (Ex: "URGENT MIRACLE TODAY", "SAVE YOUR FAMILY", "END ANXIETY NOW").
    3. THE 15-SECOND RULE (HOOK 3A): The beginning of the script MUST have 3 quick blocks:
       - Attention (0-5s): An EMPATHETIC AFFIRMATION about the believer's pain. (FORBIDDEN to use direct questions).
       - Sensory Setting (5-10s): Connect the pain with the scene of {periodo}.
       - Authority/Agenda (10-15s): Say that {persona_prompt} has a word of liberation and ask them to stay until the end.
    4. IMMEDIATE CTA: {cta_comentarios}
    5. ATTENTION RESET (MID-VIDEO): Exactly at the midpoint of the script, insert a spoken phrase to reconnect the listener.
    6. INVISIBLE RETENTION HOOKS: Every 300 to 400 words, organically incorporate — without the believer noticing the technique — one of the following: (a) ANTICIPATION: announce that something important will be revealed soon, without revealing it yet; (b) PARTIAL REVELATION: deliver part of the spiritual answer and signal there is more; (c) EMOTIONAL VALIDATION: name exactly what the believer is feeling at that moment, creating deep recognition; (d) BLOCK SHIFT: make an unexpected tone transition — from supplication to gratitude, from pain to hope — that renews attention. The hooks must be invisible: the believer does not perceive the technique, only feels they cannot stop listening. Never break the devotional atmosphere.

    GENERAL RULES:
    7. FORBIDDEN TO MENTION EXACT TIMES: Never say "06:00" or "18:00". Use only "{periodo}".
    8. PAUSES: MANDATORY to use abundant ellipses (...) to force pauses in the AI voice.
    9. ANTI-JSON: Write in PLAIN TEXT. FORBIDDEN JSON, curly braces {{ }} or asterisks (*).
    {regra_persona}
    {regra_meditacao}

    EXACT FORMAT:
    TITLE: [Pain + Solution]
    THUMB: [Urgency Trigger — Max 4 words]
    SCRIPT: [Complete prayer of 1500 to 1800 words]
    DESC: [Description of 3 paragraphs with strong SEO]
    TAGS: [Tags separated by commas]
    """

    texto_ia = None
    for i in range(5):
        try:
            texto_ia = client.models.generate_content(model=modelos_cascata[i], contents=prompt_principal).text
            break
        except Exception as gemini_err: print(f"   ⚠️ Gemini error (attempt {i+1}/5): {gemini_err}"); time.sleep(esperas_exponenciais[i])

    if not texto_ia: continue

    try:
        t_match = re.search(r'TITLE:\s*(.*?)(?=THUMB:|SCRIPT:|DESC:|TAGS:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        th_match = re.search(r'THUMB:\s*(.*?)(?=SCRIPT:|DESC:|TAGS:|TITLE:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        g_match = re.search(r'SCRIPT:\s*(.*?)(?=DESC:|TAGS:|TITLE:|THUMB:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        d_match = re.search(r'DESC:\s*(.*?)(?=TAGS:|TITLE:|THUMB:|SCRIPT:|$)', texto_ia, re.IGNORECASE | re.DOTALL)
        tg_match = re.search(r'TAGS:\s*(.*?)(?=TITLE:|THUMB:|SCRIPT:|DESC:|$)', texto_ia, re.IGNORECASE | re.DOTALL)

        titulo_final = re.sub(r'[*"\[\]]', '', t_match.group(1)).strip() if t_match else "Powerful Prayer"
        thumb_final = re.sub(r'[*"\[\]]', '', th_match.group(1)).strip() if th_match else "MIRACLE TODAY"
        roteiro_final = g_match.group(1).strip() if g_match else texto_ia
        desc_final = d_match.group(1).strip() if d_match else "Daily prayer."
        tags_final = re.sub(r'[*\[\]]', '', tg_match.group(1)).strip() if tg_match else "prayer, faith, protection"

        nova_linha = [str(data_alvo), horario, "Ready for Audio", persona, idioma, tema_gerado, titulo_final, roteiro_final, tags_final, desc_final, "Pending", thumb_final]
        aba.update(values=[nova_linha], range_name=f"A{proxima_linha_vazia}:L{proxima_linha_vazia}")
        print(f"   ✅ SUCCESS! Row {proxima_linha_vazia} filled.")
        proxima_linha_vazia += 1
        time.sleep(5)
    except Exception as e: print(f"   ❌ Failed to save: {e}")

