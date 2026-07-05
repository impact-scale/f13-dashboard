#!/usr/bin/env python3
"""
F13-Liste — Automatischer Datenabruf von SEC EDGAR
===================================================
Holt für die 15 Super-Investoren das aktuellste UND das vorherige 13F-HR-Filing,
ermittelt die Top-Positionen pro Investor, erkennt Veränderungen zum Vorquartal
(neu/aufgestockt/reduziert/verkauft), reichert um Ticker (OpenFIGI) sowie
Sektor/Region an und berechnet die Schnittmengen (F13-Liste).

Ausgabe:
  - f13_data.json  (Rohdaten)
  - f13_data.js    (window.F13_DATA für das HTML-Dashboard, funktioniert via file://)

Nur Python-Standardbibliothek, kein venv nötig.
"""

import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TICKER_CACHE = BASE_DIR / "ticker_cache.json"

# SEC verlangt einen identifizierenden User-Agent
USER_AGENT = "F13-Dashboard bjoern@impact-scale.com"
REQUEST_DELAY = 0.15  # SEC-Limit: max. 10 Requests/Sekunde

# Liste der Super-Investoren (Name, Firma, CIK-Nummer), Stand 2026
INVESTORS = [
    ("Warren Buffett",        "Berkshire Hathaway Inc",                   "0001067983"),
    ("Ray Dalio",             "Bridgewater Associates, LP",               "0001350694"),
    ("Prem Watsa",            "Fairfax Financial Holdings LTD",           "0000915191"),
    ("George Soros",          "Soros Fund Management LLC",                "0001029160"),
    ("Ron Baron",             "Bamco Inc",                                "0001017918"),
    ("Daniel Loeb",           "Third Point LLC",                          "0001040273"),
    ("Bill Ackman",           "Pershing Square Capital Management, L.P.", "0001336528"),
    ("Mohnish Pabrai",        "Dalal Street, LLC",                        "0001549575"),
    ("Carl Icahn",            "Icahn Carl C",                             "0000921669"),
    ("Stanley Druckenmiller", "Duquesne Family Office LLC",               "0001536411"),
    ("Joel Greenblatt",       "Gotham Asset Management, LLC",             "0001510387"),
    ("Ken Fisher",            "Fisher Asset Management, LLC",             "0000850529"),
    ("Jeremy Grantham",       "Grantham, Mayo, Van Otterloo & Co. LLC",   "0001352662"),
    ("Steven Cohen",          "Point72 Asset Management, L.P.",           "0001603466"),
    ("Howard Marks",          "Oaktree Capital Management LP",            "0000949509"),
]

TOP_N = 15       # Länge der finalen F13-Liste
STORE_N = 25     # gespeicherte Top-Positionen pro Investor (für dynamische Filter)

# ETFs/Indexfonds zählen nicht als Einzelunternehmen und werden aus den
# Top-Listen gefiltert (die Strategie zielt auf einzelne Aktien).
ETF_PATTERNS = re.compile(
    r"\bISHARES\b|\bSPDR\b|\bVANGUARD\b|\bPROSHARES\b|\bINVESCO QQQ\b"
    r"|\bSELECT SECTOR\b|INDEX FUND|\bETF\b|\bTRUST\b.*\bETF\b",
    re.IGNORECASE,
)

