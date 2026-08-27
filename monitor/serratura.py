"""Due serrature, per far convivere l'ascoltatore e il giro da cron.

Sono due processi distinti che toccano le stesse cose:

  bot.py --ascolta    gira sempre, interroga getUpdates ogni 50 secondi
  giro.sh -> controllore.py   parte da cron alle 07/13/18 italiane

Senza coordinamento si pestano i piedi in due modi. Telegram rifiuta con un
409 due getUpdates contemporanei sullo stesso token, quindi uno dei due
perderebbe la coda. E tutti e due leggono stato.json, ci lavorano sopra e lo
riscrivono per intero: chi scrive per ultimo cancella il lavoro dell'altro.

  ascolto.lock   la tiene l'ascoltatore per tutta la sua vita. Chi la trova
                 occupata sa che c'e' gia' un ascoltatore vivo: il controllore
                 lascia a lui la coda del bot, un secondo ascoltatore rinuncia
                 a partire.

  stato.lock     si tiene per il tempo di leggere, modificare e riscrivere
                 stato.json. Frazioni di secondo, mai durante un'attesa di
                 rete.

Su una serratura di file non si puo' fare troppo affidamento: vale finche' i
processi girano sulla stessa macchina, che e' il nostro caso.
"""

import fcntl
from contextlib import contextmanager
from pathlib import Path

QUI = Path(__file__).resolve().parent

ASCOLTO = QUI / "ascolto.lock"
STATO = QUI / "stato.lock"


@contextmanager
def presa(percorso, attesa=True):
    """Tiene la serratura per la durata del blocco.

    Con attesa=False non si mette in coda: se e' occupata restituisce None
    invece del file, e il chiamante decide cosa fare.
    """
    f = open(percorso, "w")
    modo = fcntl.LOCK_EX if attesa else fcntl.LOCK_EX | fcntl.LOCK_NB
    try:
        try:
            fcntl.flock(f, modo)
        except BlockingIOError:
            yield None
            return
        yield f
    finally:
        f.close()      # chiudere il file rilascia anche la serratura


def occupata(percorso):
    """Vero se qualcun altro la sta tenendo adesso. Non la trattiene."""
    with presa(percorso, attesa=False) as f:
        return f is None


def prendi_a_vita(percorso):
    """Per l'ascoltatore: prende la serratura e la tiene finche' vive.

    Restituisce il file aperto, che va tenuto in una variabile viva per tutta
    la durata del processo. None se c'e' gia' qualcun altro.
    """
    f = open(percorso, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f
