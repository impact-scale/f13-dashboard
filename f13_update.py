#!/usr/bin/env python3
"""
F13-Liste — Automatischer Datenabruf von SEC EDGAR
===================================================
Lädt für ein Universum bekannter 13F-Investoren die letzten Quartale,
erkennt Veränderungen zum Vorquartal (Q/Q) und seit Jahresbeginn (YTD),
reichert um Ticker (OpenFIGI), vollständige Namen (SEC) sowie FinViz-Sektoren
an und berechnet die Schnittmengen (F13-Liste) inkl. Zeitreihe.

Gruppen:
  - "super15" = die 15 Super-Investoren aus der PDF (S. 157)
  - alle übrigen = erweitertes Universum
Der "Top 30 nach Volumen"-Filter wird im Dashboard dynamisch berechnet.

Ausgabe: f13_data.json + f13_data.js  ·  nur Python-Standardbibliothek.
"""

import json
import os
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

USER_AGENT = "F13-Dashboard bjoern@impact-scale.com"
REQUEST_DELAY = 0.12
QUARTERS = 4          # geladene Quartale pro Investor (Q/Q, YTD, Zeitreihe)
TOP_N = 15            # Länge der finalen F13-Liste
STORE_N = 25          # gespeicherte Top-Positionen je Investor

# Investoren-Universum: (Person, Fondsgesellschaft, CIK, Gruppe)
# Gruppe "super15" = PDF-Liste; "" = erweitertes Universum.
INVESTORS = [
    ("Warren Buffett",        "Berkshire Hathaway Inc",                   "0001067983", "super15"),
    ("Ray Dalio",             "Bridgewater Associates, LP",               "0001350694", "super15"),
    ("Prem Watsa",            "Fairfax Financial Holdings LTD",           "0000915191", "super15"),
    ("George Soros",          "Soros Fund Management LLC",                "0001029160", "super15"),
    ("Ron Baron",             "Bamco Inc",                                "0001017918", "super15"),
    ("Daniel Loeb",           "Third Point LLC",                          "0001040273", "super15"),
    ("Bill Ackman",           "Pershing Square Capital Management, L.P.", "0001336528", "super15"),
    ("Mohnish Pabrai",        "Dalal Street, LLC",                        "0001549575", "super15"),
    ("Carl Icahn",            "Icahn Carl C",                             "0000921669", "super15"),
    ("Stanley Druckenmiller", "Duquesne Family Office LLC",               "0001536411", "super15"),
    ("Joel Greenblatt",       "Gotham Asset Management, LLC",             "0001510387", "super15"),
    ("Ken Fisher",            "Fisher Asset Management, LLC",             "0000850529", "super15"),
    ("Jeremy Grantham",       "Grantham, Mayo, Van Otterloo & Co. LLC",   "0001352662", "super15"),
    ("Steven Cohen",          "Point72 Asset Management, L.P.",           "0001603466", "super15"),
    ("Howard Marks",          "Oaktree Capital Management LP",            "0000949509", "super15"),
    # ── Erweitertes Universum (aktive 13F-Filer, CIK verifiziert) ──
    ("Michael Burry",         "Scion Asset Management, LLC",              "0001649339", ""),
    ("David Tepper",          "Appaloosa LP",                            "0001656456", ""),
    ("Chuck Akre",            "Akre Capital Management LLC",              "0001112520", ""),
    ("Li Lu",                 "Himalaya Capital Management LLC",          "0001709323", ""),
    ("Chris Hohn",            "TCI Fund Management Ltd",                  "0001647251", ""),
    ("Bill Nygren",           "Harris Associates L P",                    "0000813917", ""),
    ("Dodge & Cox",           "Dodge & Cox",                             "0000200217", ""),
    ("Bill Miller",           "Miller Value Partners, LLC",              "0001135778", ""),
    ("Thomas Russo",          "Gardner Russo & Quinn LLC",               "0000860643", ""),
    ("Mason Hawkins",         "Southeastern Asset Management",           "0000807985", ""),
    ("Tweedy Browne",         "Tweedy, Browne Co LLC",                   "0000732905", ""),
    ("Wallace Weitz",         "Weitz Investment Management, Inc.",        "0000883965", ""),
    ("Glenn Greenberg",       "Brave Warrior Advisors, LLC",             "0001553733", ""),
    ("David Abrams",          "Abrams Capital Management, L.P.",          "0001358706", ""),
    ("Francois Rochon",       "Giverny Capital Inc.",                    "0001641864", ""),
    ("Chris Bloomstran",      "Semper Augustus Investments Group LLC",    "0001115373", ""),
    ("Bruce Berkowitz",       "Fairholme Capital Management LLC",         "0001056831", ""),
    ("Andrew Brenton",        "Turtle Creek Asset Management Inc.",       "0001484148", ""),
    ("Chase Coleman",         "Tiger Global Management LLC",              "0001167483", ""),
    ("Philippe Laffont",      "Coatue Management LLC",                   "0001135730", ""),
    ("Stephen Mandel",        "Lone Pine Capital LLC",                    "0001061165", ""),
    ("Andreas Halvorsen",     "Viking Global Investors LP",              "0001103804", ""),
    ("John Armitage",         "Egerton Capital (UK) LLP",                "0001581811", ""),
    ("Gates Foundation",      "Gates Foundation Trust",                  "0001166559", ""),
    ("Robert Vinall",         "RV Capital AG",                           "0001766596", ""),
    ("Pat Dorsey",            "Dorsey Asset Management, LLC",             "0001671657", ""),
    ("Norbert Lou",           "Punch Card Management L.P.",               "0001631664", ""),
]