# Kuratierte Sektor-/Regions-Zuordnung (Ticker → Sektor, Region).
# Deckt die gängige F13-Universe der Large Caps ab; Unbekanntes → ("Sonstige","–").
SECTOR_REGION = {
    "GOOGL": ("Technologie", "USA"), "GOOG": ("Technologie", "USA"),
    "AMZN": ("Consumer Discretionary", "USA"), "AAPL": ("Technologie", "USA"),
    "MSFT": ("Technologie", "USA"), "META": ("Technologie", "USA"),
    "NVDA": ("Technologie", "USA"), "AVGO": ("Technologie", "USA"),
    "TSM": ("Technologie", "Taiwan"), "ASML": ("Technologie", "Niederlande"),
    "LRCX": ("Technologie", "USA"), "AMAT": ("Technologie", "USA"),
    "KLAC": ("Technologie", "USA"), "MU": ("Technologie", "USA"),
    "INTC": ("Technologie", "USA"), "AMD": ("Technologie", "USA"),
    "QCOM": ("Technologie", "USA"), "TXN": ("Technologie", "USA"),
    "ADBE": ("Technologie", "USA"), "CRM": ("Technologie", "USA"),
    "ORCL": ("Technologie", "USA"), "CSCO": ("Technologie", "USA"),
    "PLTR": ("Technologie", "USA"), "NOW": ("Technologie", "USA"),
    "TSLA": ("Consumer Discretionary", "USA"), "HD": ("Consumer Discretionary", "USA"),
    "MCD": ("Consumer Discretionary", "USA"), "NKE": ("Consumer Discretionary", "USA"),
    "SBUX": ("Consumer Discretionary", "USA"), "BKNG": ("Consumer Discretionary", "USA"),
    "LOW": ("Consumer Discretionary", "USA"), "TJX": ("Consumer Discretionary", "USA"),
    "DIS": ("Communication Services", "USA"), "NFLX": ("Communication Services", "USA"),
    "CMCSA": ("Communication Services", "USA"), "T": ("Communication Services", "USA"),
    "VZ": ("Communication Services", "USA"), "TMUS": ("Communication Services", "USA"),
    "TDS": ("Communication Services", "USA"),
    "KO": ("Consumer Staples", "USA"), "PEP": ("Consumer Staples", "USA"),
    "PG": ("Consumer Staples", "USA"), "COST": ("Consumer Staples", "USA"),
    "WMT": ("Consumer Staples", "USA"), "KHC": ("Consumer Staples", "USA"),
    "MDLZ": ("Consumer Staples", "USA"), "KR": ("Consumer Staples", "USA"),
    "PM": ("Consumer Staples", "USA"), "CL": ("Consumer Staples", "USA"),
    "NSRGY": ("Consumer Staples", "Schweiz"), "MO": ("Consumer Staples", "USA"),
    "JPM": ("Finanzen", "USA"), "BAC": ("Finanzen", "USA"), "WFC": ("Finanzen", "USA"),
    "C": ("Finanzen", "USA"), "GS": ("Finanzen", "USA"), "MS": ("Finanzen", "USA"),
    "AXP": ("Finanzen", "USA"), "V": ("Finanzen", "USA"), "MA": ("Finanzen", "USA"),
    "BRK.A": ("Finanzen", "USA"), "BRK.B": ("Finanzen", "USA"),
    "BLK": ("Finanzen", "USA"), "SCHW": ("Finanzen", "USA"), "SPGI": ("Finanzen", "USA"),
    "MCO": ("Finanzen", "USA"), "COF": ("Finanzen", "USA"), "PYPL": ("Finanzen", "USA"),
    "PGR": ("Finanzen", "USA"), "CB": ("Finanzen", "USA"), "FFH.TO": ("Finanzen", "Kanada"),
    "UNH": ("Gesundheit", "USA"), "JNJ": ("Gesundheit", "USA"), "LLY": ("Gesundheit", "USA"),
    "PFE": ("Gesundheit", "USA"), "MRK": ("Gesundheit", "USA"), "ABBV": ("Gesundheit", "USA"),
    "TMO": ("Gesundheit", "USA"), "ABT": ("Gesundheit", "USA"), "DHR": ("Gesundheit", "USA"),
    "AMGN": ("Gesundheit", "USA"), "ISRG": ("Gesundheit", "USA"), "DVA": ("Gesundheit", "USA"),
    "NVO": ("Gesundheit", "Dänemark"), "HCA": ("Gesundheit", "USA"),
    "XOM": ("Energie", "USA"), "CVX": ("Energie", "USA"), "COP": ("Energie", "USA"),
    "OXY": ("Energie", "USA"), "SLB": ("Energie", "USA"), "EOG": ("Energie", "USA"),
    "CAT": ("Industrie", "USA"), "BA": ("Industrie", "USA"), "HON": ("Industrie", "USA"),
    "GE": ("Industrie", "USA"), "UPS": ("Industrie", "USA"), "RTX": ("Industrie", "USA"),
    "DE": ("Industrie", "USA"), "LMT": ("Industrie", "USA"), "UNP": ("Industrie", "USA"),
    "NSC": ("Industrie", "USA"), "MMM": ("Industrie", "USA"),
    "LIN": ("Materialien", "USA"), "SHW": ("Materialien", "USA"), "APD": ("Materialien", "USA"),
    "NEE": ("Versorger", "USA"), "DUK": ("Versorger", "USA"), "SO": ("Versorger", "USA"),
    "AMT": ("Immobilien", "USA"), "PLD": ("Immobilien", "USA"),
    "LVMUY": ("Consumer Discretionary", "Frankreich"),
}


