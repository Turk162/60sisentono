"""Lettura delle tre fonti ufficiali per il GP d'Italia 2027.

Ogni funzione restituisce un dizionario di fatti grezzi e alza ErroreFonte
quando la fonte non risponde o quando la struttura non e' piu' quella attesa.
Nessuna funzione qui dentro decide se un evento e' scattato: quello e'
compito di controllore.py.
"""

import html
import json
import re
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIMEOUT = 25

# Biglietteria ufficiale MotoGP (Dorna). L'evento 21081 e' il GP d'Italia.
URL_EVENTO_ITALIA = "https://tickets.motogp.com/it/21081-italy/"
URL_CALENDARIO_SHOP = "https://tickets.motogp.com/it/"

# API pubblica del calendario, quella che alimenta motogp.com/en/calendar
URL_STAGIONI = "https://api.motogp.pulselive.com/motogp/v1/results/seasons"
URL_EVENTI = "https://api.motogp.pulselive.com/motogp/v1/events?seasonYear={anno}"

# Autodromo del Mugello
URL_PRATO = "https://www.mugellocircuit.com/it/gran-premio/prezzo-biglietti/tickets-prato"
URL_ACQUISTO = "https://www.mugellocircuit.com/it/acquistare-biglietti"

ANNO = 2027


class ErroreFonte(Exception):
    """La fonte non risponde, oppure risponde in un modo che non sappiamo leggere."""

    def __init__(self, fonte, motivo):
        super().__init__(f"[{fonte}] {motivo}")
        self.fonte = fonte
        self.motivo = motivo


def _scarica(url, fonte, tentativi=2):
    ultimo = None
    for _ in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            # Un 404 e' un fatto, non un guasto: lo restituiamo al chiamante.
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as e:  # rete, DNS, TLS, timeout
            ultimo = e
    raise ErroreFonte(fonte, f"irraggiungibile: {type(ultimo).__name__}: {ultimo}")


def _oggetto_json(testo, inizio):
    """Estrae l'oggetto JSON che comincia alla prima graffa dopo `inizio`,
    bilanciando le parentesi (i payload sono annidati)."""
    i = testo.index("{", inizio)
    livello = 0
    for j in range(i, len(testo)):
        if testo[j] == "{":
            livello += 1
        elif testo[j] == "}":
            livello -= 1
            if livello == 0:
                return testo[i:j + 1]
    raise ValueError("graffa di chiusura non trovata")


def _carica(frammento):
    try:
        return json.loads(frammento)
    except json.JSONDecodeError:
        return json.loads(html.unescape(frammento))


# --------------------------------------------------------------------------
# Fonte 1 - biglietteria ufficiale MotoGP
# --------------------------------------------------------------------------

def biglietteria():
    """Legge il blocco <script id="event-date"> della pagina del GP d'Italia.

    Restituisce: stagione, data_ufficiale (bool), in_vendita (bool),
    data_inizio, data_fine, circuito, in_calendario_2027 (bool).
    """
    stato, corpo = _scarica(URL_EVENTO_ITALIA, "biglietteria")
    if stato != 200:
        raise ErroreFonte("biglietteria", f"la pagina dell'evento 21081 risponde HTTP {stato}")

    m = re.search(r'<script id="event-date" type="application/json">\s*(\{.*?\})\s*</script>', corpo, re.S)
    if not m:
        raise ErroreFonte("biglietteria", 'blocco <script id="event-date"> sparito: la pagina e\' cambiata')
    try:
        d = _carica(m.group(1))
    except Exception as e:
        raise ErroreFonte("biglietteria", f"JSON dell'evento illeggibile: {e}")

    # Controlli di sanita': se saltano, stiamo leggendo un'altra cosa.
    if d.get("id") != 21081:
        raise ErroreFonte("biglietteria", f"id evento inatteso: {d.get('id')} invece di 21081")
    circuito = ((d.get("stadium") or {}).get("name") or "")
    if "mugello" not in circuito.lower():
        raise ErroreFonte("biglietteria", f"circuito inatteso: {circuito!r}")
    for campo in ("dateUnknown", "isClosed", "seasonName", "startDate"):
        if campo not in d:
            raise ErroreFonte("biglietteria", f"campo {campo!r} assente dal payload")

    inizio = (d.get("startDate") or {}).get("date", "")[:10]
    fine = (d.get("endDate") or {}).get("date", "")[:10]

    return {
        "stagione": str(d.get("seasonName")),
        "data_ufficiale": d["dateUnknown"] is False,
        "in_vendita": d["isClosed"] is False,
        "data_inizio": inizio,
        "data_fine": fine,
        "circuito": circuito,
        "citta": d.get("city"),
        "link": URL_EVENTO_ITALIA,
        "in_calendario_2027": _in_calendario_shop(),
    }