ETF_PATTERNS = re.compile(
    r"\bISHARES\b|\bSPDR\b|\bVANGUARD\b|\bPROSHARES\b|\bINVESCO QQQ\b"
    r"|\bSELECT SECTOR\b|INDEX FUND|\bETF\b|\bTRUST\b.*\bETF\b", re.IGNORECASE)

# ── FinViz-Sektortaxonomie (Ticker → Sektor, Region) ──────────────────────────
# Sektoren exakt wie FinViz: Basic Materials, Communication Services,
# Consumer Cyclical, Consumer Defensive, Energy, Financial, Healthcare,
# Industrials, Real Estate, Technology, Utilities.
SECTOR_REGION = {
    "GOOGL": ("Communication Services", "USA"), "GOOG": ("Communication Services", "USA"),
    "META": ("Communication Services", "USA"), "NFLX": ("Communication Services", "USA"),
    "DIS": ("Communication Services", "USA"), "CMCSA": ("Communication Services", "USA"),
    "T": ("Communication Services", "USA"), "VZ": ("Communication Services", "USA"),
    "TMUS": ("Communication Services", "USA"), "TDS": ("Communication Services", "USA"),
    "SPOT": ("Communication Services", "Luxemburg"),
    "AAPL": ("Technology", "USA"), "MSFT": ("Technology", "USA"),
    "NVDA": ("Technology", "USA"), "AVGO": ("Technology", "USA"),
    "TSM": ("Technology", "Taiwan"), "ASML": ("Technology", "Niederlande"),
    "LRCX": ("Technology", "USA"), "AMAT": ("Technology", "USA"),
    "KLAC": ("Technology", "USA"), "MU": ("Technology", "USA"),
    "INTC": ("Technology", "USA"), "AMD": ("Technology", "USA"),
    "QCOM": ("Technology", "USA"), "TXN": ("Technology", "USA"),
    "ADBE": ("Technology", "USA"), "CRM": ("Technology", "USA"),
    "ORCL": ("Technology", "USA"), "CSCO": ("Technology", "USA"),
    "PLTR": ("Technology", "USA"), "NOW": ("Technology", "USA"),
    "CDNS": ("Technology", "USA"), "SNPS": ("Technology", "USA"),
    "UBER": ("Technology", "USA"), "SHOP": ("Technology", "Kanada"),
    "SE": ("Technology", "Singapur"), "MELI": ("Consumer Cyclical", "Argentinien"),
    "AMZN": ("Consumer Cyclical", "USA"), "TSLA": ("Consumer Cyclical", "USA"),
    "HD": ("Consumer Cyclical", "USA"), "MCD": ("Consumer Cyclical", "USA"),
    "NKE": ("Consumer Cyclical", "USA"), "SBUX": ("Consumer Cyclical", "USA"),
    "BKNG": ("Consumer Cyclical", "USA"), "LOW": ("Consumer Cyclical", "USA"),
    "TJX": ("Consumer Cyclical", "USA"), "DPZ": ("Consumer Cyclical", "USA"),
    "LVMUY": ("Consumer Cyclical", "Frankreich"), "RACE": ("Consumer Cyclical", "Italien"),
    "KO": ("Consumer Defensive", "USA"), "PEP": ("Consumer Defensive", "USA"),
    "PG": ("Consumer Defensive", "USA"), "COST": ("Consumer Defensive", "USA"),
    "WMT": ("Consumer Defensive", "USA"), "KHC": ("Consumer Defensive", "USA"),
    "MDLZ": ("Consumer Defensive", "USA"), "KR": ("Consumer Defensive", "USA"),
    "PM": ("Consumer Defensive", "USA"), "CL": ("Consumer Defensive", "USA"),
    "MO": ("Consumer Defensive", "USA"), "NSRGY": ("Consumer Defensive", "Schweiz"),
    "JPM": ("Financial", "USA"), "BAC": ("Financial", "USA"), "WFC": ("Financial", "USA"),
    "C": ("Financial", "USA"), "GS": ("Financial", "USA"), "MS": ("Financial", "USA"),
    "AXP": ("Financial", "USA"), "V": ("Financial", "USA"), "MA": ("Financial", "USA"),
    "BRK.A": ("Financial", "USA"), "BRK.B": ("Financial", "USA"),
    "BRK/A": ("Financial", "USA"), "BRK/B": ("Financial", "USA"),
    "BLK": ("Financial", "USA"), "SCHW": ("Financial", "USA"), "SPGI": ("Financial", "USA"),
    "MCO": ("Financial", "USA"), "COF": ("Financial", "USA"), "PYPL": ("Financial", "USA"),
    "PGR": ("Financial", "USA"), "CB": ("Financial", "USA"), "AON": ("Financial", "USA"),
    "FFH.TO": ("Financial", "Kanada"), "AJG": ("Financial", "USA"), "MKL": ("Financial", "USA"),
    "UNH": ("Healthcare", "USA"), "JNJ": ("Healthcare", "USA"), "LLY": ("Healthcare", "USA"),
    "PFE": ("Healthcare", "USA"), "MRK": ("Healthcare", "USA"), "ABBV": ("Healthcare", "USA"),
    "TMO": ("Healthcare", "USA"), "ABT": ("Healthcare", "USA"), "DHR": ("Healthcare", "USA"),
    "AMGN": ("Healthcare", "USA"), "ISRG": ("Healthcare", "USA"), "DVA": ("Healthcare", "USA"),
    "NVO": ("Healthcare", "Dänemark"), "HCA": ("Healthcare", "USA"), "ELV": ("Healthcare", "USA"),
    "XOM": ("Energy", "USA"), "CVX": ("Energy", "USA"), "COP": ("Energy", "USA"),
    "OXY": ("Energy", "USA"), "SLB": ("Energy", "USA"), "EOG": ("Energy", "USA"),
    "PSX": ("Energy", "USA"), "MPC": ("Energy", "USA"),
    "CAT": ("Industrials", "USA"), "BA": ("Industrials", "USA"), "HON": ("Industrials", "USA"),
    "GE": ("Industrials", "USA"), "UPS": ("Industrials", "USA"), "RTX": ("Industrials", "USA"),
    "DE": ("Industrials", "USA"), "LMT": ("Industrials", "USA"), "UNP": ("Industrials", "USA"),
    "NSC": ("Industrials", "USA"), "MMM": ("Industrials", "USA"), "GD": ("Industrials", "USA"),
    "LIN": ("Basic Materials", "USA"), "SHW": ("Basic Materials", "USA"),
    "APD": ("Basic Materials", "USA"), "CRH": ("Basic Materials", "Irland"),
    "FCX": ("Basic Materials", "USA"), "NEM": ("Basic Materials", "USA"),
    "NEE": ("Utilities", "USA"), "DUK": ("Utilities", "USA"), "SO": ("Utilities", "USA"),
    "AMT": ("Real Estate", "USA"), "PLD": ("Real Estate", "USA"), "SPG": ("Real Estate", "USA"),
}