# Ticker-Fallback für CUSIP-Stämme (erste 6 Stellen), die OpenFIGI nicht kennt
# (v.a. ausländische CINS-Codes). key = cusip[:6] → Ticker.
TICKER_FALLBACK = {
    "N07059": "ASML",   # ASML Holding NV (NY Registry)
    "H1467J": "CB",     # Chubb Ltd
    "G5480U": "LIN",    # Linde PLC
    "G54950": "LIN",    # Linde PLC (alt. CINS)
    "G25508": "CRH",    # CRH PLC
    "L8681T": "SPOT",   # Spotify Technology SA
}


def sector_region(ticker):
    if ticker and ticker.upper() in SECTOR_REGION:
        return SECTOR_REGION[ticker.upper()]
    return ("Sonstige", "–")


def is_etf(name):
    return bool(ETF_PATTERNS.search(name))


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    time.sleep(REQUEST_DELAY)
    return data


def http_get_json(url):
    return json.loads(http_get(url).decode("utf-8"))


def localname(tag):
    return tag.rsplit("}", 1)[-1]


def find_13f_filings(cik):
    """Alle 13F-HR(/A)-Filings, neuestes Quartal zuerst, je Quartal das jüngste Doc."""
    subs = http_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    recent = subs["filings"]["recent"]
    by_period = {}
    for form, fdate, rdate, acc in zip(
        recent["form"], recent["filingDate"],
        recent["reportDate"], recent["accessionNumber"],
    ):
        if form not in ("13F-HR", "13F-HR/A"):
            continue
        prev = by_period.get(rdate)
        cand = {"form": form, "filingDate": fdate, "reportDate": rdate, "accession": acc}
        # Bei mehreren Docs pro Quartal (z.B. Amendment) gewinnt das jüngste
        if prev is None or fdate > prev["filingDate"]:
            by_period[rdate] = cand
    return [by_period[p] for p in sorted(by_period, reverse=True)]


def fetch_infotable(cik, accession):
    """Lädt die Information Table (XML) eines Filings und parst die Positionen."""
    acc_nodash = accession.replace("-", "")
    cik_int = int(cik)
    index = http_get_json(
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/index.json"
    )
    xml_files = [
        f["name"] for f in index["directory"]["item"]
        if f["name"].lower().endswith(".xml")
        and "primary_doc" not in f["name"].lower()
    ]
    xml_files.sort(key=lambda n: 0 if "infotable" in n.lower() else 1)
    for name in xml_files:
        raw = http_get(
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{name}"
        )
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue
        if localname(root.tag) != "informationTable":
            continue
        positions = []
        for entry in root:
            if localname(entry.tag) != "infoTable":
                continue
            row = {}
            for child in entry.iter():
                row[localname(child.tag)] = (child.text or "").strip()
            put_call = row.get("putCall", "")
            shr_type = row.get("sshPrnamtType", "SH")
            if put_call or shr_type != "SH":
                continue  # nur Long-Aktienpositionen (keine Optionen/Anleihen)
            try:
                value = float(row.get("value", "0") or 0)
            except ValueError:
                value = 0.0
            try:
                shares = float(row.get("sshPrnamt", "0") or 0)
            except ValueError:
                shares = 0.0
            cusip = row.get("cusip", "").upper()
            if not cusip or value <= 0:
                continue
            positions.append({
                "name": row.get("nameOfIssuer", "?"),
                "cusip": cusip,
                "value": value,
                "shares": shares,
            })
        return positions
    return None


