# -*- coding: utf-8 -*-
"""novenas.py — Slot 06:00 (Novenas) — gerado a partir do padrão do PT (aprovado por Leandro em 2026-09-25). Somente personas marianas do canal."""
import datetime

CFG = {
 "canal": "EN", "tz": "America/New_York", "lang_name": "American English",
 "ativacao": datetime.date(2026, 9, 30), "epoca_pedidos": datetime.date(2026, 9, 30),
 "status_pronto": "Ready for Audio", "invocacao_padrao": "Blessed Virgin Mary",
 "promessa_regra": 'MUST start with "Our Lady". Ex: "Our Lady Heals Your Home", "Our Lady Opens New Doors".',
 "festas": [
   {"id": "immaculate", "inicio": (11, 29), "nome": "Novena to the Immaculate Conception", "invocacao": "Mary Immaculate",
    "festa": "Solemnity of the Immaculate Conception, Patroness of the United States (December 8)"},
   {"id": "christmas", "inicio": (12, 16), "nome": "Christmas Novena with Our Lady", "invocacao": "Blessed Virgin Mary",
    "festa": "Christmas (December 25) — Mary, the Mother awaiting the Child Jesus"},
 ],
 "intencoes_festa": ["healing of illness and the health of those you love", "the unity and restoration of your family",
   "reconciliation, forgiveness and peace", "freedom from addictions and every chain", "the protection and future of your children",
   "work, provision and open doors", "spiritual protection of your home against all evil",
   "impossible and desperate causes", "gratitude for graces received and consecration to Our Lady"],
 "categorias": {
   "saude": ("Novena for Healing and Health", "illness, physical health, treatments and surgeries"),
   "familia": ("Novena for Family Restoration", "conflict, distance and restoration of family and marriage"),
   "emprego": ("Novena for a New Job", "unemployment, work, provision and open doors"),
   "dividas": ("Novena for Financial Breakthrough", "debt, financial hardship and divine providence"),
   "filhos": ("Novena for Your Children", "protection, direction and conversion of children"),
   "vicios": ("Novena for Freedom from Addiction", "addictions, dependency and chains of those we love"),
   "ansiedade": ("Novena to Overcome Anxiety", "anxiety, distress, deep sadness and inner peace"),
   "protecao": ("Novena for Spiritual Protection", "protection against evil, envy and spiritual attacks"),
   "causas": ("Novena for Impossible Causes", "impossible, urgent and desperate causes"),
   "luto": ("Novena for Comfort in Grief", "grief, longing and comfort after losing a loved one")},
 "meses": ["January","February","March","April","May","June","July","August","September","October","November","December"],
 "completa": "(Complete)", "dia_label": "Day {n}", "thumb_fmt": "NOVENA DAY {n}",
 "data_no_titulo_festa": False, "data_fmt": "",
 "periodo": "this morning",
 "desc_link": "📿 Pray the complete novena, every day in order: {url}",
 "cap_titulo": "⏱️ Novena Chapters:",
 "cap": ["Opening and Intention of the Day", "Reflection on the Word", "Novena Prayer", "Petition of the Day", "Our Father, Hail Mary and Glory Be", "Closing and Blessing"],
 "sinal_da_cruz": "In the name of the Father... and of the Son... and of the Holy Spirit... Amen...",
 "ato_contricao": ("Let us pray together the Act of Contrition... O my God... I am heartily sorry for having offended Thee... "
   "and I detest all my sins because of Thy just punishments... but most of all because they offend Thee, my God... who art all good and deserving of all my love... "
   "I firmly resolve, with the help of Thy grace... to sin no more and to avoid the near occasion of sin... Amen..."),
 "pai_nosso": ("Our Father, who art in heaven... hallowed be thy name... thy kingdom come... thy will be done on earth as it is in heaven... "
   "Give us this day our daily bread... and forgive us our trespasses... as we forgive those who trespass against us... "
   "and lead us not into temptation... but deliver us from evil... Amen..."),
 "ave_maria": ("Hail Mary, full of grace... the Lord is with thee... Blessed art thou among women... "
   "and blessed is the fruit of thy womb Jesus... Holy Mary, Mother of God... pray for us sinners... now and at the hour of our death... Amen..."),
 "gloria": "Glory be to the Father... and to the Son... and to the Holy Spirit... as it was in the beginning, is now, and ever shall be, world without end... Amen...",
 "oracoes_festa": {
   "immaculate": ("Let us now pray the prayer of this novena... O Mary Immaculate... conceived without sin... Patroness of our nation... "
     "look upon my tired heart... You who said yes to the plan of God... teach me to trust as you trusted... "
     "On this day of your novena I entrust to you my intention... Purify my life... keep all evil far from my home... "
     "and present my petition to your Son Jesus... Amen..."),
   "christmas": ("Let us now pray the prayer of this novena... O Mary... Mother of hope... "
     "you who kept in your heart the Child who was to be born... prepare my heart too, to welcome Jesus this Christmas... "
     "On this day of the novena I entrust to you my intention and my family... may the light of Bethlehem enter our home... and bring peace... healing... and unity... Amen...")},
 "oracao_festa_generica": "Let us now pray the prayer of this novena... O {inv}... on this day of your novena I entrust to you my intention... present it to your Son Jesus... Amen...",
 "oracao_pedido": ("Let us now pray the prayer of this novena... O Blessed Virgin Mary... Mother of God and our Mother... "
   "in this novena I come to your feet with a petition that weighs on my heart... You know my pain... even before I speak it... "
   "On this day of the novena I entrust to you my intention... and I ask you to bring it to your Son Jesus... as you brought the need of the couple at Cana... "
   "May God's will be done... and may I have strength to wait in faith... Amen..."),
 "jaculatoria": "{inv}... pray for us...",
 "cta_pista": "invite them to write in the comments their intention or the name of the person they entrust to Our Lady, because these intentions are prayed in our 24-hour live stream",
}