# Ticker-Fallback für CINS-Codes (cusip[:6]), die OpenFIGI nicht kennt
TICKER_FALLBACK = {
    "N07059": "ASML", "H1467J": "CB", "G5480U": "LIN", "G54950": "LIN",
    "G25508": "CRH", "L8681T": "SPOT",
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
    """Alle 13F-HR(/A)-Filings, neuestes Quartal zuerst, je Quartal jüngstes Doc."""
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
        if prev is None or fdate > prev["filingDate"]:
            by_period[rdate] = cand
    return [by_period[p] for p in sorted(by_period, reverse=True)]


def fetch_infotable(cik, accession):
    """Lädt die Information Table (XML) und parst Long-Aktienpositionen."""
    acc_nodash = accession.replace("-", "")
    cik_int = int(cik)
    index = http_get_json(
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/index.json")
    xml_files = [f["name"] for f in index["directory"]["item"]
                 if f["name"].lower().endswith(".xml")
                 and "primary_doc" not in f["name"].lower()]
    xml_files.sort(key=lambda n: 0 if "infotable" in n.lower() else 1)
    for name in xml_files:
        raw = http_get(
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{name}")
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
            if row.get("putCall") or row.get("sshPrnamtType", "SH") != "SH":
                continue
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
            positions.append({"name": row.get("nameOfIssuer", "?"),
                              "cusip": cusip, "value": value, "shares": shares})
        return positions
    return None


def aggregate_investor(positions):
    by_issuer = {}
    for p in positions:
        key = p["cusip"][:6]
        slot = by_issuer.setdefault(key, {"names": Counter(), "value": 0.0,
                                          "shares": 0.0, "cusips": Counter()})
        slot["names"][p["name"]] += 1
        slot["value"] += p["value"]
        slot["shares"] += p["shares"]
        slot["cusips"][p["cusip"]] += 1
    merged = [{"key": k, "rawname": s["names"].most_common(1)[0][0],
               "value": s["value"], "shares": s["shares"],
               "cusip": s["cusips"].most_common(1)[0][0]}
              for k, s in by_issuer.items()]
    merged.sort(key=lambda x: -x["value"])
    return merged


def norm_scale(total):
    return 1000.0 if total < 1e7 else 1.0


# ── Namensaufbereitung ────────────────────────────────────────────────────────

_KEEP_UP = {"NV", "AG", "SE", "PLC", "SA", "LP", "LLC", "USA", "US", "AB",
            "ADR", "REIT", "NA", "PLC.", "AG.", "III", "II", "IV"}


def clean_name(title):
    """SEC-Firmennamen säubern: /XX/-Suffixe weg, ALLCAPS → Title Case."""
    t = re.sub(r"\s*/[A-Za-z]{2,4}/?\s*$", "", title).strip().rstrip(",")
    if t.isupper():
        t = " ".join(w.upper() if w.upper() in _KEEP_UP else w
                     for w in t.title().split())
    return t


def pretty_raw(raw):
    keep = {"LLC", "LP", "INC", "CORP", "CO", "PLC", "SA", "NV", "SE", "AG",
            "ETF", "II", "III", "IV", "US", "USA", "&"}
    out = []
    for w in raw.split():
        if w.upper() in keep and len(w) <= 4:
            out.append(w.upper())
        elif re.fullmatch(r"[A-Z0-9&.\-/']+", w) and len(w) > 1:
            out.append(w.capitalize())
        else:
            out.append(w)
    return " ".join(out)


def load_company_names():
    """SEC company_tickers.json → {TICKER: sauberer Firmenname}."""
    try:
        d = http_get_json("https://www.sec.gov/files/company_tickers.json")
        return {v["ticker"].upper(): clean_name(v["title"]) for v in d.values()}
    except Exception as e:
        print(f"  Namensliste nicht geladen ({e}) — Fallback auf Filing-Namen.")
        return {}


# ── Ticker-Auflösung (OpenFIGI, Cache) ────────────────────────────────────────

def load_cache():
    if TICKER_CACHE.exists():
        try:
            return json.loads(TICKER_CACHE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def resolve_tickers(cusips):
    cache = load_cache()
    missing = sorted({c for c in cusips if c and c not in cache})
    print(f"  Ticker: {len(cusips)} CUSIPs, {len(missing)} neu via OpenFIGI ...")
    for i in range(0, len(missing), 10):
        batch = missing[i:i + 10]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"}
                           for c in batch]).encode()
        req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": USER_AGENT})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            for c, r in zip(batch, resp):
                d = r.get("data") or []
                cache[c] = (d[0].get("ticker") if d else None) or ""
        except Exception as e:
            print(f"    OpenFIGI-Batch fehlgeschlagen ({e}) — Retry beim nächsten Lauf.")
        time.sleep(3.0)
    TICKER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), "utf-8")
    return cache