def aggregate_investor(positions):
    """Emittenten zusammenfassen (CUSIP-Stamm, erste 6 Stellen)."""
    by_issuer = {}
    for p in positions:
        key = p["cusip"][:6]
        slot = by_issuer.setdefault(key, {
            "names": Counter(), "value": 0.0, "shares": 0.0, "cusips": Counter(),
        })
        slot["names"][p["name"]] += 1
        slot["value"] += p["value"]
        slot["shares"] += p["shares"]
        slot["cusips"][p["cusip"]] += 1
    merged = [{
        "key": key,
        "name": slot["names"].most_common(1)[0][0],
        "value": slot["value"],
        "shares": slot["shares"],
        "cusip": slot["cusips"].most_common(1)[0][0],
    } for key, slot in by_issuer.items()]
    merged.sort(key=lambda x: -x["value"])
    return merged


def norm_scale(total):
    # Ältere Filings (vor 2023) melden in Tausend USD — heuristisch normalisieren
    return 1000.0 if total < 1e7 else 1.0


def pretty_name(raw):
    """Filing-Namen (oft GROSSBUCHSTABEN) lesbar machen."""
    keep_upper = {"LLC", "LP", "L.P.", "INC", "CORP", "CO", "PLC", "SA", "NV",
                  "ADR", "SE", "AG", "ETF", "II", "III", "IV", "US", "USA",
                  "DE", "NEW", "CL", "A", "B", "C", "&"}
    out = []
    for w in raw.split():
        if w.upper() in keep_upper and len(w) <= 4:
            out.append(w.upper() if w.upper() not in {"NEW", "CL"} else w.capitalize())
        elif re.fullmatch(r"[A-Z0-9&.\-/']+", w) and len(w) > 1:
            out.append(w.capitalize())
        else:
            out.append(w)
    return " ".join(out)


# ─── Ticker-Auflösung via OpenFIGI (mit lokalem Cache) ────────────────────────

def load_cache():
    if TICKER_CACHE.exists():
        try:
            return json.loads(TICKER_CACHE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def resolve_tickers(cusips):
    """cusip → ticker. Nutzt Cache; fehlende via OpenFIGI (10er-Batches)."""
    cache = load_cache()
    missing = sorted({c for c in cusips if c and c not in cache})
    print(f"  Ticker: {len(cusips)} CUSIPs, {len(missing)} neu via OpenFIGI ...")
    for i in range(0, len(missing), 10):
        batch = missing[i:i + 10]
        # exchCode "US" → US-Composite-Ticker (13F listet nur US-gelistete Papiere)
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"}
                           for c in batch]).encode()
        req = urllib.request.Request(
            "https://api.openfigi.com/v3/mapping", data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            for c, r in zip(batch, resp):
                d = r.get("data") or []
                # "No identifier found" → dauerhaft "" cachen; echte Treffer → Ticker
                cache[c] = (d[0].get("ticker") if d else None) or ""
        except Exception as e:
            # Transienter Fehler (z.B. Ratelimit) → NICHT cachen, nächster Lauf holt nach
            print(f"    OpenFIGI-Batch fehlgeschlagen ({e}) — Retry beim nächsten Lauf.")
        time.sleep(3.0)  # unter 25 Anfragen/Minute bleiben (ohne API-Key)
    TICKER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), "utf-8")
    return cache


# ─── Hauptlauf ────────────────────────────────────────────────────────────────

def build_holdings(merged, total, ticker_map, prev_by_key=None):
    """Baut angereicherte Positionsliste; erkennt Veränderung ggü. prev_by_key."""
    scale = norm_scale(total)
    out = []
    for m in merged:
        ticker = ticker_map.get(m["cusip"], "") or TICKER_FALLBACK.get(m["key"], "")
        sector, region = sector_region(ticker)
        pos = {
            "key": m["key"],
            "name": pretty_name(m["name"]),
            "ticker": ticker,
            "sector": sector,
            "region": region,
            "value": m["value"] * scale,
            "shares": m["shares"],
            "weight": round(100.0 * m["value"] / total, 2) if total else 0.0,
            "isEtf": is_etf(m["name"]),
        }
        if prev_by_key is not None:
            prev = prev_by_key.get(m["key"])
            if prev is None:
                pos["change"] = "NEU"
                pos["prevShares"] = 0.0
            else:
                ps = prev["shares"]
                pos["prevShares"] = ps
                if ps <= 0:
                    pos["change"] = "NEU"
                elif m["shares"] > ps * 1.02:
                    pos["change"] = "AUFGESTOCKT"
                elif m["shares"] < ps * 0.98:
                    pos["change"] = "REDUZIERT"
                else:
                    pos["change"] = "GEHALTEN"
        out.append(pos)
    return out


