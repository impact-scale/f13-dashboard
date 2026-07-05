#!/usr/bin/env python3
"""
F13-Liste — Automatischer Datenabruf von SEC EDGAR
===================================================
Holt für die 15 Super-Investoren das jeweils aktuellste 13F-HR-Filing,
ermittelt die Top-15-Positionen pro Investor und berechnet die
Schnittmengen (F13-Top-15-Liste).

Ausgabe:
  - f13_data.json  (Rohdaten)
  - f13_data.js    (window.F13_DATA für das Dashboard, funktioniert via file://)

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

TOP_N = 15  # Top-Positionen pro Investor und Länge der finalen Liste

# ETFs/Indexfonds zählen nicht als Einzelunternehmen und werden aus den
# Top-Listen gefiltert (die Strategie zielt auf einzelne Aktien).
ETF_PATTERNS = re.compile(
    r"\bISHARES\b|\bSPDR\b|\bVANGUARD\b|\bPROSHARES\b|\bINVESCO QQQ\b"
    r"|\bSELECT SECTOR\b|INDEX FUND|\bETF\b|\bTRUST\b.*\bETF\b",
    re.IGNORECASE,
)


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


def find_latest_13f(cik):
    """Neuestes 13F-HR(/A)-Filing: (form, filingDate, reportDate, accessionNumber)."""
    subs = http_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    recent = subs["filings"]["recent"]
    candidates = []
    for form, fdate, rdate, acc in zip(
        recent["form"], recent["filingDate"],
        recent["reportDate"], recent["accessionNumber"],
    ):
        if form in ("13F-HR", "13F-HR/A"):
            candidates.append({"form": form, "filingDate": fdate,
                               "reportDate": rdate, "accession": acc})
    if not candidates:
        return None
    latest_period = max(c["reportDate"] for c in candidates)
    same_period = [c for c in candidates if c["reportDate"] == latest_period]
    # Bei Amendments (13F-HR/A) gewinnt das zuletzt eingereichte Dokument
    return max(same_period, key=lambda c: c["filingDate"])


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
    # infotable-Dateien bevorzugt zuerst probieren
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
            cusip = row.get("cusip", "").upper()
            if not cusip or value <= 0:
                continue
            positions.append({
                "name": row.get("nameOfIssuer", "?"),
                "cusip": cusip,
                "value": value,
            })
        return positions
    return None


def aggregate_investor(positions):
    """Gleiche Emittenten zusammenfassen (CUSIP-Stamm, erste 6 Stellen)."""
    by_issuer = {}
    for p in positions:
        key = p["cusip"][:6]
        slot = by_issuer.setdefault(key, {"names": Counter(), "value": 0.0})
        slot["names"][p["name"]] += 1
        slot["value"] += p["value"]
    merged = [
        {"key": key, "name": slot["names"].most_common(1)[0][0], "value": slot["value"]}
        for key, slot in by_issuer.items()
    ]
    merged.sort(key=lambda x: -x["value"])
    return merged


def pretty_name(raw):
    """Filing-Namen (oft GROSSBUCHSTABEN) lesbar machen."""
    keep_upper = {"LLC", "LP", "L.P.", "INC", "CORP", "CO", "PLC", "SA", "NV",
                  "ADR", "SE", "AG", "ETF", "II", "III", "IV", "US", "USA",
                  "DE", "NEW", "CL", "A", "B", "C", "&"}
    words = raw.split()
    out = []
    for w in words:
        if w.upper() in keep_upper and len(w) <= 4:
            out.append(w.upper() if w.upper() not in {"NEW", "CL"} else w.capitalize())
        elif re.fullmatch(r"[A-Z0-9&.\-/']+", w) and len(w) > 1:
            out.append(w.capitalize())
        else:
            out.append(w)
    return " ".join(out)


def main():
    print("F13-Liste — Datenabruf von SEC EDGAR")
    print("=" * 50)
    investors_out = []
    errors = []

    for person, firm, cik in INVESTORS:
        label = f"{person} ({firm})"
        try:
            filing = find_latest_13f(cik)
            if not filing:
                raise RuntimeError("kein 13F-HR-Filing gefunden")
            positions = fetch_infotable(cik, filing["accession"])
            if positions is None:
                raise RuntimeError("Information Table nicht gefunden")
            merged = aggregate_investor(positions)
            total = sum(m["value"] for m in merged)
            # Ältere Filings (vor 2023) melden in Tausend USD — heuristisch normalisieren
            scale = 1000.0 if total < 1e7 else 1.0

            def as_pos(m):
                return {
                    "key": m["key"],
                    "name": pretty_name(m["name"]),
                    "value": m["value"] * scale,
                    "weight": round(100.0 * m["value"] / total, 2) if total else 0.0,
                    "isEtf": is_etf(m["name"]),
                }

            # holdings = Top 25 (inkl. ETFs, mit Flag) für dynamische Filter im Dashboard
            holdings = [as_pos(m) for m in merged[:25]]
            # top = klassische Top-15-Einzelaktien (ohne ETFs) für die Standard-Liste
            stock_picks = [m for m in merged if not is_etf(m["name"])]
            top = [as_pos(m) for m in stock_picks[:TOP_N]]

            investors_out.append({
                "person": person,
                "firm": firm,
                "cik": cik,
                "form": filing["form"],
                "filingDate": filing["filingDate"],
                "reportDate": filing["reportDate"],
                "accession": filing["accession"],
                "portfolioValue": total * scale,
                "positionsCount": len(merged),
                "top": top,
                "holdings": holdings,
            })
            print(f"  OK   {label}: {len(merged)} Positionen, "
                  f"Quartal {filing['reportDate']}, Filing {filing['filingDate']}")
        except Exception as exc:
            errors.append({"investor": label, "error": str(exc)})
            print(f"  FEHLER {label}: {exc}", file=sys.stderr)

    # Schnittmengen: In wie vielen Top-15-Listen taucht jede Aktie auf?
    overlap = {}
    for inv in investors_out:
        for pos in inv["top"]:
            slot = overlap.setdefault(pos["key"], {
                "names": Counter(), "investors": [], "combinedValue": 0.0,
            })
            slot["names"][pos["name"]] += 1
            slot["investors"].append({
                "person": inv["person"],
                "weight": pos["weight"],
                "value": pos["value"],
            })
            slot["combinedValue"] += pos["value"]

    ranking = [
        {
            "key": key,
            "name": slot["names"].most_common(1)[0][0],
            "count": len(slot["investors"]),
            "investors": sorted(slot["investors"], key=lambda x: -x["value"]),
            "combinedValue": slot["combinedValue"],
        }
        for key, slot in overlap.items()
    ]
    ranking.sort(key=lambda x: (-x["count"], -x["combinedValue"]))

    data = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "topN": TOP_N,
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
    print(f"F13-Top-{TOP_N}:")
    for i, r in enumerate(data["f13"], 1):
        print(f"  {i:2d}. {r['name']:<40s} {r['count']} von {len(investors_out)} Investoren")
    if errors:
        print(f"\nHinweis: {len(errors)} Investor(en) mit Fehlern — siehe oben.")
    print("\nGespeichert: f13_data.json + f13_data.js")

    # Optional: nach GitHub pushen, damit Streamlit Cloud automatisch neu deployt.
    # Aktiv, wenn mit --push aufgerufen ODER hier ein Git-Repo eingerichtet ist.
    if "--push" in sys.argv or (BASE_DIR / ".git").exists():
        git_push(BASE_DIR)


def git_push(repo_dir):
    """Committet f13_data.json/.js und pusht zu GitHub. Läuft still ohne Repo."""
    import subprocess
    git = ["git", "-C", str(repo_dir)]
    try:
        if subprocess.run(git + ["rev-parse", "--git-dir"],
                          capture_output=True, timeout=5).returncode != 0:
            print("Git-Push übersprungen (kein Repo eingerichtet).")
            return
        subprocess.run(git + ["add", "f13_data.json", "f13_data.js"],
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
