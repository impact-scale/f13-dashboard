#!/bin/bash
# ─────────────────────────────────────────────────────────
# F13-Liste — Daten aktualisieren
# Doppelklick: holt die neuesten 13F-Daten von SEC EDGAR,
# pusht sie zu GitHub (falls eingerichtet → Streamlit Cloud
# aktualisiert sich automatisch) und öffnet das Dashboard.
# ─────────────────────────────────────────────────────────
cd "$(dirname "$0")"

echo ""
echo "=== F13-Liste — Datenabruf ==="
echo "$(date '+%d.%m.%Y %H:%M')"
echo ""

# f13_update.py nutzt nur die Python-Standardbibliothek (kein venv nötig).
# Pusht automatisch zu GitHub, wenn hier ein .git-Repo eingerichtet ist.
python3 f13_update.py

echo ""
# Dashboard öffnen: bevorzugt die Streamlit-Cloud-URL (in dashboard_url.txt),
# sonst das lokale HTML-Dashboard als Offline-Fallback.
if [ -f dashboard_url.txt ]; then
  URL="$(head -n1 dashboard_url.txt | tr -d '[:space:]')"
  if [ -n "$URL" ]; then
    echo "Öffne Streamlit-Dashboard: $URL"
    open "$URL"
  else
    open "F13-Dashboard.html"
  fi
else
  echo "Öffne lokales Dashboard (F13-Dashboard.html)."
  echo "Tipp: Für das Online-Dashboard die Streamlit-URL in dashboard_url.txt eintragen."
  open "F13-Dashboard.html"
fi

echo ""
read -p "Fenster schließen zum Beenden ..."
