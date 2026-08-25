#!/usr/bin/env python3
"""
gerar_bloco_live_en.py — GitHub Actions: generates multiple blocks per run (Canal EN)

Run 6x/day by gerador_blocos_en.yml. Each run:
  1. Fetches up to 100 channel EN comments (1 YouTube API call)
  2. Gemini classifies into 4-5 thematic groups (1 call)
  3. For each group: generates script with real names + prayer (1 lite call)
  4. Edge TTS synthesizes audio → audio_YYYYMMDD_HHMM_NN.mp3
  5. Assembler on VPS builds H blocks with videos_base/

Persona: Blessed Virgin Mary — Our Lady of Guadalupe (en-US-JennyNeural)
"""

import os
import sys
import json
import random
import asyncio
import re
from datetime import datetime
from pathlib import Path

import pytz
import edge_tts
from google import genai
from google.genai import types as genai_types
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

FUSO       = pytz.timezone("America/New_York")
VOZ        = "en-US-JennyNeural"
VOZ_RATE   = "-30%"
VOZ_PITCH  = "-8Hz"
CANAL_ID   = "UCOGQwey2JXGvL8cqZ9tmCoQ"
DIR_BLOCOS = Path("blocos_en")
MAX_GRUPOS = 5

MODELOS_LITE = ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
MODELOS_FULL = ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]

CHAVES = [k for k in [
    os.environ.get("GEMINI_KEY_LIVE_CONTENT_1_EN", ""),
    os.environ.get("GEMINI_KEY_LIVE_CONTENT_2_EN", ""),
] if k]

PILARES = {
    0: "Spiritual Warfare and Divine Protection",
    1: "Liberation from Addictions and Bondage",
    2: "Family Restoration and Reconciliation",
    3: "Divine Providence and Open Doors",
    4: "Divine Mercy and Physical Healing",
    5: "The Blessed Virgin's Mantle",
    6: "Miracles and Gratitude",
}

GRUPOS_HARDCODED = [
    {"tema": "healing",      "label": "Healing and Health",           "nomes": [], "suplica_comum": "for illness, pain, and recovery of sick brothers and sisters",           "num_fieis": 0},
    {"tema": "liberation",   "label": "Liberation from Addictions",   "nomes": [], "suplica_comum": "for liberation from alcohol, drugs, and bonds of sin",                   "num_fieis": 0},
    {"tema": "family",       "label": "Family Restoration",           "nomes": [], "suplica_comum": "for marriages in crisis, prodigal children, and peace in homes",         "num_fieis": 0},
    {"tema": "provision",    "label": "Provision and Work",           "nomes": [], "suplica_comum": "for financial provision, employment, and freedom from debt",             "num_fieis": 0},
    {"tema": "protection",   "label": "Spiritual Protection",         "nomes": [], "suplica_comum": "for protection against evil, envy, and all danger",                      "num_fieis": 0},
]


# ═══════════════════════════════════════════════════════════════════════
# GEMINI
# ═══════════════════════════════════════════════════════════════════════

def _chamar_gemini(prompt: str, modelos: list, max_tokens: int = 2048) -> str:
    for chave in CHAVES:
        for modelo in modelos:
            try:
                client = genai.Client(api_key=chave)
                resp = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(max_output_tokens=max_tokens),
                )
                return resp.text.strip()
            except Exception as e:
                print(f"  [WARN] {modelo} [{chave[-6:]}]: {str(e)[:80]}")
    raise RuntimeError("All Gemini models failed.")


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
    p = _easter(ano)
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
# YOUTUBE API
# ═══════════════════════════════════════════════════════════════════════

def get_youtube_readonly():
    raw = os.environ.get("YOUTUBE_TOKEN_EN", "")
    if not raw:
        return None
    try:
        data  = json.loads(raw)
        creds = OAuthCredentials.from_authorized_user_info(
            data, scopes=["https://www.googleapis.com/auth/youtube.readonly"]
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"  [WARN] YouTube readonly EN: {e}")
        return None

