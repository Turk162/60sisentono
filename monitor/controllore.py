#!/usr/bin/env python3
"""Sorveglianza del GP d'Italia 2027 al Mugello.

Tre stati, in ordine di avanzamento:

  calendario  il Mugello compare fra gli eventi 2027 (data ancora non ufficiale)
  data        la data e' ufficiale
  vendita     i biglietti sono acquistabili

Ogni stato viene annunciato una volta sola: il file di stato ricorda cosa e'
gia' stato detto. Se una fonte si rompe o cambia struttura il controllo non
tace: produce un allarme.

Uso:
  controllore.py                  controllo reale
  controllore.py --prova data     simula uno scenario con valori finti
  controllore.py --prova tutto    simula la sequenza completa
  controllore.py --telegram       manda i messaggi di collaudo e esce
  controllore.py --stato          mostra il file di stato
  controllore.py --azzera-prova   ripulisce lo stato di prova

Configurazione Telegram: vedi .env.esempio
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fonti
import notifiche
from fonti import ErroreFonte

QUI = Path(__file__).resolve().parent
STATO = QUI / "stato.json"
STATO_PROVA = QUI / "stato_prova.json"
LOG = QUI / "controllore.log"
PUBBLICO = QUI.parent / "stato_gara.json"   # letto dalla web app

ROMA = ZoneInfo("Europe/Rome")   # il container gira a UTC, ma i log li leggi tu

EVENTI = ("calendario", "data", "vendita")
GIORNI_HEARTBEAT = 7

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


# --------------------------------------------------------------------------
# Stato persistente
# --------------------------------------------------------------------------

def stato_vuoto():
    return {
        "versione": 1,
        "annunciati": {},          # evento -> {"il": iso, "dati": {...}}
        "ultimo_controllo_ok": None,
        "ultimo_heartbeat": None,
        "errori_consecutivi": 0,
        "ultimo_errore": None,
        "chat_rino": None,         # imparata dal bot al primo /start
        "regalo_aperto_il": None,
        "tg_offset": 0,            # coda getUpdates gia' letta
    }


def leggi_stato(percorso):
    if not percorso.exists():
        return stato_vuoto()
    try:
        d = json.loads(percorso.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"file di stato illeggibile ({percorso}): {e}\n"
                         f"correggilo a mano oppure cancellalo per ripartire da zero.")
    base = stato_vuoto()
    base.update(d)
    return base


def scrivi_stato(percorso, stato):
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(stato, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(percorso)


# --------------------------------------------------------------------------
# Lettura delle fonti e valutazione degli stati
# --------------------------------------------------------------------------

def leggi_fonti():
    """Interroga le tre fonti. Una fonte rotta non ferma le altre: diventa un allarme."""
    letture, allarmi = {}, []
    for nome, funzione in (("biglietteria", fonti.biglietteria),
                           ("calendario", fonti.calendario),
                           ("mugello", fonti.mugello)):
        try:
            letture[nome] = funzione()
        except ErroreFonte as e:
            letture[nome] = None
            allarmi.append(str(e))
        except Exception as e:  # imprevisto vero
            letture[nome] = None
            allarmi.append(f"[{nome}] errore imprevisto: {type(e).__name__}: {e}")
    return letture, allarmi


def valuta(letture):
    """Da fatti grezzi a tre booleani, piu' i dettagli utili nei messaggi."""
    b = letture.get("biglietteria") or {}
    c = letture.get("calendario") or {}
    m = letture.get("mugello") or {}

    anno = str(fonti.ANNO)

    in_calendario = bool(b.get("in_calendario_2027")) or bool(c.get("gara_trovata"))

    # La data e' ufficiale se lo dice l'API del calendario, oppure se la
    # biglietteria toglie il flag "data non ufficiale" e indica un giorno del 2027.
    data_da_shop = (
        b.get("data_ufficiale")
        and b.get("stagione") == anno
        and str(b.get("data_inizio", "")).startswith(anno)
    )
    data_ufficiale = bool(c.get("gara_trovata")) or bool(data_da_shop)

    in_vendita = bool(b.get("in_vendita")) or bool(m.get("in_vendita"))

    # La data buona e' quella del calendario; la biglietteria e' il ripiego.
    if c.get("gara_trovata"):
        inizio, fine, provenienza = c.get("data_inizio"), c.get("data_fine"), "calendario ufficiale motogp.com"
    elif data_da_shop:
        inizio, fine, provenienza = b.get("data_inizio"), b.get("data_fine"), "biglietteria ufficiale MotoGP"
    else:
        inizio = fine = provenienza = None

    return (
        {"calendario": in_calendario, "data": data_ufficiale, "vendita": in_vendita},
        {
            "data_inizio": inizio,
            "data_fine": fine,
            "provenienza_data": provenienza,
            "link_evento": b.get("link") or fonti.URL_EVENTO_ITALIA,
            "link_prato": m.get("link_prato"),
            "anni_ticketone": m.get("anni_in_vendita"),
        },
    )


