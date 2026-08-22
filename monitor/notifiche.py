"""Invio degli avvisi su Telegram.

Due destinatari, due testi diversi:
  - Rino  riceve un solo messaggio, quando la data e' ufficiale, in tono da
          comunicato del box, e viene invitato a riaprire la web app;
  - Guido riceve tutto: preavvisi, data, vendita, allarmi, heartbeat.

L'interruttore per passare dal collaudo al destinatario vero e' uno solo:
TG_DESTINATARIO_REALE. Finche' vale 0, il messaggio di Rino arriva a Guido
con un'intestazione che lo dichiara.

Configurazione: variabili d'ambiente, oppure un file monitor/.env con righe
CHIAVE=valore (non versionato). Nessun segreto sta in questo file.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

QUI = Path(__file__).resolve().parent
ENV = QUI / ".env"

APP = "https://turk162.github.io/60sisentono/"
FOTO = APP + "voi_al_mugello.png"   # Rino e suo figlio, al Mugello
TIMEOUT = 20

# Chat di Rino imparata dal bot quando si collega al muretto: ha la
# precedenza su TG_CHAT_RINO, che resta utile solo per configurarla a mano.
chat_rino_appresa = None


def _config(chiave, difetto=None):
    if chiave in os.environ:
        return os.environ[chiave]
    if ENV.exists():
        for riga in ENV.read_text(encoding="utf-8").splitlines():
            riga = riga.strip()
            if not riga or riga.startswith("#") or "=" not in riga:
                continue
            k, _, v = riga.partition("=")
            if k.strip() == chiave:
                return v.strip().strip("'\"")
    return difetto


def _vero(valore):
    return str(valore).strip().lower() in ("1", "si", "sì", "true", "vero", "on")


class ErroreInvio(Exception):
    pass


# --------------------------------------------------------------------------
# Trasporto
# --------------------------------------------------------------------------

def _spedisci(chat_id, testo):
    """Manda un messaggio. Alza ErroreInvio se non ci riesce."""
    token = _config("TG_TOKEN")
    if _vero(_config("TG_FINTO", "0")):
        print(f"[telegram finto] -> chat {chat_id}\n{testo}\n")
        return
    if not token:
        raise ErroreInvio("TG_TOKEN non configurato")
    if not chat_id:
        raise ErroreInvio("chat id del destinatario non configurato")

    dati = json.dumps({
        "chat_id": chat_id,
        "text": testo,
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=dati, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            risposta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="replace")[:300]
        raise ErroreInvio(f"HTTP {e.code} da Telegram: {corpo}")
    except Exception as e:
        raise ErroreInvio(f"{type(e).__name__}: {e}")
    if not risposta.get("ok"):
        raise ErroreInvio(f"Telegram ha rifiutato: {risposta}")


def _a_guido(testo):
    _spedisci(_config("TG_CHAT_GUIDO"), testo)


def chat_rino():
    return chat_rino_appresa or _config("TG_CHAT_RINO")


def _a_rino(testo):
    """Rispetta l'interruttore: in collaudo il messaggio di Rino arriva a Guido."""
    if _vero(_config("TG_DESTINATARIO_REALE", "0")):
        _spedisci(chat_rino(), testo)
    else:
        _a_guido("🧪 COLLAUDO — questo messaggio andrebbe a Rino:\n"
                 "----------------------------------------\n" + testo)


def destinatario_reale():
    return _vero(_config("TG_DESTINATARIO_REALE", "0"))


def configurata():
    """Vero se c'e' abbastanza configurazione per provarci davvero."""
    if _vero(_config("TG_FINTO", "0")):
        return True
    if not _config("TG_TOKEN") or not _config("TG_CHAT_GUIDO"):
        return False
    return not destinatario_reale() or bool(chat_rino())


def link_muretto():
    """Il collegamento che la web app mette sul bottone. Nessun segreto:
    il nome utente di un bot e' pubblico."""
    nome = _config("TG_BOT_USERNAME")
    if not nome:
        return None
    return f"https://t.me/{nome.lstrip('@')}?start=muretto"