def buscar_comentarios_canal(yt) -> list[str]:
    if not yt:
        return []
    try:
        resp = yt.commentThreads().list(
            part="snippet",
            allThreadsRelatedToChannelId=CANAL_ID,
            maxResults=100,
            order="relevance",
        ).execute()
        textos = []
        for item in resp.get("items", []):
            s = item["snippet"]["topLevelComment"]["snippet"]
            texto = s.get("textOriginal", "").strip()
            if texto and len(texto) > 10:
                textos.append(texto[:200])
        print(f"  EN comments obtained: {len(textos)}")
        return textos
    except Exception as e:
        print(f"  [WARN] buscar_comentarios EN: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════
# GROUP CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

def _limpar_json(texto: str) -> str:
    texto = re.sub(r'```(?:json)?', '', texto)
    texto = re.sub(r'```', '', texto)
    inicio = texto.find('[')
    fim    = texto.rfind(']')
    if inicio != -1 and fim != -1:
        return texto[inicio:fim+1]
    return texto.strip()

def classificar_grupos(comentarios: list[str], pilar_hoje: str) -> list[dict]:
    if len(comentarios) >= 5:
        lista_str = "\n".join(f"- {c}" for c in comentarios[:80])
        prompt = f"""Analyze these comments from Catholic faithful on a prayer channel.
Extract the first name (if present) and classify the supplication of each comment.
Group into a maximum of 5 themes (e.g.: healing, liberation, family, finances, protection).

Return ONLY valid JSON without markdown or additional text:
[{{"tema":"slug","label":"Group name","nomes":["name1","name2"],"suplica_comum":"common petition in max 15 words","num_fieis":N}}]

RULES:
- Only proper names that appear in comments; do not invent
- suplica_comum: maximum 15 words describing the common petition
- Minimum 3 groups, maximum 5

COMMENTS:
{lista_str}"""
        try:
            raw = _chamar_gemini(prompt, MODELOS_LITE, max_tokens=1024)
            grupos = json.loads(_limpar_json(raw))
            if isinstance(grupos, list) and len(grupos) >= 2:
                print(f"  EN groups classified: {len(grupos)}")
                for g in grupos:
                    n = len(g.get("nomes", []))
                    print(f"    [{g.get('tema','')}] {g.get('num_fieis',0)} faithful, {n} names")
                return grupos[:MAX_GRUPOS]
            print("  [WARN] Invalid JSON or too few groups — using fallback")
        except Exception as e:
            print(f"  [WARN] classify_groups EN: {e}")

    print("  [Fallback 1] Generating thematic groups via Gemini EN...")
    prompt_fb = f"""Create 4 groups of frequent prayer intentions among English-speaking Catholic faithful.
Today's spiritual pillar is: {pilar_hoje}
Return ONLY valid JSON:
[{{"tema":"slug","label":"Name","nomes":[],"suplica_comum":"petition in max 15 words","num_fieis":0}}]"""
    try:
        raw = _chamar_gemini(prompt_fb, MODELOS_LITE, max_tokens=512)
        grupos = json.loads(_limpar_json(raw))
        if isinstance(grupos, list) and len(grupos) >= 2:
            print(f"  EN groups fallback: {len(grupos)}")
            return grupos[:MAX_GRUPOS]
    except Exception as e:
        print(f"  [WARN] fallback groups EN: {e}")

    print("  [Fallback 2] Using hardcoded EN groups.")
    return GRUPOS_HARDCODED[:MAX_GRUPOS]


# ═══════════════════════════════════════════════════════════════════════
# SCRIPT GENERATION
# ═══════════════════════════════════════════════════════════════════════

def _formatar_nomes(nomes: list) -> str:
    nomes = [n for n in nomes if n and len(n) >= 2]
    if not nomes:
        return "each brother and sister praying with us right now"
    if len(nomes) == 1:
        return nomes[0]
    return ", ".join(nomes[:-1]) + f" and {nomes[-1]}"

def gerar_roteiro_grupo(grupo: dict, contexto: str, pilar: str,
                        agora: datetime, num_bloco: int,
                        so_full: bool = False) -> str:
    nomes_raw  = grupo.get("nomes", [])
    nomes_str  = _formatar_nomes(nomes_raw)
    suplica    = grupo.get("suplica_comum", "for the needs of our brothers and sisters")
    label      = grupo.get("label", "Prayer of Intercession")
    tem_nomes  = len([n for n in nomes_raw if n and len(n) >= 2]) > 0

    nota_nomes = (
        f"Mention each name with maternal tenderness: {nomes_str}"
        if tem_nomes else
        "There are no specific names — speak of 'each brother and sister praying right now'"
    )
    nota_miguel = (
        "When natural in the intercession, mention Archangel Saint Michael as the spiritual guardian fighting at our side."
        if "Spiritual Warfare" in pilar else ""
    )

    prompt = f"""You are the Blessed Virgin Mary, Our Lady of Guadalupe, speaking in first person, in English.
Block #{num_bloco} | Group: {label}
Liturgical context of the day: {contexto}
Today's spiritual pillar: {pilar}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE (20 minutes — between 2600 and 3000 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[OPENING — first 90 seconds — REQUIRED]
Open by citing the brothers and sisters who asked for intercession:
"{nota_nomes}"
Common supplication of this group: "{suplica}"
Close the opening with: "I have come to intercede for you in this moment..."

[MAIN BODY — ~16 minutes]
MANDATORY ALTERNATION — the block must oscillate between two modes:
  Mode A (NARRATION): Our Lady speaks, welcomes, reveals grace — warm and maternal voice
  Mode B (GUIDED PRAYER): Our Lady leads the listener to pray aloud with her
  Ex: "Repeat with me in faith: Lord, I believe... Lord, I trust..."
  Ex: "Place your hand over your heart and say: Heavenly Mother, I receive this grace now..."
  Each transition between modes must be smooth and natural — minimum 3 alternations per block.

- Weave the pillar "{pilar}" with the intercession theme "{label}"
- Complete Hail Mary GUIDED (listener prays along): "Repeat with me: Hail Mary, full of grace..."
- Intercession block for health (required, guided): "Place your hand over the place that hurts and say with me..."
- Organic retention hooks every ~300 words (the faithful doesn't notice the technique):
  • Anticipation: "What comes now in this prayer..."
  • Revelation: "This grace has a name..."
  • Validation: "If you feel something in your heart right now, it is a sign that..."
  • Turn: "But what your Heavenly Mother wants to tell you about this is..."
{nota_miguel}

[THREE SUBTLE CTAs — only at natural transitions, never during prayer]
CTA 1 (~minute 4): "If this broadcast is blessing you, subscribe to the channel to receive prayers every day — we are a faith family that prays without ceasing for you..."
CTA 2 (~minute 8): "If this prayer is touching your heart, share it with someone who needs it..."
CTA 3 (~minute 17): "Stay, what comes next is for you..."

[CLOSING — last 3 minutes]
- Final blessing as Heavenly Mother
- End in STRENGTH — the faithful leaves protected, never desperate
- REQUIRED SYNTACTIC LOOP: the last sentence is syntactically incomplete
  to unite with the first sentence of the next block without the listener noticing the cut

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NEVER markdown, asterisks, hyphens, numbering, or titles — plain flowing text only
- NEVER ellipsis (...) or em dash (—) — these cause unwanted pauses in narration
- NEVER start a sentence with the word "Prayer"
- NEVER "Write Amen in the comments"
- NEVER mention other channels or brands
- ABSOLUTE TIMELESSNESS: this prayer plays at ANY time of day or night.
  NEVER mention times, parts of the day (dawn, morning, noon, afternoon, evening, night),
  days of the week, or dates. If you need to place the moment, say only "in this moment" or "right now"
- Only text that Our Lady speaks aloud — no production instructions
- Between 2600 and 3000 words
"""

    modelos = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"] if so_full else MODELOS_FULL
    texto   = _chamar_gemini(prompt, modelos, max_tokens=8192)
    texto   = re.sub(r'\*+', '', texto)
    texto   = re.sub(r'#{1,6}\s+', '', texto)
    texto   = re.sub(r'^\s*[-•]\s+', '', texto, flags=re.MULTILINE)
    texto   = re.sub(r'\.{2,}', '', texto)
    texto   = re.sub(r'\s*[—–]\s*', ', ', texto)
    texto   = re.sub(r'(?<!\n)\n(?!\n)', ' ', texto)
    texto   = re.sub(r'\n{3,}', '\n\n', texto)
    texto   = re.sub(r'  +', ' ', texto)
    return texto.strip()


# ═══════════════════════════════════════════════════════════════════════
# QUALITY GATE
# ═══════════════════════════════════════════════════════════════════════

def motivo_degeneracao(texto: str) -> str | None:
    palavras = texto.split()
    n = len(palavras)
    if n < 1400:
        return f"too short ({n} words)"
    if n > 4500:
        return f"too long ({n} words — likely loop)"
    tri = {}
    for i in range(n - 2):
        t = (palavras[i].lower(), palavras[i + 1].lower(), palavras[i + 2].lower())
        tri[t] = tri.get(t, 0) + 1
    max_tri = max(tri.values()) if tri else 0
    if max_tri > 25:
        return f"trigram repeated {max_tri}x (loop)"
    if texto.count(",") / max(n, 1) > 0.14:
        return "comma density typical of name list"
    frases = {}
    for f in re.split(r"[.!?…]+", texto):
        f = f.strip().lower()
        if len(f.split()) > 5:
            frases[f] = frases.get(f, 0) + 1
    max_frase = max(frases.values()) if frases else 0
    if max_frase >= 4:
        return f"identical sentence repeated {max_frase}x"
    return None


# ═══════════════════════════════════════════════════════════════════════
# TTS
# ═══════════════════════════════════════════════════════════════════════

async def _tts_async(texto: str, saida: Path):
    comm = edge_tts.Communicate(texto, voice=VOZ, rate=VOZ_RATE, pitch=VOZ_PITCH)
    await comm.save(str(saida))

def gerar_audio(texto: str, saida: Path):
    asyncio.run(_tts_async(texto, saida))
    print(f"  TTS EN: {saida.name} ({saida.stat().st_size // 1024} KB)")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def _gh_error(msg: str):
    linha = msg.replace("\n", " | ").replace("\r", "")[:500]
    print(f"::error::{linha}", flush=True)


def main():
    print("=" * 60)
    print("gerar_bloco_live_en.py — Canal EN — Blessed Virgin Mary")
    print("=" * 60)

    DIR_BLOCOS.mkdir(parents=True, exist_ok=True)
    agora    = datetime.now(FUSO)
    contexto = calcular_contexto_sazonal(agora)
    pilar    = PILARES.get(agora.weekday(), "Prayer and Intercession")
    ts_base  = agora.strftime("%Y%m%d_%H%M")

    print(f"Local time: {agora.strftime('%Y-%m-%d %H:%M')} (New York)")
    print(f"Liturgical context: {contexto}")
    print(f"Pillar of the day: {pilar}")

    print("\n[1/3] Fetching EN channel comments...")
    yt = get_youtube_readonly()
    comentarios = buscar_comentarios_canal(yt)

    print("\n[2/3] Classifying into thematic groups...")
    grupos = classificar_grupos(comentarios, pilar)
    print(f"  Total blocks to generate: {len(grupos)}")

    print(f"\n[3/3] Generating EN blocks...")
    gerados = 0
    for i, grupo in enumerate(grupos):
        label = grupo.get("label", f"Group {i+1}")
        print(f"\n  ── Block {i+1}/{len(grupos)}: {label} ──")
        try:
            num_bloco = int(agora.strftime("%j")) * MAX_GRUPOS + i + 1
            roteiro   = gerar_roteiro_grupo(grupo, contexto, pilar, agora, num_bloco)
            palavras  = len(roteiro.split())
            print(f"  Script EN: {palavras} words")

            motivo = motivo_degeneracao(roteiro)
            if motivo:
                print(f"  [WARN] Script rejected ({motivo}) — retrying with full model...")
                roteiro  = gerar_roteiro_grupo(grupo, contexto, pilar, agora, num_bloco, so_full=True)
                palavras = len(roteiro.split())
                motivo   = motivo_degeneracao(roteiro)
                if motivo:
                    print(f"  [ERROR] Rejected again ({motivo}) — block discarded")
                    continue
                print(f"  Script EN (full): {palavras} words — approved")

            ts      = f"{ts_base}_{i+1:02d}"
            destino = DIR_BLOCOS / f"audio_{ts}.mp3"
            gerar_audio(roteiro, destino)
            gerados += 1
            print(f"  ✅ {destino.name}")

        except Exception as e:
            print(f"  [ERROR] Block {i+1} ({label}): {e}")
            continue

    print(f"\n{'='*60}")
    print(f"Done EN: {gerados}/{len(grupos)} blocks in {DIR_BLOCOS}/")
    print(f"VPS assembles .mp4 with videos_base/ automatically.")

    if gerados == 0:
        _gh_error("No EN blocks generated — all groups failed.")
        sys.exit(1)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as exc:
        _gh_error(f"FAILURE EN: {exc}")
        print(traceback.format_exc(), flush=True)
        sys.exit(1)