def data_a_parole(inizio, fine):
    """2027-05-28 / 2027-05-30 -> '28-30 maggio 2027'."""
    if not inizio:
        return None
    try:
        d1 = datetime.strptime(inizio, "%Y-%m-%d")
        d2 = datetime.strptime(fine, "%Y-%m-%d") if fine else d1
    except ValueError:
        return inizio
    if d1.month == d2.month:
        giorni = f"{d1.day}-{d2.day}" if d2.day != d1.day else f"{d1.day}"
        return f"{giorni} {MESI[d1.month - 1]} {d1.year}"
    return f"{d1.day} {MESI[d1.month - 1]} - {d2.day} {MESI[d2.month - 1]} {d2.year}"


# --------------------------------------------------------------------------
# Consegna degli avvisi
# --------------------------------------------------------------------------

def annuncia(evento, dettagli, prova=False):
    """Manda l'avviso dell'evento. Restituisce (riuscito, motivo_fallimento).

    Se l'invio non riesce l'evento NON va registrato come annunciato: si
    riprova al giro dopo. Meglio un doppione che un annuncio perso."""
    quando = data_a_parole(dettagli.get("data_inizio"), dettagli.get("data_fine"))
    print(f"\n>>> AVVISO [{evento}] {quando or ''}")
    try:
        notifiche.avvisa(evento, dettagli, quando, prova=prova)
    except notifiche.ErroreInvio as e:
        print(f"    invio FALLITO: {e}")
        return False, str(e)
    print("    inviato")
    return True, None


def avvisa_me(testo, prova=False):
    """Allarmi, riprese e heartbeat: solo a Guido."""
    print(f"\n>>> AVVISO [solo a te]\n{testo}")
    try:
        notifiche.solo_a_me(testo, prova=prova)
    except notifiche.ErroreInvio as e:
        print(f"    invio FALLITO: {e}")
        return False
    return True


# --------------------------------------------------------------------------
# Stato pubblico per la web app
# --------------------------------------------------------------------------