# ── Positionsaufbau + Veränderungen ──────────────────────────────────────────

def enrich(m, total, ticker_map, name_map):
    ticker = ticker_map.get(m["cusip"], "") or TICKER_FALLBACK.get(m["key"], "")
    sector, region = sector_region(ticker)
    name = name_map.get(ticker.upper()) if ticker else None
    if not name:
        name = pretty_raw(m["rawname"])
    scale = norm_scale(total)
    return {"key": m["key"], "name": name, "ticker": ticker,
            "sector": sector, "region": region,
            "value": m["value"] * scale, "shares": m["shares"],
            "weight": round(100.0 * m["value"] / total, 2) if total else 0.0,
            "isEtf": is_etf(m["rawname"])}


def change_vs(cur_shares, base_by_key, key):
    base = base_by_key.get(key)
    if base is None:
        return "NEU"
    bs = base["shares"]
    if bs <= 0:
        return "NEU"
    if cur_shares > bs * 1.02:
        return "AUFGESTOCKT"
    if cur_shares < bs * 0.98:
        return "REDUZIERT"
    return "GEHALTEN"


def slim(pos):
    return {k: pos[k] for k in ("key", "name", "ticker", "sector", "region",
                                "value", "weight", "isEtf")}


def consensus(investors, field, top_n):
    """Zählt, in wie vielen Investoren-Top-N (Einzelaktien) jede Aktie vorkommt."""
    overlap = {}
    for inv in investors:
        picks = [h for h in inv.get(field, []) if not h["isEtf"]][:top_n]
        for pos in picks:
            slot = overlap.setdefault(pos["key"], {
                "names": Counter(), "tickers": Counter(), "investors": [],
                "combined": 0.0, "sector": pos.get("sector", "Sonstige"),
                "region": pos.get("region", "–")})
            slot["names"][pos["name"]] += 1
            if pos.get("ticker"):
                slot["tickers"][pos["ticker"]] += 1
            slot["investors"].append({"person": inv["person"],
                                      "weight": pos["weight"], "value": pos["value"],
                                      "change": pos.get("change", ""),
                                      "changeYtd": pos.get("changeYtd", "")})
            slot["combined"] += pos["value"]
    ranking = [{"key": k, "name": s["names"].most_common(1)[0][0],
                "ticker": (s["tickers"].most_common(1)[0][0] if s["tickers"] else ""),
                "sector": s["sector"], "region": s["region"],
                "count": len(s["investors"]),
                "investors": sorted(s["investors"], key=lambda x: -x["value"]),
                "combinedValue": s["combined"]} for k, s in overlap.items()]
    ranking.sort(key=lambda x: (-x["count"], -x["combinedValue"]))
    return ranking