def _in_calendario_shop():
    """Vero se una card con il Mugello compare fra gli eventi 2027 della vetrina."""
    stato, corpo = _scarica(URL_CALENDARIO_SHOP, "biglietteria")
    if stato != 200:
        raise ErroreFonte("biglietteria", f"la vetrina risponde HTTP {stato}")
    testo = html.unescape(re.sub(r"\s+", " ", corpo))

    carte = []
    for m in re.finditer(r"cardHandler\(", testo):
        try:
            carte.append(_carica(_oggetto_json(testo, m.end() - 1)))
        except Exception:
            continue
    if not carte:
        raise ErroreFonte("biglietteria", "nessuna card evento nella vetrina: pagina cambiata")
    if not any(c.get("seasonName") == str(ANNO) for c in carte):
        raise ErroreFonte("biglietteria", f"nessuna card della stagione {ANNO} nella vetrina")

    return any(
        c.get("seasonName") == str(ANNO) and _e_mugello(c)
        for c in carte
    )


def _e_mugello(carta):
    """Attenzione: il codice paese IT vale anche per San Marino (Misano).
    L'identificazione passa dal circuito, non dal paese."""
    if str(carta.get("id")) == "21081":
        return True
    circuito = ((carta.get("stadium") or {}).get("name") or "")
    citta = (carta.get("city") or "")
    nome = (carta.get("name") or "")
    if "mugello" in circuito.lower() or "scarperia" in citta.lower():
        return True
    if re.search(r"\bital(y|ia)\b", nome, re.I) and "san marino" not in nome.lower():
        return True
    return False


# --------------------------------------------------------------------------
# Fonte 2 - calendario ufficiale motogp.com (API)
# --------------------------------------------------------------------------

def calendario():
    """Restituisce: stagione_aperta (bool), gara_trovata (bool), data_inizio, data_fine."""
    stato, corpo = _scarica(URL_STAGIONI, "calendario")
    if stato != 200:
        raise ErroreFonte("calendario", f"elenco stagioni HTTP {stato}")
    try:
        stagioni = json.loads(corpo)
    except Exception as e:
        raise ErroreFonte("calendario", f"elenco stagioni illeggibile: {e}")
    if not isinstance(stagioni, list) or not stagioni:
        raise ErroreFonte("calendario", "elenco stagioni vuoto")
    anni = {s.get("year") for s in stagioni}
    if not any(isinstance(a, int) and a >= 2026 for a in anni):
        raise ErroreFonte("calendario", f"elenco stagioni senza annate recenti: {sorted(a for a in anni if a)}")

    if ANNO not in anni:
        return {"stagione_aperta": False, "gara_trovata": False, "data_inizio": None, "data_fine": None}

    stato, corpo = _scarica(URL_EVENTI.format(anno=ANNO), "calendario")
    if stato == 404:
        # Stagione elencata ma senza eventi: stato transitorio plausibile.
        return {"stagione_aperta": True, "gara_trovata": False, "data_inizio": None, "data_fine": None}
    if stato != 200:
        raise ErroreFonte("calendario", f"eventi {ANNO} HTTP {stato}")
    try:
        eventi = json.loads(corpo)
    except Exception as e:
        raise ErroreFonte("calendario", f"eventi {ANNO} illeggibili: {e}")
    if not isinstance(eventi, list):
        raise ErroreFonte("calendario", "risposta eventi non e' una lista")

    gp = [
        e for e in eventi
        if e.get("kind") == "GP"
        and "mugello" in ((e.get("circuit") or {}).get("name") or "").lower()
    ]
    if not gp:
        return {"stagione_aperta": True, "gara_trovata": False, "data_inizio": None, "data_fine": None}

    g = gp[0]
    return {
        "stagione_aperta": True,
        "gara_trovata": True,
        "nome": (g.get("name") or "").strip(),
        "data_inizio": (g.get("date_start") or "")[:10],
        "data_fine": (g.get("date_end") or "")[:10],
    }


# --------------------------------------------------------------------------
# Fonte 3 - autodromo del Mugello
# --------------------------------------------------------------------------

RE_TICKETONE = re.compile(r"https://www\.ticketone\.it/event/mugello-gran-premio-ditalia-(\d{4})-[^\"'\s]+")


def mugello():
    """Cerca sui link uscenti dell'autodromo i biglietti TicketOne dell'anno 2027.

    Restituisce: anni_in_vendita (lista), link_prato (str|None).
    """
    anni = set()
    link_prato = None
    fallita_prato = None

    stato, corpo = _scarica(URL_PRATO, "mugello")
    if stato != 200:
        fallita_prato = f"pagina prato HTTP {stato}"
    else:
        trovati = RE_TICKETONE.findall(corpo)
        if not trovati:
            fallita_prato = "nessun link TicketOne sulla pagina prato: struttura cambiata"
        for m in RE_TICKETONE.finditer(corpo):
            anni.add(int(m.group(1)))
            if int(m.group(1)) == ANNO and link_prato is None:
                link_prato = m.group(0).rstrip("/") + "/"

    stato, corpo = _scarica(URL_ACQUISTO, "mugello")
    if stato == 200:
        for m in RE_TICKETONE.finditer(corpo):
            anni.add(int(m.group(1)))

    if fallita_prato and not anni:
        raise ErroreFonte("mugello", fallita_prato)

    return {
        "anni_in_vendita": sorted(anni),
        "in_vendita": ANNO in anni,
        "link_prato": link_prato,
        "avviso": fallita_prato,
    }