def main():
    print("F13-Liste — Datenabruf von SEC EDGAR")
    print("=" * 50)
    investors_raw = []
    errors = []

    for person, firm, cik in INVESTORS:
        label = f"{person} ({firm})"
        try:
            filings = find_13f_filings(cik)
            if not filings:
                raise RuntimeError("kein 13F-HR-Filing gefunden")
            cur = filings[0]
            prev = filings[1] if len(filings) > 1 else None

            cur_pos = fetch_infotable(cik, cur["accession"])
            if cur_pos is None:
                raise RuntimeError("Information Table nicht gefunden")
            cur_merged = aggregate_investor(cur_pos)

            prev_merged, prev_report = [], None
            if prev:
                pp = fetch_infotable(cik, prev["accession"])
                if pp:
                    prev_merged = aggregate_investor(pp)
                    prev_report = prev["reportDate"]

            investors_raw.append({
                "person": person, "firm": firm, "cik": cik,
                "form": cur["form"], "filingDate": cur["filingDate"],
                "reportDate": cur["reportDate"], "accession": cur["accession"],
                "cur_merged": cur_merged, "prev_merged": prev_merged,
                "prevReportDate": prev_report,
            })
            print(f"  OK   {label}: {len(cur_merged)} Pos. (Q {cur['reportDate']})"
                  f"{' · Vorquartal ' + prev_report if prev_report else ' · kein Vorquartal'}")
        except Exception as exc:
            errors.append({"investor": label, "error": str(exc)})
            print(f"  FEHLER {label}: {exc}", file=sys.stderr)

    # Alle CUSIPs (aktuell + Vorquartal, Top STORE_N) für Ticker-Auflösung sammeln
    all_cusips = set()
    for inv in investors_raw:
        for m in inv["cur_merged"][:STORE_N]:
            all_cusips.add(m["cusip"])
        for m in inv["prev_merged"][:STORE_N]:
            all_cusips.add(m["cusip"])
    ticker_map = resolve_tickers(all_cusips)

    # Investoren-Ausgabe mit Anreicherung + Veränderungen aufbauen
    investors_out = []
    for inv in investors_raw:
        cur_merged, prev_merged = inv["cur_merged"], inv["prev_merged"]
        total = sum(m["value"] for m in cur_merged)
        prev_by_key = {m["key"]: m for m in prev_merged}
        cur_keys = {m["key"] for m in cur_merged}

        holdings = build_holdings(cur_merged[:STORE_N], total, ticker_map, prev_by_key)
        prev_total = sum(m["value"] for m in prev_merged)
        prev_holdings = build_holdings(prev_merged[:STORE_N], prev_total, ticker_map)

        # Komplett verkauft: im Vorquartal in Top STORE_N, jetzt gar nicht mehr gehalten
        sold = []
        for ph in prev_holdings:
            if ph["key"] not in cur_keys:
                sold.append({
                    "key": ph["key"], "name": ph["name"], "ticker": ph["ticker"],
                    "sector": ph["sector"], "region": ph["region"],
                    "prevValue": ph["value"], "prevWeight": ph["weight"],
                })

        stock_top = [h for h in holdings if not h["isEtf"]][:TOP_N]
        investors_out.append({
            "person": inv["person"], "firm": inv["firm"], "cik": inv["cik"],
            "form": inv["form"], "filingDate": inv["filingDate"],
            "accession": inv["accession"],
            "reportDate": inv["reportDate"], "prevReportDate": inv["prevReportDate"],
            "portfolioValue": total * norm_scale(total),
            "positionsCount": len(cur_merged),
            "top": stock_top,
            "holdings": holdings,
            "prevHoldings": prev_holdings,
            "sold": sold,
        })

    # Schnittmengen (aktuelles Quartal, alle Investoren) — für HTML-Dashboard
    ranking = consensus_ranking(investors_out, "holdings", TOP_N)
    ranking_prev = {r["key"]: r["count"] for r in
                    consensus_ranking(investors_out, "prevHoldings", TOP_N)}
    for r in ranking:
        r["countPrev"] = ranking_prev.get(r["key"], 0)
        r["countDelta"] = r["count"] - r["countPrev"]

    data = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "topN": TOP_N,
        "storeN": STORE_N,
        "investors": investors_out,
        "ranking": ranking[:50],
        "f13": ranking[:TOP_N],
        "errors": errors,
    }

    (BASE_DIR / "f13_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE_DIR / "f13_data.js").write_text(
        "window.F13_DATA = " + json.dumps(data, ensure_ascii=False) + ";",
        encoding="utf-8")

    print("=" * 50)
    print(f"F13-Top-{TOP_N} (Konsens · Δ ggü. Vorquartal):")
    for i, r in enumerate(data["f13"], 1):
        d = r["countDelta"]
        arrow = f"(+{d})" if d > 0 else (f"({d})" if d < 0 else "(=)")
        tk = f"[{r['ticker']}]" if r.get("ticker") else ""
        print(f"  {i:2d}. {r['name']:<34s}{tk:<9s} {r['count']}/{len(investors_out)} {arrow}")
    if errors:
        print(f"\nHinweis: {len(errors)} Investor(en) mit Fehlern — siehe oben.")
    print("\nGespeichert: f13_data.json + f13_data.js")

    if "--push" in sys.argv or (BASE_DIR / ".git").exists():
        git_push(BASE_DIR)