# --------------------------------------------------------------------------
# Testi
# --------------------------------------------------------------------------

def testo_rino(quando):
    return (
        "📻 RADIO BOX\n\n"
        "Rino, riaccendiamo la radio 🎧\n\n"
        "È uscita. GRAN PREMIO D'ITALIA, Mugello:\n"
        f"📅 {quando}\n\n"
        "Ufficiale, sul calendario vero. Sui vostri biglietti la casella "
        "DA DEFINIRE si può cancellare.\n\n"
        "Ai due posti in prato ci pensiamo noi: appena aprono le vendite li "
        "compriamo e te li facciamo arrivare qui.\n\n"
        "PRONTI? 👇\n"
        f"{FOTO}\n\n"
        "Ci vediamo in griglia. 🏁\n"
        "Guido, Gigi e Irma"
    )


def testo_guido(evento, dettagli, quando):
    evento_link = dettagli.get("link_evento")
    if evento == "calendario":
        return (
            "🟡 PREAVVISO — Mugello 2027\n\n"
            "Il GP d'Italia compare fra gli eventi 2027 della biglietteria ufficiale, "
            "ma la data è ancora marcata come non ufficiale.\n\n"
            f"Evento: {evento_link}\n\n"
            "A Rino non è stato mandato niente: si aspetta la data vera."
        )
    if evento == "data":
        return (
            "🟢 DATA UFFICIALE — GP Italia 2027\n\n"
            f"Quando: {quando}\n"
            f"Fonte: {dettagli.get('provenienza_data')}\n"
            f"Biglietteria: {evento_link}\n\n"
            "Biglietti non ancora in vendita: aspetto il secondo segnale.\n"
            + ("Messaggio a Rino: inviato." if destinatario_reale()
               else "Messaggio a Rino: NON inviato (interruttore su collaudo).")
        )
    if evento == "vendita":
        prato = dettagli.get("link_prato")
        return (
            "🔴 BIGLIETTI IN VENDITA — GP Italia 2027\n\n"
            f"Quando: {quando or 'data ancora non ufficiale'}\n\n"
            "PRATO:\n"
            + (prato if prato else
               "l'autodromo non ha ancora esposto il link diretto — parti da\n"
               "https://www.mugellocircuit.com/it/gran-premio/prezzo-biglietti/tickets-prato")
            + f"\n\nBiglietteria MotoGP:\n{evento_link}\n\n"
            "Muoviti: il prato al Mugello finisce."
        )
    return f"Evento {evento}: {json.dumps(dettagli, ensure_ascii=False)}"


def testo_heartbeat(riassunto):
    return (
        "🫀 Sentinella Mugello — tutto a posto\n\n"
        f"Stati: calendario {riassunto['stati']['calendario']} · "
        f"data {riassunto['stati']['data']} · vendita {riassunto['stati']['vendita']}\n"
        f"Ultimo controllo riuscito: {riassunto.get('ultimo_controllo_ok') or '—'}\n"
        f"Controlli falliti di fila: {riassunto.get('errori_consecutivi', 0)}\n"
        f"Destinatario Rino: {'REALE' if destinatario_reale() else 'collaudo (arriva a te)'}\n\n"
        "Se questo messaggio smette di arrivare, la sentinella è morta."
    )


# --------------------------------------------------------------------------
# Interfaccia usata dal controllore
# --------------------------------------------------------------------------

def avvisa(evento, dettagli, quando, prova=False):
    """Manda gli avvisi dell'evento. Alza ErroreInvio se qualcosa non parte."""
    marchio = "🧪 [PROVA] " if prova else ""
    _a_guido(marchio + testo_guido(evento, dettagli, quando))
    if evento == "data":
        _a_rino(marchio + testo_rino(quando))


def solo_a_me(testo, prova=False):
    _a_guido(("🧪 [PROVA] " if prova else "") + testo)


def heartbeat(riassunto):
    _a_guido(testo_heartbeat(riassunto))