def pubblica_stato_gara(stati, dettagli):
    """Scrive stato_gara.json accanto a index.html.

    Riscrive solo se qualcosa e' davvero cambiato, cosi' il repo non risulta
    modificato a ogni controllo. Restituisce True se il file e' cambiato."""
    contenuto = {
        "data_confermata": stati["data"],
        "data_testo": data_a_parole(dettagli.get("data_inizio"), dettagli.get("data_fine")),
        "data_inizio": dettagli.get("data_inizio"),
        "data_fine": dettagli.get("data_fine"),
        "biglietti_in_vendita": stati["vendita"],
        "bot": notifiche.link_muretto(),
    }
    if PUBBLICO.exists():
        try:
            vecchio = json.loads(PUBBLICO.read_text(encoding="utf-8"))
            vecchio.pop("aggiornato", None)
            if vecchio == contenuto:
                return False
        except Exception:
            pass                      # illeggibile: lo riscriviamo
    da_scrivere = dict(contenuto, aggiornato=datetime.now(ROMA).isoformat(timespec="seconds"))
    PUBBLICO.write_text(json.dumps(da_scrivere, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# Log
# --------------------------------------------------------------------------

def registra(riga):
    ora = datetime.now(ROMA).strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{ora} | {riga}\n")


# --------------------------------------------------------------------------
# Valori finti per la modalita' di prova
# --------------------------------------------------------------------------

def letture_finte(scenario):
    base_shop = {
        "stagione": "2027", "data_ufficiale": False, "in_vendita": False,
        "data_inizio": "2026-05-28", "data_fine": "2026-05-30",
        "circuito": "Autodromo Internazionale del Mugello", "citta": "Scarperia (FI)",
        "link": fonti.URL_EVENTO_ITALIA, "in_calendario_2027": False,
    }
    base_cal = {"stagione_aperta": False, "gara_trovata": False, "data_inizio": None, "data_fine": None}
    base_mug = {"anni_in_vendita": [2026], "in_vendita": False, "link_prato": None, "avviso": None}

    if scenario == "calendario":
        base_shop["in_calendario_2027"] = True

    elif scenario == "data":
        base_shop.update(in_calendario_2027=True, data_ufficiale=True,
                         data_inizio="2027-05-28", data_fine="2027-05-30")
        base_cal.update(stagione_aperta=True, gara_trovata=True, nome="GRAND PRIX OF ITALY",
                        data_inizio="2027-05-28", data_fine="2027-05-30")

    elif scenario == "vendita":
        base_shop.update(in_calendario_2027=True, data_ufficiale=True, in_vendita=True,
                         data_inizio="2027-05-28", data_fine="2027-05-30")
        base_cal.update(stagione_aperta=True, gara_trovata=True, nome="GRAND PRIX OF ITALY",
                        data_inizio="2027-05-28", data_fine="2027-05-30")
        base_mug.update(anni_in_vendita=[2026, 2027], in_vendita=True,
                        link_prato="https://www.ticketone.it/event/mugello-gran-premio-ditalia-2027-"
                                   "autodromo-internazionale-del-mugello-99999999/")

    elif scenario == "guasto":
        return {"biglietteria": None, "calendario": base_cal, "mugello": base_mug}, [
            '[biglietteria] blocco <script id="event-date"> sparito: la pagina e\' cambiata'
        ]

    return {"biglietteria": base_shop, "calendario": base_cal, "mugello": base_mug}, []


# --------------------------------------------------------------------------
# Giro di controllo
# --------------------------------------------------------------------------

def controlla(scenario=None, silenzioso=False):
    prova = scenario is not None
    percorso = STATO_PROVA if prova else STATO
    stato = leggi_stato(percorso)
    adesso = datetime.now(ROMA).isoformat(timespec="seconds")

    # La chat imparata dal bot vive sempre nello stato vero, anche quando
    # stiamo simulando: serve al giro di prova con una persona in carne e ossa.
    notifiche.chat_rino_appresa = (stato if not prova else leggi_stato(STATO)).get("chat_rino")

    if prova:
        letture, allarmi = letture_finte(scenario)
    else:
        letture, allarmi = leggi_fonti()
        # Coda del bot: se qualcuno si e' collegato al muretto mentre
        # l'ascoltatore era spento, non va perso.
        try:
            import bot
            if bot.processa(stato):
                notifiche.chat_rino_appresa = stato.get("chat_rino")
        except notifiche.ErroreInvio as e:
            allarmi.append(f"[telegram] coda del bot non letta: {e}")

    stati, dettagli = valuta(letture)

    # Un evento e' nuovo se e' vero adesso e non era mai stato annunciato.
    nuovi = [e for e in EVENTI if stati[e] and e not in stato["annunciati"]]
    # "calendario" e' solo un preavviso: se arriva insieme a qualcosa di piu'
    # avanzato lo si registra senza annunciarlo, per non mandare due avvisi.
    da_annunciare = [e for e in nuovi if not (e == "calendario" and len(nuovi) > 1)]

    annunciati_ora = []
    for e in nuovi:
        if e in da_annunciare:
            riuscito, motivo = annuncia(e, dettagli, prova=prova)
            if not riuscito:
                # Non lo registriamo: al prossimo giro ci riprova.
                allarmi.append(f"[telegram] avviso '{e}' non consegnato: {motivo}")
                continue
            annunciati_ora.append(e)
        stato["annunciati"][e] = {"il": adesso, "dati": dettagli}

    # Allarmi: rumorosi, ma non ripetuti a ogni giro all'infinito.
    if allarmi:
        stato["errori_consecutivi"] += 1
        stato["ultimo_errore"] = {"il": adesso, "allarmi": allarmi}
        if stato["errori_consecutivi"] in (1, 4, 12) or stato["errori_consecutivi"] % 28 == 0:
            avvisa_me("⚠️ Controllo in errore ({}° giro consecutivo):\n- {}".format(
                stato["errori_consecutivi"], "\n- ".join(allarmi)), prova=prova)
    else:
        if stato["errori_consecutivi"]:
            avvisa_me(f"✅ Fonti tornate a posto dopo {stato['errori_consecutivi']} giri in errore.",
                      prova=prova)
        stato["errori_consecutivi"] = 0
        stato["ultimo_errore"] = None
        stato["ultimo_controllo_ok"] = adesso

    # Heartbeat settimanale: solo a me, e solo se il giro e' andato bene.
    heartbeat_dovuto = _heartbeat_dovuto(stato)
    if heartbeat_dovuto and not prova and not allarmi:
        try:
            notifiche.heartbeat({"stati": {k: "sì" if v else "no" for k, v in stati.items()},
                                 "ultimo_controllo_ok": stato["ultimo_controllo_ok"],
                                 "errori_consecutivi": stato["errori_consecutivi"]})
            stato["ultimo_heartbeat"] = adesso
            print("\n>>> heartbeat settimanale inviato")
        except notifiche.ErroreInvio as e:
            allarmi.append(f"[telegram] heartbeat non consegnato: {e}")
            print(f"\n>>> heartbeat FALLITO: {e}")

    scrivi_stato(percorso, stato)
    if not prova and pubblica_stato_gara(stati, dettagli):
        print(f">>> {PUBBLICO.name} aggiornato: va pubblicato su GitHub Pages")

    riga = "{} | calendario={} data={} vendita={} | nuovi={} | allarmi={}".format(
        "PROVA:" + scenario if prova else "OK" if not allarmi else "ERRORE",
        *("si" if stati[e] else "no" for e in EVENTI),
        ",".join(annunciati_ora) or "-", len(allarmi))
    if not prova:
        registra(riga)
    if not silenzioso:
        print(riga)

    return {
        "istante": adesso, "prova": prova, "letture": letture, "stati": stati,
        "dettagli": dettagli, "annunciati_ora": annunciati_ora,
        "allarmi": allarmi, "heartbeat_dovuto": heartbeat_dovuto,
    }


def _heartbeat_dovuto(stato):
    ultimo = stato.get("ultimo_heartbeat")
    if not ultimo:
        return True
    try:
        return datetime.now(ROMA) - datetime.fromisoformat(ultimo) >= timedelta(days=GIORNI_HEARTBEAT)
    except ValueError:
        return True


def collaudo_telegram():
    """Manda la catena completa di messaggi con valori finti, senza toccare lo stato."""
    if not notifiche.configurata():
        raise SystemExit(
            "Telegram non configurato.\n"
            "Servono TG_TOKEN e TG_CHAT_GUIDO (piu' TG_CHAT_RINO se TG_DESTINATARIO_REALE=1),\n"
            f"da variabili d'ambiente o dal file {notifiche.ENV}.\n"
            "Per vedere i testi senza mandare niente: TG_FINTO=1")

    print(f"destinatario di Rino: {'REALE' if notifiche.destinatario_reale() else 'collaudo (arriva a te)'}\n")
    dettagli = {
        "data_inizio": "2027-05-28", "data_fine": "2027-05-30",
        "provenienza_data": "calendario ufficiale motogp.com",
        "link_evento": fonti.URL_EVENTO_ITALIA,
        "link_prato": "https://www.ticketone.it/event/mugello-gran-premio-ditalia-2027-"
                      "autodromo-internazionale-del-mugello-99999999/",
        "anni_ticketone": [2026, 2027],
    }
    quando = data_a_parole(dettagli["data_inizio"], dettagli["data_fine"])

    # Il primo messaggio in ordine di tempo: quello che Rino riceve al tap
    # sul bottone "Collegati al muretto", quando apre il regalo.
    import bot
    print("-> benvenuto (al tap sul muretto)")
    notifiche._a_rino("🧪 [PROVA] " + bot.benvenuto("Rino"))

    for evento in EVENTI:
        print(f"-> {evento}")
        notifiche.avvisa(evento, dettagli, quando, prova=True)
    print("-> heartbeat")
    notifiche.heartbeat({"stati": {"calendario": "no", "data": "no", "vendita": "no"},
                         "ultimo_controllo_ok": "collaudo", "errori_consecutivi": 0})
    print("\nfatto: controlla la chat.")


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Sorveglianza GP d'Italia 2027 al Mugello")
    p.add_argument("--prova", choices=["calendario", "data", "vendita", "guasto", "tutto"],
                   help="usa valori finti invece delle fonti reali")
    p.add_argument("--stato", action="store_true", help="mostra il file di stato e esci")
    p.add_argument("--azzera-prova", action="store_true", help="cancella lo stato di prova")
    p.add_argument("--telegram", action="store_true",
                   help="manda subito i messaggi di collaudo e esci")
    p.add_argument("--json", action="store_true", help="stampa il risultato in JSON")
    a = p.parse_args()

    if a.telegram:
        collaudo_telegram()
        return

    if a.azzera_prova:
        STATO_PROVA.unlink(missing_ok=True)
        print(f"stato di prova azzerato ({STATO_PROVA.name})")
        return

    if a.stato:
        for percorso in (STATO, STATO_PROVA):
            print(f"--- {percorso.name}")
            print(json.dumps(leggi_stato(percorso), indent=2, ensure_ascii=False) if percorso.exists() else "(assente)")
        return

    if a.prova == "tutto":
        STATO_PROVA.unlink(missing_ok=True)
        esiti = []
        for s in ("calendario", "data", "vendita"):
            print(f"\n=== giro con scenario {s} ===")
            esiti.append(controlla(scenario=s))
        print("\n=== ripetizione dell'ultimo giro: non deve annunciare nulla ===")
        esiti.append(controlla(scenario="vendita"))
        if a.json:
            print(json.dumps(esiti, indent=2, ensure_ascii=False))
        return

    esito = controlla(scenario=a.prova)
    if a.json:
        print(json.dumps(esito, indent=2, ensure_ascii=False))
    # Uscita non nulla se qualcosa non ha funzionato: utile allo scheduler.
    sys.exit(1 if esito["allarmi"] else 0)


if __name__ == "__main__":
    main()