def consensus_ranking(investors_out, field, top_n):
    """Zählt, in wie vielen Investoren-Top-N (Einzelaktien) jede Aktie vorkommt."""
    overlap = {}
    for inv in investors_out:
        picks = [h for h in inv.get(field, []) if not h["isEtf"]][:top_n]
        for pos in picks:
            slot = overlap.setdefault(pos["key"], {
                "names": Counter(), "tickers": Counter(),
                "sector": pos.get("sector", "Sonstige"),
                "region": pos.get("region", "–"),
                "investors": [], "combinedValue": 0.0,
            })
            slot["names"][pos["name"]] += 1
            if pos.get("ticker"):
                slot["tickers"][pos["ticker"]] += 1
            slot["investors"].append({
                "person": inv["person"], "weight": pos["weight"], "value": pos["value"],
                "change": pos.get("change", ""),
            })
            slot["combinedValue"] += pos["value"]
    ranking = [{
        "key": key,
        "name": slot["names"].most_common(1)[0][0],
        "ticker": (slot["tickers"].most_common(1)[0][0] if slot["tickers"] else ""),
        "sector": slot["sector"], "region": slot["region"],
        "count": len(slot["investors"]),
        "investors": sorted(slot["investors"], key=lambda x: -x["value"]),
        "combinedValue": slot["combinedValue"],
    } for key, slot in overlap.items()]
    ranking.sort(key=lambda x: (-x["count"], -x["combinedValue"]))
    return ranking


def git_push(repo_dir):
    """Committet Daten + Ticker-Cache und pusht zu GitHub. Läuft still ohne Repo."""
    import subprocess
    git = ["git", "-C", str(repo_dir)]
    try:
        if subprocess.run(git + ["rev-parse", "--git-dir"],
                          capture_output=True, timeout=5).returncode != 0:
            print("Git-Push übersprungen (kein Repo eingerichtet).")
            return
        subprocess.run(git + ["add", "f13_data.json", "f13_data.js", "ticker_cache.json"],
                       timeout=10, check=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(git + ["commit", "-m", f"F13 Update {stamp}"],
                       capture_output=True, timeout=10)
        subprocess.run(git + ["fetch", "origin"], capture_output=True, timeout=30)
        subprocess.run(git + ["merge", "origin/main", "--no-edit", "-X", "ours"],
                       capture_output=True, timeout=30)
        result = subprocess.run(git + ["push"], capture_output=True,
                                text=True, timeout=30)
        if result.returncode == 0:
            print("GitHub-Push erfolgreich — Streamlit Cloud aktualisiert sich in ~1 Min.")
        else:
            print(f"GitHub-Push fehlgeschlagen:\n{result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        print("Git-Push: Timeout — beim nächsten Lauf erneut versuchen.")
    except Exception as e:
        print(f"Git-Push: {e}")


if __name__ == "__main__":
    main()
