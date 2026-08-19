# F13-Liste Dashboard — Projektkontext (für Entwickler / KI-Assistenten)

> Dieses Dokument erklärt **Architektur, Datenfluss und alle Funktionen**, damit
> eine neue Person oder ein anderer KI-Assistent das Projekt ohne Vorwissen
> weiterentwickeln kann. Endnutzer-Einrichtung (GitHub/Streamlit koppeln) steht in
> [`ANLEITUNG.md`](ANLEITUNG.md). Fachliche Strategie-Herleitung in `F13-Liste.pdf`
> (Kapitel 5, S. 152–168) und `F13-Conviction_Weighting.pdf` (beide gitignored).

---

## 1. Was ist das?

Ein **Streamlit-Dashboard**, das die vierteljährlichen **SEC-13F-Filings** von
**42 kuratierten „Super-Investoren"** einsammelt und daraus eine **Konsensliste**
bildet: Welche Aktien tauchen bei den meisten Investoren in deren größten
Positionen auf? Diese ~15 Titel („F13-Liste") sind der Kern; darum herum gibt es
Veränderungs-Tracking, Zeitreihe, Investment-Rechner, **Rebalancing**, Struktur-
Analyse, Investoren-Details, Backtest und eine Cash-&-Flows-Auswertung.

**Grundprinzip:** 13F-Daten sind **kein Echtzeit-Signal** — sie erscheinen
quartalsweise und sind gesetzlich bis zu **45 Tage** alt. Das Tool bildet nur
öffentliche Daten ab; **keine Anlageberatung**.

- **Repo:** `impact-scale/f13-dashboard` (privat, GitHub)
- **Deployment:** Streamlit Cloud, deployt automatisch bei jedem Push auf `main`
- **Firma/Footer:** „BS IMPACT SCALE GmbH ©"
- **Git-Credential:** macOS-Schlüsselbund (`osxkeychain`), **kein** Token in der Remote-URL

---

## 2. Dateien im Überblick

| Datei | Zweck |
|-------|-------|
| `f13_update.py` | **Daten-Pipeline** (pure stdlib). Holt 13F von SEC EDGAR, aggregiert Konsens, reichert Ticker/Sektor/Kurse an → schreibt `f13_data.json` **und** `f13_data.js` |
| `streamlit_app.py` | **Das Dashboard** (~1860 Zeilen). Liest `f13_data.json`, rendert alle Tabs |
| `f13_data.json` | Generierter Daten-Snapshot (committet, damit Streamlit Cloud ihn ohne SEC-Abruf lesen kann) |
| `f13_data.js` | Gleiche Daten als JS-Variable für das Offline-HTML |
| `F13-Dashboard.html` | Offline-Fallback (Doppelklick, ohne Deploy) |
| `*_cache.json` | Immutable-Caches: `ticker_cache` (OpenFIGI), `price_cache` (aktuelle Kurse), `quarter_cache` (historische Filings — ändern sich nie), `price_history_cache` (Quartalskurse), `cash_cache` (Berkshire/Icahn Cash) |
| `.github/workflows/update.yml` | GitHub Actions: täglich 06:00 UTC `python f13_update.py` → commit → push |
| `.streamlit/config.toml` | CI-Theme (Navy/Gold) |
| `ANLEITUNG.md` | Endnutzer-Setup |
| `dashboard_url.txt` | Deployte Streamlit-URL (für den `.command`-Starter) |

**Gitignored** (nicht im Repo): `venv/`, `__pycache__/`, `*.pdf` (Quell-Bücher),
`graphify-out/` (lokale Code-Graph-Analyse), `scratchpad/`.

---

## 3. Daten-Pipeline (`f13_update.py`)

Reines Python-Standardbibliothek (kein pip nötig), damit es überall läuft. Ablauf:

1. **Filings finden:** Für jede der `INVESTORS` (Liste oben in der Datei: Name, Firma,
   **CIK**, Gruppe) die 13F-HR-Filings von SEC EDGAR laden. Zentrale Konstanten:
   - `QUARTERS = 40` — Sicherheits-Obergrenze geladener Quartale je Investor
   - `TOP_N = 15` — Länge der finalen F13-Liste
   - `STORE_N = 25` — gespeicherte Top-Positionen je Investor
2. **Aggregieren je Investor:** Positionen nach **CUSIP-6-Wurzel** bündeln, ETFs
   filterbar markieren (`isEtf`), Q/Q-Änderung je Holding berechnen (NEU/AUFGESTOCKT/
   REDUZIERT/GEHALTEN via Stückzahl, Toleranz ±2 %), plus `sold`-Liste.
3. **Konsens bilden:** `consensus(...)` zählt, in wie vielen Investoren-Top-Listen
   jede Aktie vorkommt → `ranking`. Mit `count` (aktuell), `countPrev`, `countDelta`,
   YTD-Vergleich (vs. letztes Jahresende).
4. **Anreichern:**
   - **Ticker** via OpenFIGI (`api.openfigi.com/v3/mapping`, gecacht). `TICKER_FALLBACK`
     (nach CUSIP-6) für CINS-Codes, die OpenFIGI verfehlt. `TICKER_OVERRIDE`
     `{"084670":"BRK-B"}` erzwingt BRK-B für Berkshire.
   - **Name** via SEC `company_tickers.json`, `clean_name()` säubert.
   - **Sektor/Region** aus kuratierter `SECTOR_REGION`-Map (FinViz-Taxonomie).
   - **Kurse:** Quartals-Schlusskurse (Median 13F-Value/Shares **und** Yahoo-Historie)
     + aktuelle Kurse (Yahoo Chart v8 API, gecacht in `price_cache.json`).
   - **Benchmarks:** ^GSPC (S&P 500), ^NDX (Nasdaq 100).
   - **EUR/USD:** Yahoo `EURUSD=X` → `{"rate":…, "asOf":…}` (Fallback 1.08).
   - **Cash & Flows:** siehe Abschnitt 7.
5. **Schreiben:** `data`-Dict → `f13_data.json` + `f13_data.js`.
   - **Auto-Push:** läuft nur lokal; unter GitHub Actions (`GITHUB_ACTIONS` gesetzt)
     macht der Workflow den Commit.

### `data`-Struktur (Schlüssel in `f13_data.json`)

| Key | Inhalt |
|-----|--------|
| `generatedAt` | ISO-Timestamp der Generierung |
| `topN` / `storeN` | 15 / 25 |
| `quartersLoaded` | Anzahl Quartale in `history` (aktuell **27**: 2019-12-31 … 2026-06-30) |
| `investors` | Liste der 42 Investoren mit Portfolios, Holdings, Käufen/Verkäufen |
| `ranking` | Aktuelle Konsensliste (Top 60), `f13` = Top 15 |
| `history` | **Pro Quartal** `{quarter, ranking:[…]}`. Jedes Ranking-Element: `{key, name, ticker, sector, count, price}` — `price` = Quartals-Schlusskurs |
| `prices` | `{ticker: {price, asOf}}` — **aktuelle** Kurse (USD) |
| `pricesAsOf` | Datum der aktuellen Kurse |
| `quarterPrices` | `{ticker: {quartal: kurs}}` — split-adjustierte Quartals-Schlusskurse |
| `benchmarks` | `{"S&P 500": {quarters, current}, "Nasdaq 100": …}` |
| `eurusd` | `{rate, asOf}` — z. B. `{1.1573, "2026-08-15"}` |
| `cash`, `nportCash`, `flows` | siehe Abschnitt 7 |
| `errors` | Fehler-Log des letzten Laufs |

---

## 4. Dashboard-Aufbau (`streamlit_app.py`)

- **Theme-Konstanten** oben: `MIDNIGHT`, `NAVY`, `GOLD`, `OFFWHITE`, `SLATE` etc. +
  CSS (`.callout`, `.goldbar`, Gold-Pill-Navigation via `:has(input:checked)`).
- **Navigation:** `PAGES = [...]` als `st.radio(..., horizontal=True, key="nav_page")`.
  Jeder Tab ist ein `if page == "<label>":`-Block. **Wichtig:** bewusst `st.radio`
  statt `st.tabs`, weil `st.tabs` alle Panels ins DOM legt (Render-Leak). Nur die
  gewählte Seite wird gerendert.
- **Sidebar-Filter:** Positionen/Investor, Mindest-Konsens, ETF-Toggle, Aktien-Suche,
  Investoren-Checkboxliste mit „Alle ein-/ausschalten" + Schnellwahl „★ Super-15" /
  „Top 30 Vol.".
- **Statusleiste oben:** „Investoren aktiv · Stand · EUR/USD · Quelle SEC EDGAR (13F-HR ⓘ)".
  Konvention (siehe Memory): **jeder Abschnitt zeigt Quelle + Datenstand**.

### Wichtige Helfer (oben in der Datei / vor den Tabs)

| Helfer | Zweck |
|--------|-------|
| `de_num(x, dec=2)` | Deutsche Zahlenformatierung (1.234,56). **Immer** dafür nutzen, nicht `f"{x:,.2f}"` |
| `get_eurusd()` | `@st.cache_data(ttl=3600)` Yahoo-Fallback, falls `data["eurusd"]` fehlt |
| `EURUSD`, `EURUSD_ASOF` | Modulweite Werte aus `data["eurusd"]` (Fallback `get_eurusd()`) |
| `compute_weights(method, titles)` | Equal Weight = `1/m`; Conviction = `count / Σcounts` |
| `make_donut(counter, title)` | Sektor/Region-Donuts |
| `next_13f_release(...)` | Datum der nächsten 13F-Veröffentlichung |

### Die Tabs (`PAGES`)

1. **📊 F13-Konsensliste** — KPI-Zeile + Balkendiagramm + Tabelle (Ticker, ΔQ/Q,
   Sektor), Export CSV/Excel/PDF.
2. **🔄 Veränderungen** — Konsens-Momentum (Gainer/Loser, nicht-scrollende Tabellen
   via voller Höhe) + Käufe/Verkäufe je Investor mit Filter.
3. **📈 Verlauf** — Zeitreihe der Konsens-Ränge über die Quartale.
4. **🧮 Investment-Rechner** — Kapital + Titelzahl → Verteilung nach Equal/Conviction,
   mit **Kurs** + **Anzahl Aktien**. **Währungsumschalter €/$** (`in_usd`): bei € wird
   das Volumen via `EURUSD` in $ umgerechnet, bei $ direkt verteilt; Kurse stehen
   immer in $. Export als **CSV und PDF** (`f13_to_pdf(df, meta, title=…, tag_text=…)`,
   generalisiert — Default-Titel bleibt „F13-Konsensliste").
5. **🔁 Rebalancing** — **siehe Abschnitt 5 (Kernfeature dieser Session).**
6. **🧩 Struktur** — Sektor-/Region-Donuts der F13-Liste (Klumpenrisiko).
7. **👤 Investoren-Details** — Drilldown je Investor.
8. **🆕 Neue Meldungen** — frisch eingegangene Filings.
9. **🎯 Backtest** — F13-Liste eines Quartals bis heute: Quartals-Schlusskurs vs.
   aktueller Kurs, Portfolio-Rendite (gesamt + p.a.), Vergleich S&P 500 / Nasdaq 100.
   Plausibilitätsschutz: Kursverhältnis muss in `[0.02, 50]` liegen.
10. **💰 Cash & Flows** — siehe Abschnitt 7.

Ganz unten (immer gerendert, **außerhalb** aller `if page`-Blöcke): Risikohinweis/
Haftungsausschluss + Footer. **Neue Tab-Blöcke müssen davor eingefügt werden.**

---

## 5. Rebalancing-Tab (Kernarbeit dieser Session)

**Zweck:** Der Nutzer hält die F13-Liste eines **Basisquartals** und will auf ein
neueres **Zielquartal** umschichten (quartalsweise / halbjährlich / jährlich). Der
Tab beantwortet: **Was raus? Was rein? Was in der Gewichtung ändern? Wie viel Stück?**

### Bedienelemente
- **Rebalancing-Frequenz** (Quartalsweise/Halbjährlich/Jährlich) → `FREQ_GAP` = 1/2/4.
  `on_change`-Callback `_apply_freq()` setzt `reb_target = base + gap`.
- **Basisquartal** + **Zielquartal** (aus `history`-Quartalen, frei wählbar; Guard:
  Ziel muss nach Basis liegen).
- **Investitionsbetrag Basisquartal (€)** (`invest0`) — der zum Basisquartal
  investierte Betrag; verteilt sich gemäß Gewichtung auf die Basisliste und legt die
  Stückzahlen vor.
- **Zielbetrag = Basisbetrag** (Checkbox, default an) + **Investitionsbetrag
  Zielquartal (€)** (`invest_target`) — das **absolute** Depotvolumen nach dem
  Rebalancing. Bei aktiver Checkbox = Basisbetrag; sonst frei editierbar (default =
  Basisbetrag). `target_total = invest_target`; die implizite Auf-/Abstockung
  `aufstock = target_total − depot_now` wird in der Zusammenfassung als Euro **und %
  des heutigen Depotwerts** ausgewiesen (so lässt sich z. B. „−50 %" exakt treffen:
  Zielbetrag = halber heutiger Depotwert). Summe aller Δ = `aufstock`.
- **Anzahl Titel (Top N)**.
- **Methode getrennt je Quartal:** „Methode Basisquartal" und „Methode neues Quartal",
  jeweils Equal Weight **oder** Conviction. (Erlaubt z. B. Bestand Equal → Ziel Conviction.)

### Editierbarer Basisbestand (`st.data_editor`, key `reb_editor`)
Tabelle je Basistitel mit **Kaufkurs ($)** und **Stück**, **beide vorbelegt und
überschreibbar**:
- Kaufkurs vorbelegt = **Schlusskurs des Basisquartals** (`entry["price"]`).
- Stück vorbelegt = `Investitionsbetrag × Gewicht × EURUSD ÷ Kaufkurs`.
- **Die Stück-Spalte ist maßgeblich** für den heutigen Wert (nicht der Kaufkurs).
  Rationale des Nutzers: „Wer zu einem anderen Kurs/Menge gekauft hat, überschreibt
  es selbst." Bekannte Grenze: Ändert man nur den Kaufkurs, rechnet sich Stück
  **nicht** automatisch nach (Streamlit-Editor-Limit) — Stück ggf. selbst anpassen.

### Rechenmodell (drift-bewusst — vom Nutzer so gewünscht)
1. **Heutiger Wert je Position** = `Stück × aktueller Kurs ÷ EURUSD` (Kursdrift seit
   Kauf). Basis: Einstandskurs des Basisquartals → aktueller Kurs (`data["prices"]`).
2. **Heutiger Depotwert** `depot_now` = Σ der bewertbaren Positionswerte;
   **Zielvolumen** `target_total = invest_target` (absolut eingegeben).
3. **Ziel-Allokation** = `target_total × Ziel-Gewicht` je Titel.
4. **Δ Betrag** = Ziel − heutiger Wert; **Δ Stück** = `Δ Betrag × EURUSD ÷ aktueller Kurs`.
   (+ = zukaufen, − = verkaufen.)

**Wirkung:** Auch **gehaltene** Titel bekommen echte Ausgleichs-Trades (Gewinner
reduzieren, Nachzügler aufstocken) — nicht nur Ab-/Zugänge. Test 2025-06-30 →
2026-06-30, Equal→Equal: 4 raus, 4 rein, **9 umgewichtet**; Depot 15.000 € →
17.807 € (+18,7 %).

### Ergebnistabelle (nach raus → halten → rein sortiert)
`Aktion` (🔴 Verkaufen / 🟢 Kaufen / 🔼 Aufstocken / 🔽 Reduzieren / ▪ Halten),
`Ticker`, `Aktie`, `Kurs damals`, `Kurs heute`, `Stück alt`, `Gewicht alt`
(gedriftetes Ist-Gewicht), `Gewicht neu` (Ziel), `Wert heute (€)`, `Ziel (€)`,
`Δ Betrag (€)`, `Δ Stück`. CSV-Export. Titel ohne verwertbaren aktuellen Kurs (z. B.
Flutter, kein US-Ticker) werden nicht in `depot_now` gewertet und per ⚠-Zeile genannt.

---

## 6. Weitere Features dieser Session (Kontext)

- **Momentum-Tabellen** (Veränderungen) nutzen volle Höhe (`38 + 35*n`), damit sie
  bei mehr Daten **nicht scrollen**.
- **Investment-Rechner** zeigt zusätzlich **Kurs** + **Anzahl Aktien** (€ → $ via `EURUSD`).
- **EUR/USD** steht in der Statusleiste (alle Tabs) und wird täglich in der Pipeline
  aktualisiert (`f13_update.py` → `data["eurusd"]`).
- **WhaleWisdom WhaleIndex 20** wurde extern (nicht im Repo) mit der F13-Liste
  abgeglichen (10 Überschneidungen). Reine Analyse, kein Code — falls Integration
  gewünscht, wäre eine Vergleichs-Spalte/Sektion der nächste Schritt.

---

## 7. Cash & Flows (Vorgeschichte, Stufen 1+2 live)

13F enthält **kein** Cash (nur US-Long-Equities). Umgesetzt:
- **Echtes Cash:** Berkshire (XBRL + T-Bills aus 10-Q/10-K, `cash_cache.json`) und
  Icahn/IEP (Issuer-CIK 0000813762).
- **N-PORT-Cash** für 9 Fonds (`NPORT_SOURCES`): Cash = `cshNotRptdInCorD/netAssets`
  **plus** T-Bill-/STIV-Holdings (Fairholme parkt Liquidität in T-Bills → reines
  `cshNotRptdInCorD` wäre falsch).
- **Proxy-Flows** für alle 42: Δ Portfoliowert minus Kurseffekt (aus unveränderten
  Positionen geschätzt).
- **Stufe 3 (nicht gebaut):** Gates-Trust 990-PF, Form ADV Item 5.K, Pershing/Third
  Point NAV.

Details siehe Auto-Memory `project_f13_liste.md`.

---

## 8. Konventionen & Stolperfallen (wichtig für Weiterarbeit)

- **Nach jeder verifizierten Änderung sofort committen + pushen** (Streamlit Cloud
  deployt automatisch). Bei Auto-Update-Konflikten:
  `git merge origin/main --no-edit -X ours` (lokale Struktur-Felder behalten).
- **Push-Commits** enden mit `Co-Authored-By: Claude …`.
- **Lokal testen:** `./venv/bin/streamlit run streamlit_app.py --server.port 8601`
  (venv liegt im Projekt). Syntax-Check: `python3 -m py_compile streamlit_app.py`.
  DataFrames rendern auf **Canvas** (glide-data-grid) → DOM-Queries greifen nicht,
  zur Verifikation **Screenshots** nutzen.
- **Neue Tabs:** Label in `PAGES` **und** `if page == "…":`-Block **vor** dem Footer
  (Risikohinweis) einfügen — der Footer steht außerhalb aller Blöcke und rendert immer.
- **Zahlen:** immer `de_num()`; **kein** `.replace(",", ".")` mehr auf de_num-Ausgaben
  (verfälscht deutsche Dezimalkommas).
- **Immutable-Caches** (`quarter_cache.json` etc.) nie manuell bearbeiten — historische
  Filings ändern sich nicht; die Pipeline pflegt sie.
- **graphify:** Repo hat einen Code-Graph (`graphify-out/`, gitignored). Hooks weisen
  darauf hin. Nach Codeänderungen `graphify update .` (AST-only, keine API-Kosten).
- **Kein Buch-Bezug** in nutzerseitigen Texten (auf Wunsch entfernt).

---

## 9. Schnellstart für einen neuen Assistenten

1. `f13_data.json` lesen → Datenmodell verstehen (Abschnitt 3).
2. `streamlit_app.py`: `PAGES` + Helfer (`de_num`, `compute_weights`, `EURUSD`) →
   dann den relevanten `if page ==`-Block.
3. Änderung machen → `py_compile` → lokal in Streamlit prüfen (Screenshots) →
   committen + pushen.
4. Pipeline-Änderungen in `f13_update.py`; danach `python3 f13_update.py` (erster
   voller Lauf ~5–8 Min., danach gecacht).
