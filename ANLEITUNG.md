# F13-Liste — Dashboard: Einrichtung & Nutzung

Streamlit-Dashboard für die F13-Strategie: Es zieht die aktuellsten
13F-Portfolios der 15 Super-Investoren von SEC EDGAR und zeigt die
Schnittmengen (Konsens-Aktien) mit Filtern und Equal-Weight-Rechner.

---

## Was liegt im Ordner?

| Datei | Zweck |
|-------|-------|
| `f13_update.py` | Holt die 13F-Daten von SEC EDGAR → schreibt `f13_data.json` |
| `streamlit_app.py` | Das Online-Dashboard (Streamlit) |
| `F13-Dashboard.html` | Offline-Dashboard (Doppelklick, ohne Internet-Deploy) |
| `F13-Aktualisieren.command` | **Doppelklick = Daten neu ziehen + hochladen + Dashboard öffnen** |
| `requirements.txt` | Python-Pakete für Streamlit Cloud |
| `.streamlit/config.toml` | CI-Design (Navy/Gold) |
| `dashboard_url.txt` | (legst du an) deine Streamlit-URL — dann öffnet der Button das Online-Dashboard |

Das Repo ist lokal schon per `git` initialisiert und der erste Commit ist gemacht.
Es fehlt nur noch: **einmalig** GitHub-Repo verbinden + Streamlit Cloud koppeln.

---

## Teil A — Einmalige Einrichtung (ca. 10 Minuten)

### Schritt 1 — Altes GitHub-Token widerrufen (Sicherheit)
Beim Aufsetzen ist aufgefallen, dass in deinem **Morgenroutine**-Projekt ein
GitHub-Token offen in der Git-Adresse steht. Bitte widerrufen und neu erzeugen:

1. github.com → oben rechts Profilbild → **Settings**
2. Links unten **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. Das alte Token (beginnt mit `ghp_IxnN…`) → **Revoke**
4. **Generate new token (classic)** → Name z. B. „Mac Push", Häkchen bei **repo**,
   Ablauf „No expiration" → **Generate** → **Token kopieren** (wird nur einmal angezeigt)

> Merke dir das Token kurz — du brauchst es in Schritt 3 einmal.

### Schritt 2 — GitHub-Repo anlegen
1. github.com → **+** oben rechts → **New repository**
2. Owner: **impact-scale** · Name: **`f13-dashboard`**
3. **Private** auswählen · **kein** README/gitignore hinzufügen → **Create repository**

### Schritt 3 — Repo verbinden & hochladen
Terminal öffnen (Programme → Dienstprogramme → Terminal), diese Zeilen
**nacheinander** einfügen (Enter nach jeder Zeile):

```bash
cd "/Users/bjorn/Documents/Trading-Tools/F13 Liste"
git remote add origin https://github.com/impact-scale/f13-dashboard.git
git push -u origin main
```

Beim `push` fragt macOS nach GitHub-Login:
- **Username:** dein GitHub-Benutzername
- **Passwort:** hier das **Token** aus Schritt 1 einfügen (nicht dein GitHub-Passwort!)

macOS speichert das Token danach sicher im **Schlüsselbund** — du wirst nicht
mehr danach gefragt. (Kein Token mehr in der Git-Adresse = sicherer als vorher.)

### Schritt 4 — Streamlit Cloud koppeln
1. **share.streamlit.io** öffnen → mit **GitHub** anmelden
2. **Create app** → **Deploy a public app from GitHub** *(bzw. „from existing repo")*
3. Repository: **impact-scale/f13-dashboard** · Branch: **main** · Main file: **`streamlit_app.py`**
4. **Deploy** → nach ~2 Minuten läuft das Dashboard unter einer URL wie
   `https://f13-dashboard-xxxx.streamlit.app`

> Ist das Repo **privat**, im Streamlit-Workspace unter *Settings → Sharing* ggf.
> GitHub-Zugriff erlauben. Alternativ Repo auf **public** stellen.

### Schritt 5 — URL hinterlegen (damit der Button sie öffnet)
Die Streamlit-URL aus Schritt 4 kopieren und in eine Datei `dashboard_url.txt`
im Projektordner schreiben. Schnell per Terminal:

```bash
cd "/Users/bjorn/Documents/Trading-Tools/F13 Liste"
echo "https://DEINE-URL.streamlit.app" > dashboard_url.txt
```

Fertig. ✅

---

## Teil B — Tägliche Nutzung

**Doppelklick auf `F13-Aktualisieren.command`** — das war's. Der Ablauf:

1. holt die neuesten 13F-Daten von SEC EDGAR
2. lädt sie zu GitHub hoch
3. Streamlit Cloud aktualisiert das Dashboard automatisch (~1 Min.)
4. öffnet dein Dashboard im Browser

> **Öffnet sich beim ersten Doppelklick nur eine Textdatei?** Rechtsklick auf die
> Datei → **Öffnen** → **Öffnen** bestätigen (einmalige macOS-Sicherheitsabfrage).

Ganz **ohne Internet-Deploy** geht auch: Doppelklick genügt, es öffnet dann das
lokale `F13-Dashboard.html`.

---

## Gut zu wissen

- **Wie oft aktualisieren?** 13F-Berichte erscheinen **quartalsweise** und sind bis
  zu **45 Tage alt** (gesetzlicher Meldeverzug). Ein Abruf pro Woche reicht völlig —
  häufiger bringt keine neuen Daten. Größter Sprung: jeweils ~45 Tage nach
  Quartalsende (Mitte Februar / Mai / August / November).
- **Investoren ändern?** Die Liste der 15 Investoren steht oben in `f13_update.py`
  (Name, Firma, CIK-Nummer).
- **ETFs:** Standardmäßig ausgeblendet (Fokus auf Einzelaktien). Im
  Dashboard per Schalter „ETFs einbeziehen" zuschaltbar.
- **Keine Anlageberatung** — das Tool bildet nur öffentliche 13F-Daten ab.