def ytd_base_date(report_date, loaded_dates):
    """Passende YTD-Basis: 31.12. des Vorjahres, falls unter den geladenen Quartalen."""
    year = int(report_date[:4])
    target = f"{year-1}-12-31"
    if target in loaded_dates:
        return target
    older = [d for d in loaded_dates if d < report_date and d.endswith("-12-31")]
    return max(older) if older else None


def main():
    print("F13-Liste — Datenabruf von SEC EDGAR")
    print("=" * 56)
    name_map = load_company_names()

    raw = []
    errors = []
    for person, firm, cik, group in INVESTORS:
        label = f"{person}"
        try:
            filings = find_13f_filings(cik)[:QUARTERS]
            if not filings:
                raise RuntimeError("kein 13F-HR-Filing")
            quarters = {}
            for f in filings:
                pos = fetch_infotable(cik, f["accession"])
                if pos:
                    quarters[f["reportDate"]] = aggregate_investor(pos)
            if not quarters:
                raise RuntimeError("keine Information Table")
            raw.append({"person": person, "firm": firm, "cik": cik, "group": group,
                        "filing": filings[0], "quarters": quarters})
            qdates = sorted(quarters, reverse=True)
            print(f"  OK   {label:24s} {len(quarters)}Q  aktuell {qdates[0]}")
        except Exception as exc:
            errors.append({"investor": label, "error": str(exc)})
            print(f"  FEHLER {label}: {exc}", file=sys.stderr)

    # CUSIPs des jeweils aktuellen Quartals (Top STORE_N) für Ticker-Auflösung
    cusips = set()
    for r in raw:
        cur = sorted(r["quarters"], reverse=True)[0]
        for m in r["quarters"][cur][:STORE_N]:
            cusips.add(m["cusip"])
    ticker_map = resolve_tickers(cusips)

    # Investoren aufbauen (aktuelles Quartal + Q/Q + YTD)
    investors_out = []
    for r in raw:
        qd = sorted(r["quarters"], reverse=True)
        cur_d = qd[0]
        prev_d = qd[1] if len(qd) > 1 else None
        ytd_d = ytd_base_date(cur_d, set(r["quarters"]))

        cur = r["quarters"][cur_d]
        total = sum(m["value"] for m in cur)
        prev_by = {m["key"]: m for m in r["quarters"].get(prev_d, [])} if prev_d else {}
        ytd_by = {m["key"]: m for m in r["quarters"].get(ytd_d, [])} if ytd_d else {}

        holdings = []
        for m in cur[:STORE_N]:
            pos = enrich(m, total, ticker_map, name_map)
            pos["change"] = change_vs(m["shares"], prev_by, m["key"]) if prev_d else ""
            pos["changeYtd"] = change_vs(m["shares"], ytd_by, m["key"]) if ytd_d else ""
            holdings.append(pos)
        cur_keys = {m["key"] for m in cur}

        def slim_holdings(dd):
            ml = r["quarters"].get(dd, [])
            tt = sum(m["value"] for m in ml)
            return [slim(enrich(m, tt, ticker_map, name_map)) for m in ml[:STORE_N]]

        prev_h = slim_holdings(prev_d) if prev_d else []
        ytd_h = slim_holdings(ytd_d) if ytd_d else []

        def exits(slimlist):
            return [{"key": h["key"], "name": h["name"], "ticker": h["ticker"],
                     "sector": h["sector"], "region": h["region"],
                     "prevValue": h["value"], "prevWeight": h["weight"]}
                    for h in slimlist if h["key"] not in cur_keys and not h["isEtf"]]

        investors_out.append({
            "person": r["person"], "firm": r["firm"], "cik": r["cik"],
            "group": r["group"], "form": r["filing"]["form"],
            "filingDate": r["filing"]["filingDate"], "accession": r["filing"]["accession"],
            "reportDate": cur_d, "prevReportDate": prev_d, "ytdBaseDate": ytd_d,
            "portfolioValue": total * norm_scale(total), "positionsCount": len(cur),
            "top": [h for h in holdings if not h["isEtf"]][:TOP_N],
            "holdings": holdings, "prevHoldings": prev_h, "ytdHoldings": ytd_h,
            "sold": exits(prev_h), "soldYtd": exits(ytd_h),
        })

    # Aktuelle Konsens-Rangliste + Q/Q- und YTD-Delta (alle Investoren)
    ranking = consensus(investors_out, "holdings", TOP_N)
    prev_ct = {r["key"]: r["count"] for r in consensus(investors_out, "prevHoldings", TOP_N)}
    ytd_ct = {r["key"]: r["count"] for r in consensus(investors_out, "ytdHoldings", TOP_N)}
    for r in ranking:
        r["countPrev"] = prev_ct.get(r["key"], 0)
        r["countDelta"] = r["count"] - r["countPrev"]
        r["countYtd"] = ytd_ct.get(r["key"], 0)
        r["countDeltaYtd"] = r["count"] - r["countYtd"]

    # Zeitreihe (#8): Konsens-Top je geladenem Quartal, über alle Investoren
    all_quarters = sorted({d for r in raw for d in r["quarters"]}, reverse=True)[:QUARTERS]
    history = []
    for qd in sorted(all_quarters):
        snap = []
        for r in raw:
            if qd not in r["quarters"]:
                continue
            tot = sum(m["value"] for m in r["quarters"][qd])
            picks = [enrich(m, tot, ticker_map, name_map)
                     for m in r["quarters"][qd][:STORE_N]]
            snap.append({"person": r["person"], "holdings":
                         [h for h in picks if not h["isEtf"]][:TOP_N]})
        hr = consensus(snap, "holdings", TOP_N)[:20]
        history.append({"quarter": qd, "ranking":
                        [{"name": x["name"], "ticker": x["ticker"], "count": x["count"]}
                         for x in hr]})

    data = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "topN": TOP_N, "storeN": STORE_N, "quartersLoaded": QUARTERS,
        "investors": investors_out,
        "ranking": ranking[:60], "f13": ranking[:TOP_N],
        "history": history, "errors": errors,
    }
    (BASE_DIR / "f13_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE_DIR / "f13_data.js").write_text(
        "window.F13_DATA = " + json.dumps(data, ensure_ascii=False) + ";", encoding="utf-8")

    print("=" * 56)
    print(f"Investoren geladen: {len(investors_out)}/{len(INVESTORS)}  "
          f"(Fehler: {len(errors)})")
    print(f"F13-Top-{TOP_N} (Konsens · ΔQ/Q · ΔYTD):")
    for i, r in enumerate(data["f13"], 1):
        dq = f"+{r['countDelta']}" if r['countDelta'] > 0 else str(r['countDelta'])
        dy = f"+{r['countDeltaYtd']}" if r['countDeltaYtd'] > 0 else str(r['countDeltaYtd'])
        print(f"  {i:2d}. {(r['ticker'] or '?'):6s} {r['name'][:30]:30s} "
              f"{r['count']:2d}  Q/Q {dq:>3s}  YTD {dy:>3s}")
    print("\nGespeichert: f13_data.json + f13_data.js")

    if os.getenv("GITHUB_ACTIONS"):
        pass  # In GitHub Actions übernimmt der Workflow das Committen/Pushen
    elif "--push" in sys.argv or (BASE_DIR / ".git").exists():
        git_push(BASE_DIR)


def git_push(repo_dir):
    import subprocess
    git = ["git", "-C", str(repo_dir)]
    try:
        if subprocess.run(git + ["rev-parse", "--git-dir"],
                          capture_output=True, timeout=5).returncode != 0:
            print("Git-Push übersprungen (kein Repo).")
            return
        subprocess.run(git + ["add", "f13_data.json", "f13_data.js", "ticker_cache.json"],
                       timeout=10, check=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(git + ["commit", "-m", f"F13 Update {stamp}"],
                       capture_output=True, timeout=10)
        subprocess.run(git + ["fetch", "origin"], capture_output=True, timeout=30)
        subprocess.run(git + ["merge", "origin/main", "--no-edit", "-X", "ours"],
                       capture_output=True, timeout=30)
        res = subprocess.run(git + ["push"], capture_output=True, text=True, timeout=30)
        print("GitHub-Push erfolgreich — Streamlit Cloud aktualisiert sich in ~1 Min."
              if res.returncode == 0 else f"GitHub-Push fehlgeschlagen:\n{res.stderr.strip()}")
    except Exception as e:
        print(f"Git-Push: {e}")


if __name__ == "__main__":
    main()
