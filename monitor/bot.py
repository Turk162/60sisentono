"""Il bot che risponde a Rino quando si collega al muretto.

Quando Rino vince il gioco compare il bottone "Collegati al muretto": apre
Telegram sul bot con /start. Da quel momento:

  - il bot gli manda il messaggio di benvenuto (l'attesa della data);
  - la sua chat viene memorizzata nel file di stato, cosi' il comunicato
    RADIO BOX sapra' dove arrivare;
  - Guido riceve l'avviso che il regalo e' stato aperto.

Due modi di funzionare:
  bot.py --ascolta     resta in ascolto e risponde in pochi secondi
  bot.py --una-volta   svuota la coda e esce (lo fa anche il controllore)
  bot.py --chi         dice chi risulta collegato al muretto
  bot.py --dimentica   cancella il collegamento, per rifare la prova da zero
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notifiche

ROMA = ZoneInfo("Europe/Rome")

APP = notifiche.APP


BENVENUTO = (
    "📻 RADIO BOX\n\n"
    "{nome}, qui è il muretto 🎧 Ti riceviamo forte e chiaro.\n\n"
    "Sui due biglietti che hai appena vinto, alla voce data, c'è scritto "
    "DA DEFINIRE. Il contratto del Mugello con la MotoGP arriva al 2026 e "
    "il calendario 2027 non è ancora uscito: quella data, oggi, non ce l'ha "
    "nessuno.\n\n"
    "I due posti in prato però sono vostri. 🏁\n\n"
    "Da adesso stiamo di guardia sui canali ufficiali, giorno e notte. "
    "Appena la data esce, questa radio si riaccende e sei il primo a saperlo. "
    "Poi ci pensiamo noi: compriamo i biglietti e te li facciamo arrivare "
    "qui, su Telegram.\n\n"
    "Tu non devi fare niente. Tieni il telefono acceso. 📱\n\n"
    "Buon compleanno dal muretto. 🎂\n"
    "Guido, Gigi e Irma"
)


def benvenuto(nome):
    """Il nome arriva da Telegram: durante il giro di prova saluta l'amico,
    la sera vera saluta Rino."""
    return BENVENUTO.replace("{nome}", nome)


GIA_COLLEGATO = (
    "Ti abbiamo già in linea. Stiamo di guardia.\n"
    "Quando esce la data ti chiamiamo noi."
)


def _chiama(metodo, parametri, timeout=60):
    token = notifiche._config("TG_TOKEN")
    if not token:
        raise notifiche.ErroreInvio("TG_TOKEN non configurato")
    dati = json.dumps(parametri).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{metodo}",
        data=dati, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            risposta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise notifiche.ErroreInvio(f"HTTP {e.code} da {metodo}: "
                                    f"{e.read().decode('utf-8', errors='replace')[:200]}")
    except Exception as e:
        raise notifiche.ErroreInvio(f"{type(e).__name__} su {metodo}: {e}")
    if not risposta.get("ok"):
        raise notifiche.ErroreInvio(f"{metodo} rifiutato: {risposta}")
    return risposta.get("result")


def _rispondi(chat_id, testo):
    _chiama("sendMessage", {"chat_id": chat_id, "text": testo,
                            "disable_web_page_preview": True}, timeout=20)


def processa(stato, attesa=0):
    """Legge i messaggi arrivati al bot e reagisce ai /start.

    `stato` e' il dizionario del controllore, modificato sul posto.
    Restituisce il numero di nuovi collegamenti. Alza ErroreInvio sui guasti.
    """
    if notifiche._vero(notifiche._config("TG_FINTO", "0")):
        return 0                      # in modalita' finta non c'e' nessuna coda da leggere

    aggiornamenti = _chiama("getUpdates", {
        "offset": stato.get("tg_offset", 0),
        "timeout": attesa,
        "allowed_updates": ["message"],
    }, timeout=attesa + 20)

    nuovi = 0
    for agg in aggiornamenti or []:
        stato["tg_offset"] = agg["update_id"] + 1
        msg = agg.get("message") or {}
        testo = (msg.get("text") or "").strip()
        chat = (msg.get("chat") or {})
        chat_id = chat.get("id")
        if not chat_id or not testo.startswith("/start"):
            continue

        nome = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or "?"
        etichetta = f"{nome} (@{chat.get('username')})" if chat.get("username") else nome

        if str(chat_id) == str(stato.get("chat_rino") or ""):
            _rispondi(chat_id, GIA_COLLEGATO)
            continue

        if stato.get("chat_rino"):
            # Qualcun altro ha trovato il bot: non e' Rino, non registriamo niente.
            notifiche.solo_a_me(f"👤 /start da uno sconosciuto: {etichetta} (chat {chat_id}). Ignorato.")
            continue

        # Primo collegamento: e' lui.
        stato["chat_rino"] = chat_id
        stato["regalo_aperto_il"] = datetime.now(ROMA).isoformat(timespec="seconds")
        _rispondi(chat_id, benvenuto(chat.get("first_name") or "pilota"))
        nuovi += 1

        avviso = (f"🎁 Rino ha aperto il regalo e si è collegato al muretto.\n\n"
                  f"Chi: {etichetta}\nChat id: {chat_id}\n"
                  f"Quando: {stato['regalo_aperto_il']}\n\n"
                  "Benvenuto inviato.")
        if not notifiche.destinatario_reale():
            avviso += ("\n\n⚠️ TG_DESTINATARIO_REALE è ancora 0: il comunicato con la data "
                       "arriverebbe a te, non a lui. Mettilo a 1.")
        notifiche.solo_a_me(avviso)

    return nuovi


def main():
    import controllore  # importato qui: serve solo alla riga di comando

    p = argparse.ArgumentParser(description="Bot del muretto")
    p.add_argument("--ascolta", action="store_true", help="resta in ascolto (Ctrl-C per fermare)")
    p.add_argument("--una-volta", action="store_true", help="svuota la coda e esci")
    p.add_argument("--chi", action="store_true", help="mostra chi e' collegato al muretto")
    p.add_argument("--dimentica", action="store_true",
                   help="cancella il collegamento: il prossimo /start ricomincia da capo")
    a = p.parse_args()

    if a.chi:
        stato = controllore.leggi_stato(controllore.STATO)
        if stato.get("chat_rino"):
            print(f"collegato: chat {stato['chat_rino']}, dal {stato.get('regalo_aperto_il')}")
        else:
            print("nessuno collegato: il prossimo /start verra' registrato come Rino")
        return

    if a.dimentica:
        stato = controllore.leggi_stato(controllore.STATO)
        precedente = stato.get("chat_rino")
        stato["chat_rino"] = None
        stato["regalo_aperto_il"] = None
        controllore.scrivi_stato(controllore.STATO, stato)
        print(f"collegamento cancellato (era chat {precedente}). "
              "Il prossimo /start verra' registrato come Rino.")
        return

    if not a.ascolta and not a.una_volta:
        p.error("scegli --ascolta, --una-volta, --chi oppure --dimentica")

    if a.una_volta:
        stato = controllore.leggi_stato(controllore.STATO)
        n = processa(stato)
        controllore.scrivi_stato(controllore.STATO, stato)
        print(f"messaggi elaborati, nuovi collegamenti: {n}")
        return

    print("in ascolto sul bot. Ctrl-C per fermare.")
    try:
        while True:
            stato = controllore.leggi_stato(controllore.STATO)
            try:
                n = processa(stato, attesa=50)
                if n:
                    print(f"nuovo collegamento registrato (chat {stato.get('chat_rino')})")
            except notifiche.ErroreInvio as e:
                print(f"errore: {e}")
            controllore.scrivi_stato(controllore.STATO, stato)
    except KeyboardInterrupt:
        print("\nascolto interrotto.")


if __name__ == "__main__":
    main()
