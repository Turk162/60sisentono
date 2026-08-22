#!/bin/bash
# Un giro di sorveglianza del GP d'Italia 2027.
#
# Lanciato da cron ogni ora: esce subito se non e' una delle ore italiane
# previste. Il cron di Debian non sa programmare su un fuso diverso dal
# proprio (vedi man 5 crontab, LIMITATIONS), quindi l'ora la controlliamo
# qui: cosi' funziona anche quando cambia l'ora legale.
#
#   giro.sh           lanciato da cron, rispetta gli orari
#   giro.sh --adesso  esegue subito, qualunque ora sia

set -uo pipefail

# Sovrascrivibile solo per poterla collaudare fuori orario.
ORE_ITALIANE="${ORE_ITALIANE:-07 13 18}"

QUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$QUI")"
LOG="$QUI/giro.log"

if [ "${1:-}" != "--adesso" ]; then
  ora=$(TZ=Europe/Rome date +%H)
  case " $ORE_ITALIANE " in
    *" $ora "*) ;;
    *) exit 0 ;;
  esac
fi

# Il log non deve crescere all'infinito: sopra il mezzo mega tiene la coda.
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 524288 ]; then
  tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

avvisa() {   # manda un allarme a Guido senza far uscire segreti nel log
  python3 -c "
import sys; sys.path.insert(0, '$QUI')
import notifiche
try:
    notifiche.solo_a_me('''$1''')
except Exception as e:
    print('allarme non consegnato:', e)
"
}

{
  echo "───── $(TZ=Europe/Rome date '+%Y-%m-%d %H:%M:%S %Z')"

  python3 "$QUI/controllore.py"
  esito=$?
  [ $esito -ne 0 ] && echo "controllore uscito con codice $esito"

  # Se lo stato pubblico e' cambiato va messo in linea, altrimenti la web
  # app resta indietro rispetto ai messaggi Telegram.
  cd "$REPO" || { echo "non entro in $REPO"; exit 1; }

  if ! git diff --quiet -- stato_gara.json 2>/dev/null; then
    echo "stato_gara.json cambiato: lo pubblico"
    if git add stato_gara.json \
       && git commit -q -m "Stato della gara aggiornato dalla sentinella" \
       && git push -q origin HEAD 2>&1; then
      echo "pubblicato su GitHub Pages"
    else
      echo "PUBBLICAZIONE FALLITA"
      avvisa "⚠️ La sentinella ha aggiornato stato_gara.json ma non è riuscita a pubblicarlo su GitHub Pages. I messaggi Telegram sono partiti, la web app è rimasta indietro. Serve un push a mano da /mnt/dev/regalo_rino."
    fi
  fi
} >> "$LOG" 2>&1