# ─────────────────────── MOTOR (idêntico em todos os canais) ───────────────────────
import datetime

CANAL = CFG["canal"]
TZ = CFG["tz"]
ATIVACAO_06H = CFG["ativacao"]
EPOCA_PEDIDOS = CFG["epoca_pedidos"]
FESTAS = CFG["festas"]
INTENCOES_FESTA = CFG["intencoes_festa"]
CATEGORIAS = CFG["categorias"]
ROTACAO_FALLBACK = ["saude", "familia", "emprego", "ansiedade", "filhos", "protecao", "vicios", "dividas", "causas", "luto"]
JANELA_ANTI_REPETICAO = 3
MIN_COMENTARIOS_RANKING = 5
STATUS_PRONTO = CFG["status_pronto"]
LANG_NAME = CFG["lang_name"]
PROGRESSAO_PEDIDO = {
    1: "Day of SURRENDER: present the pain honestly and open the heart.",
    2: "Day of SURRENDER: admit what we cannot carry alone.",
    3: "Day of SURRENDER: forgive and let go of what weighs, to receive grace.",
    4: "Day of PERSEVERANCE: keep faith even when nothing seems to change.",
    5: "Day of PERSEVERANCE: the strength of Mary at the foot of the cross.",
    6: "Day of PERSEVERANCE: fight discouragement and the voice of fear.",
    7: "Day of TRUST: signs that grace is already on its way.",
    8: "Day of TRUST: give thanks in advance for what God will do.",
    9: "Day of GRATITUDE and CONSECRATION: entrust life and the cause to Our Lady.",
}
ABA_NOVENAS = "NOVENAS"
ABA_TEMAS = "TEMAS_COMENTARIOS"


def _festas_do_ano(ano):
    out = []
    for f in FESTAS:
        ini = datetime.date(ano, f["inicio"][0], f["inicio"][1])
        out.append((ini, ini + datetime.timedelta(days=8), ini + datetime.timedelta(days=9), f))
    return sorted(out, key=lambda x: x[0])


def _festa_em(d):
    for ano in (d.year - 1, d.year):
        for ini, fim, dia_festa, f in _festas_do_ano(ano):
            if ini <= d <= fim:
                return ("festa", f, (d - ini).days + 1, ini)
            if d == dia_festa:
                return ("dia_festa", f, None, ini)
    return None


def _proxima_festa_inicio(d):
    for ano in (d.year, d.year + 1):
        for ini, _, _, _ in _festas_do_ano(ano):
            if ini >= d:
                return ini
    return None


def plano_do_dia(d):
    if d < ATIVACAO_06H:
        return None
    fe = _festa_em(d)
    if fe:
        tipo, f, n, ini = fe
        if tipo == "festa":
            return {"tipo": "festa", "dia": n, "festa": f, "ciclo_inicio": ini}
        return {"tipo": "avulsa", "motivo": f"dia da festa ({f['id']})"}
    if d < EPOCA_PEDIDOS:
        return {"tipo": "avulsa", "motivo": "antes da época de pedidos"}
    cursor = EPOCA_PEDIDOS
    guard = 0
    while cursor <= d and guard < 2000:
        guard += 1
        fe_c = _festa_em(cursor)
        if fe_c:
            cursor = fe_c[3] + datetime.timedelta(days=10)
            continue
        prox = _proxima_festa_inicio(cursor)
        fim_ciclo = cursor + datetime.timedelta(days=8)
        if prox is None or fim_ciclo < prox:
            if cursor <= d <= fim_ciclo:
                return {"tipo": "pedido", "dia": (d - cursor).days + 1, "ciclo_inicio": cursor}
            cursor = fim_ciclo + datetime.timedelta(days=1)
        else:
            if cursor <= d < prox:
                return {"tipo": "avulsa", "motivo": "intervalo antes de novena de festa"}
            cursor = prox
    return {"tipo": "avulsa", "motivo": "fallback"}


def nome_mes(d):
    return f"{CFG['meses'][d.month - 1]} {d.year}"


def nome_playlist(plano, categoria=None):
    if plano["tipo"] == "festa":
        return f"{plano['festa']['nome']} {plano['ciclo_inicio'].year} {CFG['completa']}"
    if plano["tipo"] == "pedido":
        return f"{CATEGORIAS[categoria][0]} — {nome_mes(plano['ciclo_inicio'])}"
    return None


def montar_titulo(plano, promessa, categoria=None, data=None):
    """[Palavra-chave de busca] + [Dia N] + 🙏 + [Dor/Promessa]."""
    promessa = (promessa or "").strip().strip(".").strip()
    n = plano["dia"]
    dia_lbl = CFG["dia_label"].format(n=n)
    if plano["tipo"] == "festa":
        base = f"{plano['festa']['nome']} {dia_lbl} 🙏"
        if CFG.get("data_no_titulo_festa") and data is not None:
            base += " " + CFG["data_fmt"].format(d=data.day, m=CFG["meses"][data.month - 1])
            base += " |"
    else:
        base = f"{CATEGORIAS[categoria][0]} – {dia_lbl} 🙏"
    titulo = f"{base} {promessa}".strip()
    if len(titulo) > 100:
        titulo = base.rstrip(" |")
    return titulo


def texto_thumb(plano):
    return CFG["thumb_fmt"].format(n=plano["dia"])


def tema_codificado(plano, categoria=None):
    chave = plano["festa"]["id"] if plano["tipo"] == "festa" else categoria
    return f"NOVENA|{nome_playlist(plano, categoria)}|{plano['dia']}|{plano['tipo']}|{chave}"


def montar_roteiro(plano, gancho, reflexao, suplica, encerramento):
    if plano["tipo"] == "festa":
        f = plano["festa"]
        oracao = CFG["oracoes_festa"].get(f["id"], CFG["oracao_festa_generica"]).format(inv=f["invocacao"])
        jac = CFG["jaculatoria"].format(inv=f["invocacao"])
    else:
        oracao = CFG["oracao_pedido"]
        jac = CFG["jaculatoria"].format(inv=CFG["invocacao_padrao"])
    partes = [gancho.strip(), CFG["sinal_da_cruz"], CFG["ato_contricao"], reflexao.strip(), oracao,
              suplica.strip(), CFG["pai_nosso"], CFG["ave_maria"], CFG["gloria"], jac,
              encerramento.strip(), CFG["sinal_da_cruz"]]
    return "\n\n".join(p for p in partes if p)


def _aba(planilha, nome, cabecalho):
    try:
        return planilha.worksheet(nome)
    except Exception:
        ws = planilha.add_worksheet(title=nome, rows=1000, cols=len(cabecalho))
        ws.update(values=[cabecalho], range_name="A1")
        return ws


def escolher_tema_pedido(planilha, ciclo_inicio):
    ws_nov = _aba(planilha, ABA_NOVENAS, ["Canal", "Inicio", "Tipo", "Categoria", "Fonte", "Criado_em"])
    linhas = ws_nov.get_all_values()[1:]
    ciclo_str = str(ciclo_inicio)
    do_canal = [l for l in linhas if len(l) >= 4 and l[0] == CANAL and l[2] == "pedido"]
    for l in do_canal:
        if l[1] == ciclo_str and l[3] in CATEGORIAS:
            return l[3]
    usados = [l[3] for l in sorted(do_canal, key=lambda x: x[1]) if l[1] < ciclo_str][-JANELA_ANTI_REPETICAO:]
    escolha, fonte = None, "fallback"
    try:
        ws_t = _aba(planilha, ABA_TEMAS, ["Canal", "Data", "Categoria", "Contagem"])
        rows = [r for r in ws_t.get_all_values()[1:] if len(r) >= 4 and r[0] == CANAL]
        if rows:
            ultima = max(r[1] for r in rows)
            dt_ult = datetime.datetime.strptime(ultima, "%Y-%m-%d").date()
            if (ciclo_inicio - dt_ult).days <= 30:
                lote = []
                for r in rows:
                    if r[1] == ultima and r[2] in CATEGORIAS:
                        try: lote.append((r[2], int(r[3])))
                        except ValueError: pass
                if sum(c for _, c in lote) >= MIN_COMENTARIOS_RANKING:
                    for cat, cnt in sorted(lote, key=lambda x: -x[1]):
                        if cnt > 0 and cat not in usados:
                            escolha, fonte = cat, f"comentarios {ultima}"
                            break
    except Exception as e:
        print(f"[WARN] Ranking de comentários indisponível: {e}")
    if not escolha:
        idx = len(do_canal)
        for i in range(len(ROTACAO_FALLBACK)):
            cand = ROTACAO_FALLBACK[(idx + i) % len(ROTACAO_FALLBACK)]
            if cand not in usados:
                escolha = cand
                break
    ws_nov.append_row([CANAL, ciclo_str, "pedido", escolha, fonte,
                       datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")])
    print(f"📿 Novo ciclo de pedido {ciclo_str}: '{escolha}' ({fonte})")
    return escolha
