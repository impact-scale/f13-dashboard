"""
F13-Liste — Super-Investoren Dashboard (Streamlit)
==================================================
Zeigt die Schnittmengen der 13F-Portfolios der 15 Super-Investoren.
Liest f13_data.json (von f13_update.py erzeugt) und berechnet die
Konsens-Rangliste dynamisch nach Filtereinstellungen.

Deploy: https://share.streamlit.io  →  Repo verbinden  →  streamlit_app.py
Lokal:  streamlit run streamlit_app.py
"""

import json
from collections import Counter
from datetime import datetime, date, timedelta
from pathlib import Path
import io

try:
    from zoneinfo import ZoneInfo
    TZ_BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # Fallback, falls tzdata fehlt
    TZ_BERLIN = None

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─── Konfiguration ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="F13-Liste Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = Path(__file__).parent / "f13_data.json"

# CI-Farben (Impact Scale Academy)
MIDNIGHT = "#081829"
NAVY = "#0D2238"
GOLD = "#C9A84C"
OFFWHITE = "#F4F1EB"
SLATE = "#8899AA"

st.markdown(f"""
<style>
    .stApp {{ background-color: {MIDNIGHT}; color: {OFFWHITE}; }}
    section[data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    .block-container {{ padding-top: 2rem; max-width: 1250px; }}
    h1, h2, h3, h4 {{ color: {OFFWHITE}; font-family: Arial, sans-serif; }}
    hr {{ border-color: #1a3a5c; }}
    .mono {{ font-family: "IBM Plex Mono","Courier New",monospace; }}
    /* KPI-Karten */
    div[data-testid="stMetric"] {{
        background: {NAVY}; border: 1px solid #1a3a5c;
        border-radius: 10px; padding: 14px 18px;
    }}
    div[data-testid="stMetricLabel"] p {{
        color: {SLATE}; font-size: 0.72rem; text-transform: uppercase;
        letter-spacing: 0.06em; font-family: "Courier New",monospace;
    }}
    div[data-testid="stMetricValue"] {{ color: {OFFWHITE}; }}
    /* ── Navigationsmenü (st.radio als Website-Menü) ──────────── */
    div[data-testid="stRadio"] > div[role="radiogroup"] {{
        flex-direction: row; flex-wrap: wrap; gap: 4px;
        background: {NAVY}; border: 1px solid #1a3a5c;
        border-radius: 10px; padding: 5px; margin-bottom: 4px;
    }}
    div[data-testid="stRadio"] > div[role="radiogroup"] > label {{
        margin: 0; padding: 7px 15px; border-radius: 7px; cursor: pointer;
        color: {SLATE}; font-weight: 600; background: transparent;
        transition: background .12s;
    }}
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {{
        color: {OFFWHITE}; background: #12325280;
    }}
    /* aktives Element in Gold hervorheben */
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) {{
        background: {GOLD};
    }}
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) div,
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) p {{
        color: {MIDNIGHT} !important; font-weight: 700;
    }}
    /* den Radio-Kreis ausblenden */
    div[data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child {{
        display: none;
    }}
    .goldbar {{ height: 2.5px; background: {GOLD}; border: none; margin: 4px 0 14px; }}
    .importbar {{
        background: {NAVY}; border: 1px solid #1a3a5c; border-left: 3px solid {GOLD};
        border-radius: 6px; padding: 9px 16px; font-size: 0.85rem; color: {OFFWHITE};
        font-family: "Courier New",monospace;
    }}
    .importbar b {{ color: {GOLD}; }}
    .importdot {{
        display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background: {GOLD}; margin-right: 8px; vertical-align: middle;
    }}
    .tag {{
        font-family: "Courier New",monospace; font-size: 0.72rem;
        letter-spacing: 0.12em; color: {GOLD}; text-transform: uppercase;
    }}
    .stDataFrame {{ border: 1px solid #1a3a5c; border-radius: 8px; }}
    .callout {{
        background: {OFFWHITE}; color: {NAVY}; border-left: 3px solid {GOLD};
        padding: 12px 16px; border-radius: 4px; font-size: 0.9rem;
    }}
    .stButton button {{
        background: {NAVY}; color: {OFFWHITE}; border: 1px solid {GOLD};
        border-radius: 6px;
    }}
</style>
""", unsafe_allow_html=True)


# ─── Daten laden ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data():
    if not DATA_PATH.exists():
        return None
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def fmt_money(v):
    if not v:
        return "–"
    m = v / 1e6
    if m >= 1000:
        return f"{m/1000:.2f} Mrd $"
    return f"{m:.0f} Mio $"


def de_num(x, dec=2):
    """Deutsches Zahlenformat: 1234.5 -> '1.234,50'."""
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(ttl=3600)
def get_eurusd():
    """EUR→USD-Wechselkurs von Yahoo (1h gecacht). Fallback 1.08 bei Fehler."""
    import urllib.request
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               "EURUSD=X?interval=1d&range=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        j = json.loads(urllib.request.urlopen(req, timeout=10).read())
        px = j["chart"]["result"][0]["meta"].get("regularMarketPrice")
        return float(px) if px else 1.08
    except Exception:
        return 1.08


PIE_COLORS = ["#C9A84C", "#0D2238", "#8899AA", "#5a7a9a", "#a8863a",
              "#3d5a75", "#c0b088", "#6b8caa", "#8a6d2f", "#d4c9b0"]


def make_donut(counter, title):
    """Sektor-/Kategorie-Donut im CI (Prozent innen, Legende unten)."""
    items = counter.most_common()
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    f = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.5, sort=False,
        marker=dict(colors=PIE_COLORS[:len(labels)], line=dict(color=MIDNIGHT, width=1)),
        textinfo="percent", textposition="inside", insidetextorientation="horizontal",
        textfont=dict(color=OFFWHITE, family="Arial", size=13),
        hovertemplate="%{label}: %{value} Titel (%{percent})<extra></extra>"))
    f.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        paper_bgcolor=MIDNIGHT, font=dict(color=OFFWHITE), showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center",
                    x=0.5, font=dict(size=11)),
        height=380, margin=dict(l=10, r=10, t=50, b=10))
    return f


def next_13f_release(today=None):
    """Nächste 13F-Veröffentlichung: Quartalsende + 45 Tage Frist.
    Gibt (Quartalslabel, Quartalsende, Frist-Datum) zurück."""
    today = today or date.today()
    cands = []
    for y in (today.year - 1, today.year, today.year + 1):
        for q, (m, d) in enumerate([(3, 31), (6, 30), (9, 30), (12, 31)], start=1):
            qe = date(y, m, d)
            cands.append((f"Q{q} {y}", qe, qe + timedelta(days=45)))
    for label, qe, deadline in sorted(cands, key=lambda x: x[2]):
        if deadline >= today:
            return label, qe, deadline
    return None, None, None


def df_to_excel(df, sheet="F13-Liste"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        df.to_excel(xl, index=False, sheet_name=sheet)
    return buf.getvalue()


def f13_to_pdf(df, meta_lines):
    """F13-Liste als CI-gestyltes PDF (reportlab)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    navy = colors.HexColor("#0D2238")
    gold = colors.HexColor("#C9A84C")
    slate = colors.HexColor("#8899AA")
    offwhite = colors.HexColor("#F4F1EB")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18*mm, bottomMargin=16*mm,
                            leftMargin=16*mm, rightMargin=16*mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=navy,
                        fontName="Helvetica-Bold", fontSize=20, spaceAfter=2)
    tag = ParagraphStyle("tag", parent=styles["Normal"], textColor=gold,
                         fontName="Courier-Bold", fontSize=8, spaceAfter=10)
    meta = ParagraphStyle("meta", parent=styles["Normal"], textColor=slate,
                          fontName="Courier", fontSize=8, leading=12)
    story = [Paragraph("F13-LISTE · SUPER-INVESTOREN", tag),
             Paragraph("F13-Konsensliste", h1)]
    for ln in meta_lines:
        story.append(Paragraph(ln, meta))
    story.append(Spacer(1, 8*mm))

    head = list(df.columns)
    body = [head] + df.astype(str).values.tolist()
    tbl = Table(body, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), offwhite),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F4F1EB"), colors.HexColor("#EDE9E0")]),
        ("TEXTCOLOR", (0, 1), (-1, -1), navy),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, gold),
        ("GRID", (0, 1), (-1, -1), 0.3, slate),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))
    foot = ParagraphStyle("foot", parent=styles["Normal"], textColor=slate,
                          fontName="Courier", fontSize=7)
    story.append(Paragraph(
        "BS IMPACT SCALE GmbH © · Datenquelle: SEC EDGAR (13F-HR) · "
        "Keine Anlageberatung.", foot))
    doc.build(story)
    return buf.getvalue()


def compute_ranking(data, selected_investors, top_n_per_inv, include_etfs,
                    field="holdings"):
    """Konsens-Rangliste dynamisch aus den holdings (oder prevHoldings) berechnen."""
    overlap = {}
    for inv in data["investors"]:
        if inv["person"] not in selected_investors:
            continue
        picks = [h for h in inv.get(field, []) if include_etfs or not h["isEtf"]]
        for pos in picks[:top_n_per_inv]:
            slot = overlap.setdefault(pos["key"], {
                "names": Counter(), "tickers": Counter(), "investors": [],
                "combined": 0.0, "isEtf": pos["isEtf"],
                "sector": pos.get("sector", "Sonstige"),
                "region": pos.get("region", "–"),
            })
            slot["names"][pos["name"]] += 1
            if pos.get("ticker"):
                slot["tickers"][pos["ticker"]] += 1
            slot["investors"].append({
                "person": inv["person"], "weight": pos["weight"], "value": pos["value"],
                "change": pos.get("change", ""), "changeYtd": pos.get("changeYtd", ""),
            })
            slot["combined"] += pos["value"]
    ranking = [{
        "key": k, "name": s["names"].most_common(1)[0][0],
        "ticker": (s["tickers"].most_common(1)[0][0] if s["tickers"] else ""),
        "sector": s["sector"], "region": s["region"],
        "count": len(s["investors"]),
        "investors": sorted(s["investors"], key=lambda x: -x["value"]),
        "combined": s["combined"], "isEtf": s["isEtf"],
    } for k, s in overlap.items()]
    ranking.sort(key=lambda x: (-x["count"], -x["combined"]))
    return ranking


def with_consensus_delta(data, selected, top_n, include_etfs):
    """Aktuelle Rangliste + Δ ggü. Vorquartal (Q/Q) und Jahresbeginn (YTD)."""
    ranking = compute_ranking(data, selected, top_n, include_etfs, "holdings")
    prev = {r["key"]: r["count"] for r in
            compute_ranking(data, selected, top_n, include_etfs, "prevHoldings")}
    ytd = {r["key"]: r["count"] for r in
           compute_ranking(data, selected, top_n, include_etfs, "ytdHoldings")}
    for r in ranking:
        r["countPrev"] = prev.get(r["key"], 0)
        r["countDelta"] = r["count"] - r["countPrev"]
        r["countYtd"] = ytd.get(r["key"], 0)
        r["countDeltaYtd"] = r["count"] - r["countYtd"]
    return ranking


CHANGE_BADGE = {
    "NEU": "🟢 Neu", "AUFGESTOCKT": "🔼 Aufgestockt",
    "REDUZIERT": "🔽 Reduziert", "GEHALTEN": "▪ Gehalten", "": "–",
}


# ─── Kopf ─────────────────────────────────────────────────────────────────────

data = load_data()

st.markdown('<div class="tag">F13-LISTE · SUPER-INVESTOREN-KONSENS</div>',
            unsafe_allow_html=True)
st.markdown("# F13-Liste Dashboard")
st.markdown('<hr class="goldbar">', unsafe_allow_html=True)

if data is None:
    st.error("Keine Daten gefunden. Bitte zuerst `python3 f13_update.py` ausführen "
             "(erzeugt f13_data.json).")
    st.stop()

all_investors = [inv["person"] for inv in data["investors"]]
# generatedAt ist UTC (ISO mit +00:00) → in lokale Zeit umrechnen
# In deutsche Zeit umrechnen (fest Europe/Berlin — nicht die Server-Zeitzone,
# da Streamlit Cloud in UTC läuft).
generated = datetime.fromisoformat(data["generatedAt"])
generated = generated.astimezone(TZ_BERLIN) if TZ_BERLIN else generated.astimezone()
quarter = data["investors"][0]["reportDate"] if data["investors"] else "–"
n_ok = len(data["investors"])
n_err = len(data.get("errors", []))
# EUR/USD: bevorzugt aus dem täglichen Datenlauf, sonst live (gecacht)
_fx = data.get("eurusd") or {}
EURUSD = _fx.get("rate") or get_eurusd()
EURUSD_ASOF = _fx.get("asOf")

# ─── Sidebar-Filter ───────────────────────────────────────────────────────────

INV_KEYS = {p: f"inv_{p}" for p in all_investors}
SUPER15 = [inv["person"] for inv in data["investors"] if inv.get("group") == "super15"]
TOP30_VOL = [inv["person"] for inv in
             sorted(data["investors"], key=lambda x: -x.get("portfolioValue", 0))[:30]]


def _toggle_all_investors():
    val = st.session_state["inv_all"]
    for k in INV_KEYS.values():
        st.session_state[k] = val


def _set_investors(names):
    sel = set(names)
    for p, k in INV_KEYS.items():
        st.session_state[k] = (p in sel)
    st.session_state["inv_all"] = (len(sel) == len(INV_KEYS))


with st.sidebar:
    st.markdown('<div class="tag">FILTER</div>', unsafe_allow_html=True)
    st.markdown('<hr class="goldbar">', unsafe_allow_html=True)

    top_n_per_inv = st.slider(
        "Positionen pro Investor", 5, 25, 15,
        help="Wie viele der größten Positionen jedes Investors zählen als "
             "'Top-Pick'? Standard: Top 15.",
    )
    min_consensus = st.slider(
        "Mindest-Konsens (Investoren)", 1, 25, 3,
        help="Zeige nur Aktien, die von mindestens so vielen Investoren gehalten werden.",
    )
    include_etfs = st.toggle(
        "ETFs / Indexfonds einbeziehen", value=False,
        help="Fokus auf Einzelaktien. Standard: ETFs ausgeblendet.",
    )
    search = st.text_input("Aktie suchen", "").strip().lower()

    st.markdown('<hr class="goldbar">', unsafe_allow_html=True)
    st.markdown("**Investoren einbeziehen**")
    # Standard beim ersten Laden: alle eingeschaltet (vollständige F13-Liste)
    if "inv_all" not in st.session_state:
        st.session_state["inv_all"] = True
        for k in INV_KEYS.values():
            st.session_state[k] = True

    st.checkbox("Alle ein-/ausschalten", key="inv_all",
                on_change=_toggle_all_investors)
    st.caption("Schnellauswahl:")
    pb1, pb2 = st.columns(2)
    pb1.button("★ Super-15", on_click=_set_investors, args=(SUPER15,),
               use_container_width=True,
               help="Nur die 15 Super-Investoren.")
    pb2.button("Top 30 Vol.", on_click=_set_investors, args=(TOP30_VOL,),
               use_container_width=True,
               help="Die 30 Investoren mit dem größten Portfolio-Volumen.")
    st.markdown('<hr style="border-color:#1a3a5c;margin:2px 0 6px;">',
                unsafe_allow_html=True)
    st.caption("★ Super-Investoren")
    for p in SUPER15:
        st.checkbox(p, key=INV_KEYS[p])
    extended = [p for p in all_investors if p not in set(SUPER15)]
    if extended:
        st.caption("Erweitertes Universum")
        for p in extended:
            st.checkbox(p, key=INV_KEYS[p])

    selected = [p for p in all_investors if st.session_state.get(INV_KEYS[p], True)]
    st.caption(f"{len(selected)} von {len(all_investors)} Investoren aktiv")

if not selected:
    st.warning("Bitte mindestens einen Investor auswählen.")
    st.stop()

# Statusleiste oben — auf allen Ansichten sichtbar (inkl. aktiver Investoren)
st.markdown(
    f'<div class="importbar">'
    f'<span class="importdot"></span>'
    f'<b>Investoren aktiv:</b>&nbsp; {len(selected)} / {n_ok}'
    f'&nbsp;·&nbsp; <b>Stand:</b> {generated.strftime("%d.%m.%Y · %H:%M Uhr %Z")}'
    f'&nbsp;·&nbsp; <b>EUR/USD:</b> {de_num(EURUSD, 4)}'
    f'{f"&nbsp;·&nbsp; {n_err} mit Fehler" if n_err else ""}'
    f'&nbsp;·&nbsp; Quelle: SEC EDGAR (13F-HR)'
    f'&nbsp;<a href="https://www.sec.gov/edgar/search/#/forms=13F-HR" target="_blank" '
    f'title="Zur Originalquelle: SEC EDGAR 13F-HR" '
    f'style="text-decoration:none;color:{GOLD};font-weight:700;">ⓘ</a>'
    f'</div>',
    unsafe_allow_html=True,
)
st.write("")

ranking = with_consensus_delta(data, selected, top_n_per_inv, include_etfs)
ranking = [r for r in ranking if r["count"] >= min_consensus]
if search:
    ranking = [r for r in ranking
               if search in r["name"].lower() or search in r.get("ticker", "").lower()]

# ─── Navigationsmenü (oben, direkt unter dem Kopf) ────────────────────────────

prev_quarter = data["investors"][0].get("prevReportDate") if data["investors"] else None
ytd_base = data["investors"][0].get("ytdBaseDate") if data["investors"] else None
rel_label, rel_qe, rel_deadline = next_13f_release()


def delta_str(d):
    return f"▲ +{d}" if d > 0 else (f"▼ {d}" if d < 0 else "=")


PAGES = ["📊 F13-Konsensliste", "🔄 Veränderungen", "📈 Verlauf", "🧮 Investment-Rechner",
         "🔁 Rebalancing", "🧩 Struktur", "👤 Investoren-Details", "🆕 Neue Meldungen",
         "🎯 Backtest", "💰 Cash & Flows"]
# Serverseitige Navigation: es wird NUR die gewählte Kategorie gerendert
# (im Gegensatz zu st.tabs, das alle Inhalte ins DOM legt).
page = st.radio("Navigation", PAGES, horizontal=True,
                label_visibility="collapsed", key="nav_page")

# --- Tab 1: Konsens ---
if page == "📊 F13-Konsensliste":
    # KPI-Zeile (Kontext zur Konsensliste)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Investoren aktiv", f"{len(selected)} / {len(all_investors)}")
    c2.metric("Meldequartal", quarter)
    c3.metric("Konsens-Titel", len(ranking))
    c4.metric("Nächste Liste", rel_deadline.strftime("%d.%m.%Y") if rel_deadline else "–",
              help=f"Nächstes Meldequartal {rel_label} (Quartalsende "
                   f"{rel_qe.strftime('%d.%m.%Y')}). 13F-Berichte sind spätestens "
                   f"45 Tage nach Quartalsende fällig — dann ist die F13-Liste vollständig. "
                   f"Meldungen treffen aber laufend im 45-Tage-Fenster ein."
                   if rel_deadline else "")
    if data.get("errors"):
        with st.expander(f"⚠ {len(data['errors'])} Investor(en) mit Ladefehlern"):
            for e in data["errors"]:
                st.write(f"- {e['investor']} — {e['error']}")
    st.markdown(
        f'<div class="callout"><b>So liest du die Liste:</b> Je mehr Investoren dieselbe '
        f'Aktie in ihren größten Positionen halten, desto stärker der Konsens. Aktuell aus '
        f'<b>{len(all_investors)} Investoren</b> — über die Schnellauswahl links auf die '
        f'<b>15 Super-Investoren</b> oder die <b>Top 30 nach Volumen</b> eingrenzbar.</div>',
        unsafe_allow_html=True)
    st.write("")

    if not ranking:
        st.info("Keine Titel mit diesen Filtern. Konsens-Schwelle senken oder mehr "
                "Investoren wählen.")
    else:
        top_chart = ranking[:20][::-1]
        fig = go.Figure(go.Bar(
            x=[r["count"] for r in top_chart],
            y=[f"{r['ticker'] or r['name'][:14]}" for r in top_chart],
            orientation="h", marker_color=GOLD,
            text=[f"{r['count']}" for r in top_chart], textposition="outside",
            textfont=dict(color=OFFWHITE, family="Courier New"),
        ))
        fig.update_layout(
            title="Anzahl Investoren pro Aktie (Top 20)",
            paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
            font=dict(color=OFFWHITE, family="Arial"),
            xaxis=dict(gridcolor="#1a3a5c", title="Investoren"),
            yaxis=dict(gridcolor="#1a3a5c"),
            height=max(340, 26 * len(top_chart)), margin=dict(l=10, r=30, t=50, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        df_rank = pd.DataFrame([{
            "Rang": i + 1,
            "Ticker": r.get("ticker", "") or "–",
            "Aktie": r["name"] + ("  ⓔ" if r["isEtf"] else ""),
            "Investoren": f"{r['count']} / {len(selected)}",
            "Δ Q/Q": delta_str(r["countDelta"]),
            "Δ YTD": delta_str(r.get("countDeltaYtd", 0)),
            "Sektor": r.get("sector", "–"),
            "Gehalten von": ", ".join(inv["person"] for inv in r["investors"]),
            "Summe Wert": fmt_money(r["combined"]),
        } for i, r in enumerate(ranking)])
        st.dataframe(df_rank, use_container_width=True, hide_index=True,
                     height=min(560, 45 + 35 * len(df_rank)))
        st.caption(f"ⓔ = ETF/Indexfonds · Δ Q/Q = Δ Investorenzahl ggü. Vorquartal "
                   f"({prev_quarter or 'n/a'}) · Δ YTD = ggü. Jahresbeginn "
                   f"({ytd_base or 'n/a'})")

        # Export
        st.markdown("**Export der aktuellen F13-Liste**")
        e1, e2, e3 = st.columns(3)
        fname = f"F13-Liste_{quarter}"
        e1.download_button("⬇ CSV", df_rank.to_csv(index=False).encode("utf-8"),
                           f"{fname}.csv", "text/csv", use_container_width=True)
        try:
            e2.download_button("⬇ Excel", df_to_excel(df_rank), f"{fname}.xlsx",
                               "application/vnd.openxmlformats-officedocument."
                               "spreadsheetml.sheet", use_container_width=True)
        except Exception:
            e2.caption("Excel: openpyxl fehlt")
        try:
            meta = [f"Meldequartal: {quarter}",
                    f"Stand Datenimport: {generated.strftime('%d.%m.%Y %H:%M')}",
                    f"Investoren einbezogen: {len(selected)} von {len(all_investors)}"]
            e3.download_button("⬇ PDF", f13_to_pdf(df_rank, meta), f"{fname}.pdf",
                               "application/pdf", use_container_width=True)
        except Exception as ex:
            e3.caption("PDF: reportlab fehlt")

# --- Tab 2: Veränderungen ---
if page == "🔄 Veränderungen":
    if not prev_quarter:
        st.info("Kein Vorquartal in den Daten — Veränderungen nicht berechenbar.")
    else:
        mode = st.radio("Vergleichszeitraum", ["Vorquartal (Q/Q)", "Jahresbeginn (YTD)"],
                        horizontal=True)
        ytd = mode.startswith("Jahresbeginn")
        base_label = (ytd_base or "n/a") if ytd else (prev_quarter or "n/a")
        dkey = "countDeltaYtd" if ytd else "countDelta"
        chkey = "changeYtd" if ytd else "change"
        soldkey = "soldYtd" if ytd else "sold"

        st.markdown(f"### Konsens-Momentum &nbsp;·&nbsp; {base_label} → {quarter}")
        st.caption("Welche Aktien gewinnen oder verlieren gerade Investoren? "
                   "Das ist das eigentliche Signal der Strategie.")
        movers = [r for r in ranking if r.get(dkey, 0) != 0]
        gainers = sorted([r for r in movers if r[dkey] > 0], key=lambda x: -x[dkey])
        losers = sorted([r for r in movers if r[dkey] < 0], key=lambda x: x[dkey])
        def _full_height(n):
            # Höhe so setzen, dass alle Zeilen ohne Scrollbalken sichtbar sind
            return 38 + 35 * max(n, 1)
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown("**🟢 Gewinnt Investoren**")
            st.dataframe(pd.DataFrame([{
                "Ticker": r.get("ticker") or "–", "Aktie": r["name"],
                "Jetzt": r["count"], "Δ": f"+{r[dkey]}",
            } for r in gainers]) if gainers else pd.DataFrame({"—": ["keine"]}),
                hide_index=True, use_container_width=True,
                height=_full_height(len(gainers)))
        with mc2:
            st.markdown("**🔴 Verliert Investoren**")
            st.dataframe(pd.DataFrame([{
                "Ticker": r.get("ticker") or "–", "Aktie": r["name"],
                "Jetzt": r["count"], "Δ": str(r[dkey]),
            } for r in losers]) if losers else pd.DataFrame({"—": ["keine"]}),
                hide_index=True, use_container_width=True,
                height=_full_height(len(losers)))

        st.markdown("---")
        st.markdown("### Käufe & Verkäufe je Investor")
        typ = st.selectbox("Filter", ["Alle Veränderungen", "Nur Käufe (Neu)",
                                      "Aufgestockt", "Reduziert", "Verkäufe"])
        change_rows = []
        for inv in data["investors"]:
            if inv["person"] not in selected:
                continue
            picks = [h for h in inv.get("holdings", [])
                     if include_etfs or not h["isEtf"]][:top_n_per_inv]
            for h in picks:
                ch = h.get(chkey, "")
                if ch in ("NEU", "AUFGESTOCKT", "REDUZIERT"):
                    change_rows.append({"Investor": inv["person"],
                                        "Ticker": h.get("ticker") or "–",
                                        "Aktie": h["name"],
                                        "Veränderung": CHANGE_BADGE.get(ch, ch),
                                        "Gewicht": f"{h['weight']:.1f} %"})
            for s in inv.get(soldkey, []):
                change_rows.append({"Investor": inv["person"],
                                    "Ticker": s.get("ticker") or "–",
                                    "Aktie": s["name"],
                                    "Veränderung": "🔴 Verkauft", "Gewicht": "–"})
        df_ch = pd.DataFrame(change_rows)
        if not df_ch.empty:
            filt = {"Nur Käufe (Neu)": "🟢 Neu", "Aufgestockt": "🔼 Aufgestockt",
                    "Reduziert": "🔽 Reduziert", "Verkäufe": "🔴 Verkauft"}
            if typ in filt:
                df_ch = df_ch[df_ch["Veränderung"] == filt[typ]]
        if df_ch.empty:
            st.info("Keine Veränderungen für diese Auswahl.")
        else:
            st.dataframe(df_ch, hide_index=True, use_container_width=True,
                         height=min(600, 45 + 33 * len(df_ch)))
            st.caption(f"Basis: gespeicherte Top-Positionen je Investor · Vergleich "
                       f"gegen {base_label} (Verkäufe = damals in Top-Positionen, "
                       f"jetzt nicht mehr).")

# --- Tab 6: Verlauf (Zeitreihe) ---
if page == "📈 Verlauf":
    history = data.get("history", [])
    if len(history) < 2:
        st.info("Noch keine ausreichende Historie (mindestens 2 Quartale nötig).")
    else:
        st.markdown(f"### Konsens-Verlauf über {len(history)} Quartale")
        st.caption("Wie sich die Zahl der Investoren pro Top-Aktie über die geladenen "
                   "Quartale entwickelt hat (Basis: alle Investoren).")
        quarters_axis = [h["quarter"] for h in history]
        # Aktien der aktuellen F13-Liste verfolgen
        track = [(r.get("ticker") or r["name"], r["key"]) for r in ranking[:8]]
        # Quartal → {Aktienname: Investorenzahl}; Match über den Namen
        per_q = {h["quarter"]: {x["name"]: x["count"] for x in h["ranking"]}
                 for h in history}
        cur_names = {r["key"]: r["name"] for r in ranking}
        fig = go.Figure()
        palette = ["#C9A84C", "#8899AA", "#5fbf7f", "#d9776a", "#7fa8d9",
                   "#c0b088", "#a86dcf", "#6bbfb5"]
        for i, (lbl, key) in enumerate(track):
            nm = cur_names.get(key)
            ys = [per_q.get(q, {}).get(nm, 0) for q in quarters_axis]
            fig.add_trace(go.Scatter(
                x=quarters_axis, y=ys, mode="lines+markers", name=lbl,
                line=dict(width=2.5, color=palette[i % len(palette)]),
                marker=dict(size=7)))
        fig.update_layout(
            paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
            font=dict(color=OFFWHITE, family="Arial"),
            xaxis=dict(gridcolor="#1a3a5c", title="Meldequartal"),
            yaxis=dict(gridcolor="#1a3a5c", title="Anzahl Investoren"),
            height=430, margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Verfolgt die aktuell 8 stärksten Konsens-Titel rückwirkend über "
                   "die geladenen Quartale.")

# --- Tab 7: Backtest ---
if page == "🎯 Backtest":
    history = data.get("history", [])
    prices = data.get("prices", {})
    prices_asof = data.get("pricesAsOf")
    quarters_avail = [h["quarter"] for h in history if any(
        e.get("price") for e in h["ranking"])]
    if not quarters_avail or not prices:
        st.info("Für den Backtest werden Quartals- und aktuelle Kurse benötigt — "
                "bitte zuerst `python3 f13_update.py` mit aktueller Version ausführen.")
    else:
        st.markdown("### Backtest — F13-Liste eines Quartals bis heute")
        st.caption("Wähle ein Meldequartal: Wir vergleichen den damaligen "
                   "Quartals-Schlusskurs (aus 13F) mit dem aktuellen Kurs und zeigen die "
                   "Rendite, die die F13-Liste jenes Quartals bis heute erzielt hätte.")

        bc1, bc2, bc3 = st.columns([2, 2, 2])
        sel_q = bc1.selectbox("Meldequartal", quarters_avail[::-1],
                              help="Stand der F13-Liste, ab dem gerechnet wird.")
        n_bt = bc2.number_input("Anzahl Titel (Top N)", 5, 20, data["topN"], 1)
        method_bt = bc3.radio("Gewichtung", ["Equal Weight", "Conviction (Profi)"],
                              horizontal=True)

        snap = next(h for h in history if h["quarter"] == sel_q)
        entries = [e for e in snap["ranking"] if e.get("price")][:int(n_bt)]

        # Haltedauer in Jahren: vom Quartalsende bis zum aktuellen Kursdatum
        def _pd(s):
            y, m, d = map(int, s.split("-"))
            return date(y, m, d)
        end_d = _pd(prices_asof) if prices_asof else date.today()
        years = max((end_d - _pd(sel_q)).days / 365.25, 1e-6)

        def annualize(total_pct):
            return ((1 + total_pct / 100) ** (1 / years) - 1) * 100

        rows, rets = [], []
        excluded = 0
        counts_bt = [max(e["count"], 0) for e in entries]
        wsum = sum(counts_bt) or 1
        for i, e in enumerate(entries):
            p0 = e["price"]
            pn = prices.get(e["ticker"], {}).get("price")
            # Plausibilitätsschutz: Kursverhältnis muss zwischen 0,1x und 10x liegen
            # (fängt Aktienklassen-/Einheiten-Fehler wie BRK.A vs BRK.B ab)
            valid = bool(p0 and pn and 0.02 <= (pn / p0) <= 50)
            r = (pn - p0) / p0 * 100 if valid else None
            # p.a. nur bei Haltedauer ≥ 1 Jahr (darunter überzeichnet die Hochrechnung)
            pa = annualize(r) if (r is not None and years >= 1.0) else None
            w = (1 / len(entries)) if method_bt.startswith("Equal") else counts_bt[i] / wsum
            if r is not None:
                rets.append((r, w))
            elif pn:
                excluded += 1
            rows.append({
                "Ticker": e["ticker"] or "–", "Aktie": e["name"],
                f"Kurs {sel_q}": f"{p0:,.2f} $".replace(",", "."),
                "Kurs aktuell": f"{pn:,.2f} $".replace(",", ".") if pn else "–",
                "Rendite gesamt": f"{r:+.1f} %" if r is not None else "–",
                "Rendite p.a.": f"{pa:+.1f} %" if pa is not None else "–",
                "Gewicht": f"{w*100:.1f} %",
            })

        # Portfolio-Rendite (gewichtet über verfügbare Titel, neu normiert)
        if rets:
            wtot = sum(w for _, w in rets) or 1
            port = sum(r * w for r, w in rets) / wtot
            colr = "#5fbf7f" if port >= 0 else "#d9776a"
            if years >= 1.0:
                port_pa = annualize(port)
                colp = "#5fbf7f" if port_pa >= 0 else "#d9776a"
                pa_html = (f'&nbsp;·&nbsp; p.a. <span style="color:{colp};'
                           f'font-weight:700;font-size:1.15em;">{port_pa:+.1f} %</span>')
            else:
                pa_html = ('&nbsp;·&nbsp; <span style="color:#8899AA;">p.a. erst ab '
                           '~1 Jahr Haltedauer</span>')
            st.markdown(
                f'<div class="callout"><b>F13-Portfolio {sel_q} → heute'
                f'{f" ({prices_asof})" if prices_asof else ""}:</b> &nbsp;'
                f'Gesamt <span style="color:{colr};font-weight:700;font-size:1.15em;">'
                f'{port:+.1f} %</span>{pa_html} &nbsp; '
                f'(Haltedauer ~{years:.1f} J., {method_bt}, {len(rets)} Titel). '
                f'Kurseffekt ohne Dividenden.</div>', unsafe_allow_html=True)

            # Vergleich mit Indizes (S&P 500, Nasdaq 100) über denselben Zeitraum
            benchmarks = data.get("benchmarks", {})

            def bench_ret(name):
                b = benchmarks.get(name)
                if not b:
                    return None
                q0 = b.get("quarters", {}).get(sel_q)
                cur = b.get("current")
                return (cur - q0) / q0 * 100 if (q0 and cur) else None

            sp, nd = bench_ret("S&P 500"), bench_ret("Nasdaq 100")
            if sp is not None or nd is not None:
                st.markdown("#### Vergleich mit dem Markt (gleicher Zeitraum)")
                comp = [("F13-Portfolio", port, GOLD)]
                if sp is not None:
                    comp.append(("S&P 500", sp, SLATE))
                if nd is not None:
                    comp.append(("Nasdaq 100", nd, "#6b8caa"))
                comp_s = sorted(comp, key=lambda x: x[1])  # höchster oben (horizontal)
                figc = go.Figure(go.Bar(
                    x=[c[1] for c in comp_s], y=[c[0] for c in comp_s], orientation="h",
                    marker=dict(color=[c[2] for c in comp_s],
                                line=dict(color=MIDNIGHT, width=1)),
                    text=[f"<b>{c[1]:+.1f} %</b>" for c in comp_s], textposition="outside",
                    textfont=dict(color=OFFWHITE, family="Arial", size=15),
                    hovertemplate="%{y}: %{x:+.1f} %<extra></extra>", cliponaxis=False))
                figc.update_layout(
                    paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                    font=dict(color=OFFWHITE, family="Arial"),
                    xaxis=dict(gridcolor="#1a3a5c", title="Rendite gesamt (%)",
                               zeroline=True, zerolinecolor="#33475c"),
                    yaxis=dict(tickfont=dict(size=13)),
                    height=180, margin=dict(l=10, r=60, t=10, b=34), showlegend=False)
                st.plotly_chart(figc, use_container_width=True)

                bits = []
                for name, val in (("S&P 500", sp), ("Nasdaq 100", nd)):
                    if val is not None:
                        d = port - val
                        word = "schlägt" if d >= 0 else "liegt hinter"
                        col = "#5fbf7f" if d >= 0 else "#d9776a"
                        bits.append(f'{word} den {name} um '
                                    f'<span style="color:{col};font-weight:700;">'
                                    f'{abs(d):.1f} pp</span>')
                st.markdown(
                    f'<div class="callout">Das <b>F13-Portfolio</b> ({port:+.1f} %) '
                    f'{" und ".join(bits)}.</div>', unsafe_allow_html=True)
                st.caption("Indizes = Kursindex ohne Dividenden, Startpunkt = Schlusskurs "
                           "zum selben Quartalsende. pp = Prozentpunkte.")

        if excluded:
            st.caption(f"⚠ {excluded} Titel wegen unplausiblem Kursverhältnis "
                       "(z. B. Aktienklassen-Mismatch) aus der Renditeberechnung "
                       "ausgeschlossen.")
        df_bt = pd.DataFrame(rows)
        st.dataframe(df_bt, use_container_width=True, hide_index=True,
                     height=min(620, 45 + 35 * len(df_bt)))

        chart = []
        for e in entries:
            p0 = e["price"]
            pn = prices.get(e["ticker"], {}).get("price")
            if p0 and pn and 0.02 <= pn / p0 <= 50:
                chart.append((e["ticker"] or e["name"][:10], (pn - p0) / p0 * 100))
        chart.sort(key=lambda x: x[1])
        if chart:
            fig_bt = go.Figure(go.Bar(
                x=[c[1] for c in chart], y=[c[0] for c in chart], orientation="h",
                marker_color=["#d9776a" if c[1] < 0 else "#5fbf7f" for c in chart],
                text=[f"{c[1]:+.0f}%" for c in chart], textposition="outside",
                textfont=dict(color=OFFWHITE, family="Courier New")))
            fig_bt.update_layout(
                title=f"Rendite je Titel seit {sel_q}",
                paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                font=dict(color=OFFWHITE), xaxis=dict(gridcolor="#1a3a5c", title="Rendite %"),
                yaxis=dict(gridcolor="#1a3a5c"),
                height=max(300, 26 * len(chart)), margin=dict(l=10, r=40, t=50, b=10))
            st.plotly_chart(fig_bt, use_container_width=True)

        # Sektor-Zusammensetzung der F13-Liste ZU DIESEM Quartal
        tsec = {}
        for r in data.get("ranking", []):
            if r.get("ticker"):
                tsec.setdefault(r["ticker"], r.get("sector", "Sonstige"))
        for _inv in data["investors"]:
            for _h in _inv.get("holdings", []):
                if _h.get("ticker"):
                    tsec.setdefault(_h["ticker"], _h.get("sector", "Sonstige"))
        sec_ct = Counter(
            (e.get("sector") or tsec.get(e["ticker"], "Sonstige")) for e in entries)
        if sec_ct:
            st.markdown(f"#### Sektor-Zusammensetzung der F13-Liste zum {sel_q}")
            st.plotly_chart(make_donut(sec_ct, f"Nach Sektor · {sel_q}"),
                            use_container_width=True)
            biggest = sec_ct.most_common(1)[0]
            st.caption(f"So war die F13-Konsensliste zum Meldequartal {sel_q} nach "
                       f"Sektoren zusammengesetzt (größter Block: {biggest[0]}, "
                       f"{biggest[1]} von {len(entries)} Titeln). Vergleiche das mit der "
                       "aktuellen „Struktur\"-Ansicht, um Verschiebungen über die Zeit zu sehen.")

        st.caption("Rendite gesamt = über den ganzen Zeitraum · Rendite p.a. = auf ein "
                   "Jahr annualisiert (nur ab ~1 Jahr Haltedauer). Kurse = split-bereinigte "
                   "Schlusskurse (Yahoo), Startpunkt = Quartalsende. Reine Kursrendite ohne "
                   "Dividenden/Gebühren. Keine Anlageberatung.")

        # ── Advanced Backtest: frei wählbarer Zeitraum (Start → Ende) ──────────
        st.markdown("---")
        with st.expander("⚙️ Advanced Backtest — frei wählbarer Zeitraum "
                         "(Start- → Endquartal)"):
            qp = data.get("quarterPrices", {})
            all_q = [h["quarter"] for h in history]  # aufsteigend
            bench = data.get("benchmarks", {})
            if len(all_q) < 2 or not qp:
                st.info("Zu wenig Historie für einen Zeitraum-Backtest.")
            else:
                TODAY_OPT = "Heute (aktuelle Kurse)"
                a1, a2, a3 = st.columns(3)
                start_q = a1.selectbox("Startquartal", all_q[:-1], index=0, key="adv_s")
                end_opts = [q for q in all_q if q > start_q] + [TODAY_OPT]
                # Default = jüngstes Quartal; "Heute" nur bei expliziter Auswahl
                end_q = a2.selectbox("Endquartal", end_opts,
                                     index=max(len(end_opts) - 2, 0), key="adv_e")
                method_a = a3.radio("Gewichtung", ["Equal Weight", "Conviction (Profi)"],
                                    horizontal=True, key="adv_m")
                n_a = st.number_input("Anzahl Titel (Top N)", 5, 20, data["topN"], 1,
                                      key="adv_n")

                use_today = end_q == TODAY_OPT
                prices_now = data.get("prices", {}) or {}
                asof_now = (data.get("pricesAsOf") or date.today().isoformat())[:10]
                end_label = f"heute ({asof_now})" if use_today else end_q

                snap_s = next(h for h in history if h["quarter"] == start_q)
                entries_a = list(snap_s["ranking"])[:int(n_a)]

                def _pd2(s):
                    y, m, d = map(int, s.split("-"))
                    return date(y, m, d)
                end_date_s = asof_now if use_today else end_q
                yrs_a = max((_pd2(end_date_s) - _pd2(start_q)).days / 365.25, 1e-6)

                rows_a, rets_a, exc_a = [], [], 0
                counts_a = [max(e["count"], 0) for e in entries_a]
                csum = sum(counts_a) or 1
                for i, e in enumerate(entries_a):
                    t = e["ticker"]
                    p0 = qp.get(t, {}).get(start_q) or e.get("price")
                    p1 = ((prices_now.get(t) or {}).get("price") if use_today
                          else qp.get(t, {}).get(end_q))
                    ok = bool(p0 and p1 and 0.02 <= p1 / p0 <= 50)
                    r = (p1 - p0) / p0 * 100 if ok else None
                    w = (1 / len(entries_a) if method_a.startswith("Equal")
                         else counts_a[i] / csum)
                    if r is not None:
                        rets_a.append((r, w))
                    elif p0 and p1 is None:
                        exc_a += 1
                    rows_a.append({
                        "Ticker": t or "–", "Aktie": e["name"],
                        f"Kurs {start_q}": f"{p0:,.2f} $".replace(",", ".") if p0 else "–",
                        f"Kurs {end_label}": f"{p1:,.2f} $".replace(",", ".") if p1 else "–",
                        "Rendite": f"{r:+.1f} %" if r is not None else "–",
                        "Gewicht": f"{w*100:.1f} %"})

                def bwin(name):
                    b = bench.get(name, {})
                    q0 = b.get("quarters", {}).get(start_q)
                    q1 = b.get("current") if use_today else b.get("quarters", {}).get(end_q)
                    return (q1 - q0) / q0 * 100 if (q0 and q1) else None

                spw, ndw = bwin("S&P 500"), bwin("Nasdaq 100")
                if rets_a:
                    wt = sum(w for _, w in rets_a) or 1
                    port_a = sum(r * w for r, w in rets_a) / wt
                    pa_a = ((1 + port_a / 100) ** (1 / yrs_a) - 1) * 100 if yrs_a >= 1 else None
                    colr = "#5fbf7f" if port_a >= 0 else "#d9776a"
                    st.markdown(
                        f'<div class="callout"><b>F13-Portfolio {start_q} → {end_label}:</b> '
                        f'<span style="color:{colr};font-weight:700;font-size:1.1em;">'
                        f'{port_a:+.1f} %</span>'
                        f'{f" · p.a. {pa_a:+.1f} %" if pa_a is not None else ""} '
                        f'({method_a}, ~{yrs_a:.1f} J., {len(rets_a)} Titel). '
                        f'Kurseffekt ohne Dividenden.</div>', unsafe_allow_html=True)
                    comp = [("F13-Portfolio", port_a, GOLD)]
                    if spw is not None:
                        comp.append(("S&P 500", spw, SLATE))
                    if ndw is not None:
                        comp.append(("Nasdaq 100", ndw, "#6b8caa"))
                    cs = sorted(comp, key=lambda x: x[1])
                    fc = go.Figure(go.Bar(
                        x=[c[1] for c in cs], y=[c[0] for c in cs], orientation="h",
                        marker=dict(color=[c[2] for c in cs],
                                    line=dict(color=MIDNIGHT, width=1)),
                        text=[f"<b>{c[1]:+.1f} %</b>" for c in cs], textposition="outside",
                        textfont=dict(color=OFFWHITE, size=14), cliponaxis=False))
                    fc.update_layout(
                        paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                        font=dict(color=OFFWHITE),
                        xaxis=dict(gridcolor="#1a3a5c", title="Rendite (%)",
                                   zeroline=True, zerolinecolor="#33475c"),
                        height=175, margin=dict(l=10, r=60, t=10, b=32), showlegend=False)
                    st.plotly_chart(fc, use_container_width=True)
                else:
                    st.info("Keine Titel mit Kursdaten in diesem Zeitraum.")
                if exc_a:
                    st.caption(f"⚠ {exc_a} Titel ohne Kurs zum Endzeitpunkt ausgeschlossen.")
                st.dataframe(pd.DataFrame(rows_a), use_container_width=True,
                             hide_index=True, height=min(560, 45 + 34 * len(rows_a)))
                st.caption("Zeitraum-Backtest: F13-Liste des Startquartals, gehalten bis zum "
                           "Endquartal bzw. bis heute (split-bereinigte Kurse; „Heute“ nutzt "
                           "die zuletzt importierten Tageskurse). Reine Kursrendite ohne "
                           "Dividenden.")


def compute_weights(method, titles):
    """Gibt Gewichte (0..1) je Titel für die gewählte Methode zurück."""
    m = len(titles)
    if m == 0:
        return []
    if method.startswith("Equal"):
        return [1 / m] * m
    # Conviction: Gewicht proportional zur Investorenzahl (Überzeugung)
    counts = [max(t["count"], 0) for t in titles]
    tot = sum(counts) or 1
    return [c / tot for c in counts]


# --- Tab 3: Rechner ---
if page == "🧮 Investment-Rechner":
    st.markdown("### Investment-Rechner")
    method = st.radio(
        "Gewichtungsmethode",
        ["Equal Weight (Standard)", "Conviction (Profi)"],
        horizontal=True,
        help="Equal Weight: jede Aktie gleich. Conviction: mehr Gewicht für Titel, "
             "die mehr Investoren halten.")
    is_conviction = method.startswith("Conviction")

    ic1, ic2 = st.columns([1, 2])
    with ic1:
        capital = st.number_input(
            "Investitionsvolumen (€)", min_value=0, value=15000, step=500,
            help="Betrag eingeben — die Verteilung berechnet sich sofort neu.")
    with ic2:
        n_titles = st.number_input(
            "Anzahl Aktien", min_value=1,
            max_value=max(1, len(ranking)) if ranking else 1,
            value=min(data["topN"], len(ranking)) if ranking else 1, step=1,
            help="Auf wie viele der obersten Konsens-Titel wird verteilt? Standard: 15.")

    if is_conviction:
        st.markdown(
            '<div class="callout" style="border-left-color:#C9A84C;">'
            '<b>Conviction (Profi):</b> Aktien mit mehr Investoren-Überzeugung '
            'bekommen mehr Gewicht → höheres Renditepotenzial, aber <b>höheres '
            'Klumpenrisiko</b>. Für Einsteiger empfiehlt sich Equal Weight. '
            'Rebalancing einmal jährlich.</div>', unsafe_allow_html=True)
    st.write("")

    n = int(min(n_titles, len(ranking)))
    if n == 0:
        st.info("Keine Titel mit diesen Filtern.")
    else:
        titles = ranking[:n]
        weights = compute_weights(method, titles)
        amounts = [capital * w for w in weights]

        if method.startswith("Equal"):
            summary = (f"Bei <b>{capital:,.0f} €</b> auf <b>{n}</b> Aktien "
                       f"gleichgewichtet → <b>ca. {capital/n:,.0f} €</b> pro Aktie "
                       f"({100/n:.2f} % je Position).")
        else:
            wmin, wmax = min(weights) * 100, max(weights) * 100
            summary = (f"Bei <b>{capital:,.0f} €</b> auf <b>{n}</b> Aktien nach "
                       f"Überzeugung gewichtet → Gewichte von <b>{wmin:.1f} %</b> "
                       f"(schwächster) bis <b>{wmax:.1f} %</b> (stärkster Titel).")
        st.markdown(f'<div class="callout">{summary}</div>'.replace(",", "."),
                    unsafe_allow_html=True)
        st.write("")

        prices = data.get("prices", {})
        calc_rows = []
        for i, t in enumerate(titles):
            row = {"Nr.": i + 1, "Ticker": t.get("ticker") or "–", "Aktie": t["name"]}
            if is_conviction:  # Konsens treibt nur bei Conviction die Gewichtung
                row["Konsens"] = f"{t['count']} / {len(selected)}"
            row["Gewicht"] = f"{weights[i]*100:.2f} %"
            row["Betrag"] = f"{de_num(amounts[i], 0)} €"
            px = prices.get(t.get("ticker", ""), {}).get("price")
            if px:
                shares = amounts[i] * EURUSD / px  # € → $ umrechnen, dann / Kurs
                row["Kurs"] = f"{de_num(px)} $"
                row["Anzahl Aktien"] = de_num(shares)
            else:
                row["Kurs"] = "–"
                row["Anzahl Aktien"] = "–"
            calc_rows.append(row)
        df_calc = pd.DataFrame(calc_rows)
        st.dataframe(df_calc, use_container_width=True, hide_index=True,
                     height=min(760, 45 + 35 * n))
        tag = "equal" if method.startswith("Equal") else "conviction"
        st.download_button("⬇ Kaufliste als CSV",
                           df_calc.to_csv(index=False).encode("utf-8"),
                           f"F13-Kaufliste_{tag}_{quarter}.csv", "text/csv")
        st.caption(f"Anzahl Aktien = Betrag (€ → $ zu {de_num(EURUSD, 4)}) ÷ aktueller "
                   f"Kurs; Bruchstücke sind bei vielen Brokern handelbar, sonst abrunden. "
                   f"Kurse Stand {EURUSD_ASOF or (data.get('pricesAsOf') or '–')}. "
                   f"13F-Daten sind bis zu 45 Tage alt (Quartalslag) und ein Signal, kein "
                   f"Echtzeit-Kaufsignal. Keine Anlageberatung.")

# --- Tab 4: Struktur ---
if page == "🧩 Struktur":
    if not ranking:
        st.info("Keine Titel mit diesen Filtern.")
    else:
        n_struct = min(data["topN"], len(ranking))
        base = ranking[:n_struct]
        st.markdown(f"### Struktur der F13-Liste (Top {n_struct}, gleichgewichtet)")
        st.caption("Zeigt Klumpenrisiken: Verteilung der gleichgewichteten "
                   "F13-Titel nach Sektor und Region.")
        pie_colors = ["#C9A84C", "#0D2238", "#8899AA", "#5a7a9a", "#a8863a",
                      "#3d5a75", "#c0b088", "#6b8caa", "#8a6d2f", "#d4c9b0"]

        def pie(counter, title):
            # Nach Häufigkeit sortiert, damit Legende & Farben konsistent sind
            items = counter.most_common()
            labels = [k for k, _ in items]
            values = [v for _, v in items]
            f = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.5, sort=False,
                marker=dict(colors=pie_colors[:len(labels)],
                            line=dict(color=MIDNIGHT, width=1)),
                textinfo="percent", textposition="inside",
                insidetextorientation="horizontal",
                textfont=dict(color=OFFWHITE, family="Arial", size=13),
                hovertemplate="%{label}: %{value} Titel (%{percent})<extra></extra>"))
            f.update_layout(
                title=dict(text=title, x=0.5, xanchor="center"),
                paper_bgcolor=MIDNIGHT, font=dict(color=OFFWHITE),
                showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.05,
                            xanchor="center", x=0.5, font=dict(size=11)),
                height=400, margin=dict(l=10, r=10, t=50, b=10))
            return f

        sec_ct = Counter(r.get("sector", "Sonstige") for r in base)
        reg_ct = Counter(r.get("region", "–") for r in base)
        pc1, pc2 = st.columns(2)
        pc1.plotly_chart(pie(sec_ct, "Nach Sektor"), use_container_width=True)
        pc2.plotly_chart(pie(reg_ct, "Nach Region"), use_container_width=True)

        biggest = sec_ct.most_common(1)[0]
        st.markdown(
            f'<div class="callout">Größter Block: <b>{biggest[0]}</b> mit '
            f'<b>{biggest[1]} von {n_struct}</b> Titeln '
            f'({100*biggest[1]/n_struct:.0f} %). Je höher ein einzelner Block, '
            f'desto größer das Klumpenrisiko.</div>', unsafe_allow_html=True)

# --- Tab 5: Investoren ---
if page == "👤 Investoren-Details":
    st.caption("Veränderungen im Titel beziehen sich auf das Vorquartal "
               f"({prev_quarter or 'n/a'}).")
    for inv in data["investors"]:
        if inv["person"] not in selected:
            continue
        fdate = datetime.strptime(inv["filingDate"], "%Y-%m-%d").strftime("%d.%m.%Y")
        picks = [h for h in inv.get("holdings", [])
                 if include_etfs or not h["isEtf"]][:top_n_per_inv]
        # Zusammenfassung ALLER Veränderungen (nicht nur Verkäufe)
        cc = Counter(h.get("change", "") for h in picks)
        sold_n = len(inv.get("sold", []))
        parts = []
        if cc.get("NEU"):
            parts.append(f"🟢 {cc['NEU']} neu")
        if cc.get("AUFGESTOCKT"):
            parts.append(f"🔼 {cc['AUFGESTOCKT']} aufgestockt")
        if cc.get("REDUZIERT"):
            parts.append(f"🔽 {cc['REDUZIERT']} reduziert")
        if sold_n:
            parts.append(f"🔴 {sold_n} verkauft")
        change_summary = ("  ·  " + "  ·  ".join(parts)) if parts else "  ·  unverändert"
        with st.expander(
            f"{inv['person']} — {inv['firm']}  ·  {fmt_money(inv['portfolioValue'])}  "
            f"·  Filing {fdate} ({inv['form']}){change_summary}"
        ):
            qh = inv.get("quartersHist") or []
            qdates = [q["d"] for q in qh][::-1]  # neueste zuerst

            # Quartalsfilter: Standard = aktuelles Meldequartal
            sel_q = inv["reportDate"]
            if len(qdates) > 1:
                sel_q = st.selectbox(
                    "Quartal", qdates, index=0,
                    format_func=lambda d: datetime.strptime(d, "%Y-%m-%d")
                    .strftime("%d.%m.%Y") + ("  (aktuell)" if d == inv["reportDate"] else ""),
                    key=f"qsel_{inv['cik']}")

            if sel_q == inv["reportDate"] or not qh:
                df = pd.DataFrame([{
                    "Ticker": p.get("ticker") or "–",
                    "Position": p["name"] + ("  ⓔ" if p["isEtf"] else ""),
                    "Gewicht": f"{p['weight']:.1f} %",
                    "Wert": fmt_money(p["value"]),
                    "Veränderung": CHANGE_BADGE.get(p.get("change", ""), "–"),
                } for p in picks])
                st.dataframe(df, use_container_width=True, hide_index=True)
                if sold_n:
                    st.caption("Im Vorquartal gehalten, jetzt verkauft: "
                               + ", ".join(f"{s['name']}" for s in inv["sold"]))
            else:
                qsnap = next(q for q in qh if q["d"] == sel_q)
                df = pd.DataFrame([{
                    "Ticker": p.get("t") or "–",
                    "Position": p["n"],
                    "Gewicht": f"{p['w']:.1f} %",
                    "Wert": fmt_money(p["v"]),
                } for p in qsnap["top"]])
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"Top 10 zum {datetime.strptime(sel_q, '%Y-%m-%d').strftime('%d.%m.%Y')} "
                           f"· Portfoliowert damals: {fmt_money(qsnap['total'])} · "
                           f"Veränderungs-Badges gibt es nur im aktuellen Quartal.")

            # Verlaufs-Charts nur auf Wunsch rendern: st.expander legt Inhalte
            # IMMER ins DOM — 84 Plotly-Charts würden den Tab ausbremsen.
            show_viz = st.toggle("📈 Bestandsentwicklung & Netto-Flows anzeigen",
                                 key=f"hviz_{inv['cik']}")

            # Bestandsentwicklung: Top-Positionen über die Zeit
            if show_viz and len(qh) >= 2:
                series, names_by_key = {}, {}
                for q in qh:
                    for p in q["top"]:
                        series.setdefault(p["k"], {})[q["d"]] = p["v"]
                        names_by_key[p["k"]] = p["t"] or p["n"][:18]
                top_keys = sorted(series, key=lambda k: -max(series[k].values()))[:8]
                dates = [q["d"] for q in qh]
                unit, ulabel = (1e9, "Mrd USD") if max(
                    q["total"] for q in qh) >= 2e9 else (1e6, "Mio USD")
                palette = [GOLD, "#8899AA", "#5FA97C", "#C25E5E", "#6b8caa",
                           "#a8863a", "#d4c9b0", "#3d7a9a"]
                fig_h = go.Figure()
                for i, k in enumerate(top_keys):
                    fig_h.add_scatter(
                        x=dates, y=[(series[k][d] / unit if d in series[k] else None)
                                    for d in dates],
                        mode="lines+markers", name=names_by_key[k],
                        connectgaps=False,
                        line=dict(color=palette[i % len(palette)], width=2),
                        marker=dict(size=5))
                fig_h.update_layout(
                    title=f"Bestandsentwicklung der größten Positionen ({ulabel})",
                    paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                    font=dict(color=OFFWHITE, family="Arial"),
                    xaxis=dict(gridcolor="#1a3a5c"),
                    yaxis=dict(gridcolor="#1a3a5c", title=ulabel),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10)),
                    height=380, margin=dict(l=10, r=10, t=90, b=10),
                )
                st.plotly_chart(fig_h, use_container_width=True,
                                key=f"hist_{inv['cik']}")
                st.caption("Wert der jeweiligen Position zum Quartalsende (13F). "
                           "Lücken/Enden = Position war nicht (mehr) unter den Top 10 "
                           "des Quartals — ein endender Verlauf zeigt Verkauf oder Abstieg.")

            # Netto-Flow je Quartal (Proxy) — kauft oder verkauft dieser Investor?
            inv_flows = (data.get("flows") or {}).get(inv["person"]) or []
            if show_viz and inv_flows:
                fig_f = go.Figure(go.Bar(
                    x=[s["to"] for s in inv_flows],
                    y=[s["flowPct"] for s in inv_flows],
                    marker_color=["#C25E5E" if s["flowPct"] < 0 else "#5FA97C"
                                  for s in inv_flows],
                    hovertemplate="Quartal bis %{x}<br>Netto-Flow: %{y:.1f} %"
                                  "<extra></extra>",
                ))
                fig_f.update_layout(
                    title="Netto-Käufe / -Verkäufe je Quartal (% des Portfolios, Proxy)",
                    paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                    font=dict(color=OFFWHITE, family="Arial"),
                    xaxis=dict(gridcolor="#1a3a5c"),
                    yaxis=dict(gridcolor="#1a3a5c", title="%", zerolinecolor=GOLD),
                    height=260, margin=dict(l=10, r=10, t=50, b=10),
                )
                st.plotly_chart(fig_f, use_container_width=True,
                                key=f"flow_{inv['cik']}")
                st.caption("Schätzung aus 13F-Daten (Details & Methodik im Bereich "
                           "„💰 Cash & Flows“). Rot = netto verkauft, grün = netto gekauft.")

# --- Tab 8: Neue Meldungen (Filing-Tracker) ---
if page == "🆕 Neue Meldungen":
    invs = data["investors"]
    target_q = rel_qe.strftime("%Y-%m-%d") if rel_qe else None
    st.markdown("### Neue Meldungen — Filing-Tracker")
    if not target_q or not invs:
        st.info("Kein Meldefenster bestimmbar.")
    else:
        filed = [i for i in invs if i["reportDate"] >= target_q]
        n_all = len(invs)
        st.markdown(
            f'<div class="callout"><b>Aktuelles Meldefenster: {rel_label}</b> '
            f'(Quartalsende {rel_qe.strftime("%d.%m.%Y")}, Frist '
            f'<b>{rel_deadline.strftime("%d.%m.%Y")}</b>). Bereits eingereicht: '
            f'<b>{len(filed)} von {n_all}</b> Investoren. 13F-Meldungen treffen über das '
            f'45-Tage-Fenster laufend ein — mit jedem Tagesimport kommen neue hinzu.</div>',
            unsafe_allow_html=True)
        st.progress(len(filed) / n_all if n_all else 0.0)

        tc1, tc2 = st.columns(2)
        only_open = tc1.toggle("Nur ausstehende Meldungen", value=False,
                               help="Zeigt nur Investoren, deren aktuelle Meldung noch fehlt.")
        only_super = tc2.toggle("Nur Super-Investoren (15)", value=False)

        def _de(iso):
            try:
                return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
            except Exception:
                return iso or "–"

        rows = []
        for i in invs:
            has = i["reportDate"] >= target_q
            is_super = i.get("group") == "super15"
            if only_open and has:
                continue
            if only_super and not is_super:
                continue
            rows.append({
                "Status": "✅" if has else "❌",
                "Investor": i["person"] + (" ★" if is_super else ""),
                "Gemeldetes Quartal": _de(i["reportDate"]),
                "Eingereicht am": _de(i["filingDate"]),
                "_has": has, "_fd": i["filingDate"] or "",
            })
        # Neu Eingereichte zuerst, dann nach jüngstem Einreichungsdatum
        rows.sort(key=lambda r: (r["_has"], r["_fd"]), reverse=True)
        df_new = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                               for r in rows])
        st.dataframe(df_new, use_container_width=True, hide_index=True,
                     height=min(760, 45 + 33 * len(df_new)))
        st.caption("✅ = hat für das aktuelle Meldequartal bereits ein 13F eingereicht · "
                   "❌ = Meldung steht noch aus · ★ = Super-Investor (PDF-15). "
                   "Sortiert nach jüngstem Einreichungsdatum — neu eingegangene Meldungen "
                   "rücken bei jedem Tagesimport nach oben.")

# --- Tab 9: Cash & Flows ---
if page == "💰 Cash & Flows":
    cash_data = data.get("cash", {}) or {}
    flows_data = data.get("flows", {}) or {}
    POS_GREEN, NEG_RED = "#5FA97C", "#C25E5E"

    def mrd(v):
        return (f"{v/1e9:,.1f}".replace(",", "X").replace(".", ",")
                .replace("X", ".") + " Mrd $")

    def _dd(iso):
        try:
            return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            return iso or "–"

    def source_line(quelle_html, stand):
        st.markdown(
            f'<div class="mono" style="color:{SLATE};font-size:0.78rem;'
            f'margin:-4px 0 12px;"><b>Quelle:</b> {quelle_html}'
            f'&nbsp;·&nbsp; <b>Stand der Daten:</b> {stand}</div>',
            unsafe_allow_html=True)

    def info_link(url, title):
        return (f'<a href="{url}" target="_blank" title="{title}" '
                f'style="text-decoration:none;color:{GOLD};font-weight:700;">ⓘ</a>')

    def section_desc(html):
        st.markdown(
            f'<div style="color:{SLATE};font-size:0.9rem;line-height:1.55;'
            f'margin:-2px 0 14px;max-width:920px;">{html}</div>',
            unsafe_allow_html=True)

    st.markdown(
        f'<div class="callout"><b>Warum zwei Datenarten?</b> 13F-Meldungen enthalten '
        f'<b>kein Cash</b> — nur US-Long-Aktienpositionen. Echte Cash-Bestände gibt es '
        f'nur für börsennotierte Vehikel aus deren Quartalsberichten (unten: Berkshire, '
        f'Icahn Enterprises). Für alle übrigen Investoren zeigt der <b>Netto-Flow-Proxy</b>, '
        f'ob im Quartal per Saldo Aktien ge- oder verkauft wurden: Netto-Verkäufe deuten '
        f'auf Cash-Aufbau hin, sind aber von Anleger-Abflüssen nicht unterscheidbar.</div>',
        unsafe_allow_html=True)
    st.write("")

    # ── 1) Gemessene Cash-Bestände (börsennotierte Vehikel) ──────────────────
    st.subheader("Gemessene Cash-Bestände — Quartalsberichte (10-Q/10-K)")
    if not cash_data:
        st.info("Noch keine Cash-Daten im Datenbestand — bitte das Daten-Update "
                "(f13_update.py) einmal ausführen.")
    else:
        links = " · ".join(
            f'{c["label"].split(" (")[0]} ' + info_link(
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&CIK={c.get('cik', '')}&type=10&dateb=&owner=include&count=20",
                f"Zur Originalquelle: SEC EDGAR Quartals-/Jahresberichte — {c['label']}")
            for c in cash_data.values() if c.get("series"))
        cash_asof = max(c["series"][-1]["date"]
                        for c in cash_data.values() if c.get("series"))
        source_line(f"SEC EDGAR 10-Q/10-K &nbsp;{links}",
                    f"Bilanzstichtag {_dd(cash_asof)}")
        section_desc(
            "Echte, bilanzierte Kriegskassen: Berkshire Hathaway und Icahn "
            "Enterprises veröffentlichen Cash und T-Bills quartalsweise im "
            "Geschäftsbericht — hier wird nichts geschätzt. Der wichtigste Wert ist "
            "die <b>Cash-Quote</b> (weiße Linie): der Anteil der investierbaren "
            "Mittel, der <i>nicht</i> im Aktienmarkt steckt. Steigt sie deutlich, "
            "findet Buffett zu aktuellen Preisen zu wenig Kaufenswertes.")

        # Berkshire-Cash-Quote: Cash+T-Bills ÷ (Cash+T-Bills + 13F-Aktienportfolio).
        # Erst die Quote macht den Cash-Berg über die Zeit vergleichbar — absolute
        # Beträge wachsen auch ohne Verkäufe durch operative Gewinne.
        brk_inv = next((i for i in data["investors"]
                        if i["person"] == "Warren Buffett"), None)
        eq_by_date = {q["d"]: q["total"]
                      for q in (brk_inv.get("quartersHist") if brk_inv else []) or []}
        brk = cash_data.get("Warren Buffett")
        quote_series = []
        for x in (brk.get("series") if brk else []) or []:
            eq = eq_by_date.get(x["date"])
            if eq:
                quote_series.append(
                    (x["date"], 100.0 * x["total"] / (x["total"] + eq)))

        cols = st.columns(len(cash_data) + (1 if quote_series else 0))
        for col, (person, c) in zip(cols, cash_data.items()):
            s = c.get("series") or []
            if not s:
                continue
            last = s[-1]
            prev = s[-2] if len(s) > 1 else None
            delta_txt = None
            if prev:
                d = last["total"] - prev["total"]
                delta_txt = ("+" if d >= 0 else "−") + mrd(abs(d)) + " Q/Q"
            col.metric(f"{c['label']}", mrd(last["total"]), delta=delta_txt,
                       help=f"Stichtag {_dd(last['date'])} · Quelle: {c['source']}" +
                            (" · Summe aus Cash + US-T-Bills" if last.get("tbills") else ""))
        if quote_series:
            q_last = quote_series[-1][1]
            q_prev = quote_series[-2][1] if len(quote_series) > 1 else None
            cols[len(cash_data)].metric(
                "Berkshire Cash-Quote",
                f"{q_last:.0f} %".replace(".", ","),
                delta=(f"{q_last - q_prev:+.1f} Pp Q/Q".replace(".", ",")
                       if q_prev is not None else None),
                delta_color="inverse",
                help="Cash + T-Bills im Verhältnis zu Cash + T-Bills + "
                     "13F-Aktienportfolio. Steigende Quote = Buffett findet "
                     "nichts Kaufenswertes (Bewertungssignal, kein Timing-Signal).")
        st.write("")

        brk = cash_data.get("Warren Buffett")
        if brk and brk.get("series"):
            s = brk["series"]
            dates = [x["date"] for x in s]
            fig = go.Figure()
            fig.add_bar(x=dates, y=[(x["cash"] or 0) / 1e9 for x in s],
                        name="Cash & Äquivalente", marker_color=SLATE)
            fig.add_bar(x=dates, y=[(x["tbills"] or 0) / 1e9 for x in s],
                        name="US Treasury Bills", marker_color=GOLD)
            if quote_series:
                fig.add_scatter(
                    x=[d for d, _ in quote_series],
                    y=[v for _, v in quote_series],
                    name="Cash-Quote (%)", yaxis="y2",
                    mode="lines+markers", line=dict(color=OFFWHITE, width=2.5),
                    marker=dict(size=5),
                    hovertemplate="Cash-Quote: %{y:.1f} %<extra></extra>")
            fig.update_layout(
                barmode="stack",
                title="Berkshire Hathaway — der Cash-Berg (Mrd USD) und die Cash-Quote (%)",
                paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                font=dict(color=OFFWHITE, family="Arial"),
                xaxis=dict(gridcolor="#1a3a5c"),
                yaxis=dict(gridcolor="#1a3a5c", title="Mrd USD"),
                yaxis2=dict(overlaying="y", side="right", range=[0, 100],
                            title="Cash-Quote %", showgrid=False,
                            tickfont=dict(color=OFFWHITE)),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                height=380, margin=dict(l=10, r=10, t=70, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Quelle: SEC EDGAR 10-Q/10-K (XBRL-Cash + T-Bills aus der "
                       "Konzernbilanz). Buffetts 'Cash-Berg' besteht überwiegend aus "
                       "kurzlaufenden US-Staatsanleihen (T-Bills) — beides zusammen ist "
                       "die investierbare Reserve. Die weiße Linie setzt sie ins "
                       "Verhältnis zum Aktienportfolio (13F): Erst diese Quote macht "
                       "Quartale vergleichbar, weil der absolute Bestand auch durch "
                       "operative Gewinne wächst.")

    # ── 1b) Echte Cash-Quoten der Fondsmanager (N-PORT) ───────────────────────
    nport = data.get("nportCash", {}) or {}
    if nport:
        st.divider()
        st.subheader("Cash-Quoten der Fondsmanager — N-PORT (echt gemessen)")
        np_asof = max(c["series"][-1]["d"] for c in nport.values() if c.get("series"))
        source_line(
            "SEC EDGAR N-PORT (Flaggschiff-Fonds je Manager) " + info_link(
                "https://www.sec.gov/edgar/search/#/forms=NPORT-P",
                "Zur Originalquelle: SEC EDGAR N-PORT"),
            f"Stichtage bis {_dd(np_asof)} · je Fonds unten · ~60 Tage Meldeverzug")
        section_desc(
            "Publikumsfonds müssen ihre Kasse vollständig offenlegen. Für neun "
            "Manager des Universums zeigt dieser Abschnitt die <b>echte Cash-Quote</b> "
            "ihres Flaggschiff-Fonds — inklusive Geldmarktpositionen und T-Bills, in "
            "denen viele Fonds ihre Liquidität parken. Hohe oder steigende Quoten "
            "heißen: Der Manager hält bewusst Pulver trocken, weil ihm Kaufgelegenheiten "
            "fehlen.")

        palette_np = [GOLD, "#5FA97C", "#C25E5E", "#8899AA", "#6b8caa",
                      "#a8863a", "#d4c9b0", "#3d7a9a", "#b085c9"]
        fig_np = go.Figure()
        for i, (person, c) in enumerate(sorted(
                nport.items(), key=lambda kv: -kv[1]["series"][-1]["cashPct"])):
            s = c["series"]
            fig_np.add_scatter(
                x=[x["d"] for x in s], y=[x["cashPct"] for x in s],
                mode="lines+markers", name=person,
                line=dict(color=palette_np[i % len(palette_np)], width=2),
                marker=dict(size=4),
                hovertemplate=f"<b>{person}</b> · {c['label']}"
                              "<br>%{x}: %{y:.1f} % Cash<extra></extra>")
        fig_np.update_layout(
            title="Cash-Quote je Fondsmanager (% des Fondsvermögens)",
            paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
            font=dict(color=OFFWHITE, family="Arial"),
            xaxis=dict(gridcolor="#1a3a5c"),
            yaxis=dict(gridcolor="#1a3a5c", title="% Cash", rangemode="tozero"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10)),
            height=420, margin=dict(l=10, r=10, t=90, b=10),
        )
        st.plotly_chart(fig_np, use_container_width=True)

        df_np = pd.DataFrame([{
            "Manager": person,
            "Fonds": c["label"],
            "Cash-Quote": f"{c['series'][-1]['cashPct']:.1f} %".replace(".", ","),
            "Δ Vorstichtag": (f"{c['series'][-1]['cashPct'] - c['series'][-2]['cashPct']:+.1f} Pp"
                              .replace(".", ",") if len(c["series"]) > 1 else "–"),
            "Stichtag": _dd(c["series"][-1]["d"]),
            "Quelle": ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                       f"&CIK={c['seriesId']}&type=NPORT-P&count=10"),
        } for person, c in sorted(nport.items(),
                                  key=lambda kv: -kv[1]["series"][-1]["cashPct"])])
        st.dataframe(df_np, use_container_width=True, hide_index=True,
                     column_config={"Quelle": st.column_config.LinkColumn(
                         "Quelle", display_text="EDGAR ⓘ")})
        st.caption("Cash-Quote = nicht angelegtes Cash + Geldmarkt-/Repo-Positionen "
                   "+ US-Staatsanleihen in % des Fondsvermögens (viele Fonds parken "
                   "Liquidität in T-Bills statt Cash). Der Flaggschiff-Fonds dient "
                   "als Näherung für die Positionierung des Managers. Fiskalquartale "
                   "weichen z.T. vom Kalenderquartal ab — der Stichtag zeigt den "
                   "tatsächlichen Datenstand.")

    st.divider()

    # ── 2) Netto-Flow-Proxy (alle Investoren) ─────────────────────────────────
    st.subheader("Netto-Käufe / -Verkäufe je Investor — Proxy aus 13F")
    flow_asof = max((s[-1]["to"] for s in flows_data.values() if s), default=None)
    if flow_asof:
        source_line(
            "SEC EDGAR 13F-HR (eigene Berechnung) " + info_link(
                "https://www.sec.gov/edgar/search/#/forms=13F-HR",
                "Zur Originalquelle: SEC EDGAR 13F-HR"),
            f"Meldequartale bis {_dd(flow_asof)} (13F-Meldeverzug bis 45 Tage) · "
            f"Import {generated.strftime('%d.%m.%Y %H:%M')}")
    section_desc(
        "Hedgefonds und Family Offices melden kein Cash — aber ihre 13F-Portfolios "
        "verraten, ob sie per Saldo Aktien abgebaut haben. <b>Rot</b> = im jüngsten "
        "Quartal netto verkauft (mögliches Indiz für Cash-Aufbau — oder "
        "Anleger-Abflüsse), <b>grün</b> = netto zugekauft; jeweils bereinigt um die "
        "reine Kursentwicklung. Die <b>Verkäuferquote</b> darunter verdichtet das "
        "über alle Investoren und Quartale zu einem Stimmungs-Indikator: Je höher "
        "der Balken, desto breiter der Rückzug aus US-Aktien.")

    # Diskretionäre = Eigenkapital/Family Offices/Permanent Capital: Sie KÖNNEN
    # Cash aufbauen — ihre Netto-Verkäufe sind Marktmeinung. Mandatsgebundene
    # Verwalter (SMA/Publikumsfonds) sind i.d.R. voll investiert und verwässern
    # das Signal mit Kundengeld-Flüssen.
    disc_names = {i["person"] for i in data["investors"] if i.get("discretionary")}
    only_disc = False
    if disc_names:
        only_disc = st.toggle(
            "🎯 Nur diskretionäre Investoren (Family Offices, Eigenkapital, "
            "Permanent Capital)", value=False, key="flows_disc",
            help="Kuratierte Zuordnung: " + ", ".join(sorted(disc_names)) +
                 ". Mandatsgebundene Verwalter wie Fisher oder Dodge & Cox sind "
                 "quasi immer voll investiert — ihre Flows spiegeln eher "
                 "Kundengelder als Marktmeinung.")
    flow_pool = [p for p in selected if not only_disc or p in disc_names]

    latest = []
    for person in flow_pool:
        series = flows_data.get(person) or []
        if series:
            latest.append((person, series[-1]))
    if not latest:
        st.info("Keine Flow-Daten für die aktuelle Auswahl — bitte das Daten-Update "
                "(f13_update.py) einmal ausführen.")
    else:
        latest.sort(key=lambda t: t[1]["flowPct"])
        n_sell = sum(1 for _, s in latest if s["flowPct"] < -2)
        n_buy = sum(1 for _, s in latest if s["flowPct"] > 2)
        k1, k2, k3 = st.columns(3)
        k1.metric("Netto-Verkäufer", f"{n_sell} / {len(latest)}",
                  help="Investoren mit implizitem Netto-Verkauf > 2 % des Portfolios "
                       "im jüngsten gemeldeten Quartal.")
        k2.metric("Netto-Käufer", f"{n_buy} / {len(latest)}",
                  help="Investoren mit implizitem Netto-Zukauf > 2 % des Portfolios.")
        k3.metric("Neutral", f"{len(latest) - n_sell - n_buy} / {len(latest)}")

        chart = latest[::-1]
        fig = go.Figure(go.Bar(
            x=[s["flowPct"] for _, s in chart],
            y=[p for p, _ in chart],
            orientation="h",
            marker_color=[NEG_RED if s["flowPct"] < 0 else POS_GREEN for _, s in chart],
            text=[f"{s['flowPct']:+.1f} %".replace(".", ",") for _, s in chart],
            textposition="outside", cliponaxis=False,
            textfont=dict(color=OFFWHITE, family="Courier New", size=11),
            customdata=[[mrd(s["flowUsd"]), _dd(s["from"]), _dd(s["to"])] for _, s in chart],
            hovertemplate="<b>%{y}</b><br>Netto-Flow: %{x:.1f} % (%{customdata[0]})"
                          "<br>Zeitraum: %{customdata[1]} → %{customdata[2]}"
                          "<extra></extra>",
        ))
        fig.update_layout(
            title="Impliziter Netto-Flow im jüngsten Meldequartal (% des Portfolios)",
            paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
            font=dict(color=OFFWHITE, family="Arial"),
            xaxis=dict(gridcolor="#1a3a5c", title="% des Portfoliowerts",
                       zerolinecolor=GOLD, automargin=True),
            yaxis=dict(gridcolor="#1a3a5c", tickfont=dict(size=11)),
            height=max(420, 20 * len(chart)), margin=dict(l=10, r=70, t=50, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Aggregat über die Zeit: Verkäuferquote je Quartal
        by_q = {}
        for person in flow_pool:
            for s in flows_data.get(person) or []:
                by_q.setdefault(s["to"], []).append(s["flowPct"])
        min_n = 6 if only_disc else 10
        agg = [(q, sum(1 for v in vals if v < -2) / len(vals) * 100.0, len(vals))
               for q, vals in sorted(by_q.items()) if len(vals) >= min_n]
        if agg:
            fig2 = go.Figure(go.Bar(
                x=[a[0] for a in agg], y=[a[1] for a in agg], marker_color=NEG_RED,
                customdata=[[a[2]] for a in agg],
                hovertemplate="Quartal %{x}<br>Verkäuferquote: %{y:.0f} %"
                              "<br>Investoren: %{customdata[0]}<extra></extra>",
            ))
            fig2.update_layout(
                title="Verkäuferquote je Quartal (Anteil Investoren mit Netto-Verkauf > 2 %)",
                paper_bgcolor=MIDNIGHT, plot_bgcolor=MIDNIGHT,
                font=dict(color=OFFWHITE, family="Arial"),
                xaxis=dict(gridcolor="#1a3a5c"),
                yaxis=dict(gridcolor="#1a3a5c", title="% der Investoren", range=[0, 100]),
                height=320, margin=dict(l=10, r=10, t=50, b=10),
            )
            st.plotly_chart(fig2, use_container_width=True)

        with st.expander("Details je Investor (jüngstes Quartal)"):
            df_flows = pd.DataFrame([{
                "Investor": p,
                "Zeitraum": f"{_dd(s['from'])} → {_dd(s['to'])}",
                "Portfolio": fmt_money(s["totalUsd"]),
                "Netto-Flow": ("+" if s["flowUsd"] >= 0 else "−") + fmt_money(abs(s["flowUsd"])),
                "Flow %": f"{s['flowPct']:+.1f} %".replace(".", ","),
                "Kurs-Effekt %": f"{s['ret']:+.1f} %".replace(".", ","),
                "Schätzbasis": ("eigene Positionen" if s["basis"] == "portfolio"
                                 else "S&P 500"),
            } for p, s in latest])
            st.dataframe(df_flows, use_container_width=True, hide_index=True,
                         height=min(700, 45 + 35 * len(df_flows)))
        st.caption(
            "Methodik: Netto-Flow = Portfoliowert-Änderung abzüglich des geschätzten "
            "Kurs-Effekts. Der Kurs-Effekt wird aus Positionen mit unveränderter "
            "Stückzahl geschätzt; reicht deren Abdeckung nicht (< 15 % des Portfolios), "
            "dient der S&P 500 als Näherung. Negativ = netto verkauft (Cash-Aufbau "
            "oder Anleger-Abflüsse — aus 13F nicht unterscheidbar). Erfasst nur "
            "gemeldete US-Long-Positionen; Optionen, Shorts, Anleihen und "
            "Nicht-US-Aktien bleiben unsichtbar. Kein gemessener Wert — eine Schätzung.")

    # ── Methodik-Disclaimer: Logik, Annahmen, Datenquellen ────────────────────
    CASH_METHODIK = [
        ("01 · DATENQUELLEN",
         "Alle Daten stammen aus öffentlichen Pflichtveröffentlichungen und werden "
         "täglich um 06:00 UTC automatisch aktualisiert: <b>SEC EDGAR 13F-HR</b> "
         "(US-Long-Aktienpositionen aller 42 Investoren; Meldeverzug bis 45 Tage), "
         "<b>SEC 10-Q/10-K</b> (Cash und T-Bills von Berkshire Hathaway und Icahn "
         "Enterprises aus XBRL-Daten und Konzernbilanz; ~5 Wochen Verzug), "
         "<b>SEC N-PORT</b> (Positions- und Cash-Daten der Publikumsfonds; quartalsweise "
         "öffentlich mit ~60 Tagen Verzug) sowie Yahoo Finance (S&P 500 als "
         "Vergleichsmaßstab). Fiskalquartale einzelner Fonds weichen vom "
         "Kalenderquartal ab — maßgeblich ist der je Abschnitt angezeigte Stichtag."),
        ("02 · LOGIK & ANNAHMEN",
         "<b>13F-Meldungen enthalten kein Cash.</b> Gemessene Werte gibt es daher nur, "
         "wo Vehikel selbst berichten: Berkshire/IEP (Bilanz) und Publikumsfonds "
         "(N-PORT). <b>Berkshire-Cash-Quote</b> = Cash + T-Bills ÷ (Cash + T-Bills + "
         "13F-Aktienportfolio). <b>N-PORT-Cash-Quote</b> = nicht angelegtes Cash + "
         "Geldmarkt-/Repo-Positionen + US-Staatsanleihen in % des Fondsvermögens; der "
         "Flaggschiff-Fonds dient als Näherung für den Manager. <b>Netto-Flow-Proxy</b> "
         "= Portfoliowert-Änderung minus geschätztem Kurs-Effekt (aus Positionen mit "
         "unveränderter Stückzahl; unter 15 % Abdeckung: S&P 500 als Näherung) — eine "
         "Schätzung, die Verkäufe nicht von Anleger-Abflüssen unterscheiden kann und "
         "nur gemeldete US-Long-Positionen sieht (keine Optionen, Shorts, Anleihen, "
         "Nicht-US-Aktien). Der Filter „diskretionäre Investoren“ ist eine kuratierte "
         "Zuordnung (Eigenkapital/Family Offices/Permanent Capital)."),
        ("03 · GRENZEN DER AUSSAGEKRAFT",
         "Hohe oder steigende Cash-Quoten sind ein <b>Bewertungssignal</b> („die "
         "erfahrensten Käufer finden wenig Kaufenswertes“), aber <b>kein "
         "Timing-Signal</b>: Quoten können jahrelang erhöht bleiben, bevor der Markt "
         "korrigiert — und hohe Cash-Bestände markieren historisch teils eher Böden "
         "als Tops. Mandatsgebundene Verwalter sind konstruktionsbedingt fast immer "
         "voll investiert. Alle Angaben ohne Gewähr; keine Anlageberatung — siehe "
         "Risikohinweis am Seitenende."),
    ]
    meth_sections = "".join(
        f'<div style="border-left:3px solid {GOLD};padding:2px 0 2px 16px;margin:14px 0;">'
        f'<div style="font-family:\'Courier New\',monospace;font-size:0.72rem;'
        f'letter-spacing:0.08em;color:{GOLD};margin-bottom:5px;">{label}</div>'
        f'<div style="color:{SLATE};font-size:0.82rem;line-height:1.5;">{text}</div>'
        f'</div>'
        for label, text in CASH_METHODIK)
    st.markdown(
        f'<div style="background:{NAVY};border:1px solid #1a3a5c;border-radius:10px;'
        f'padding:20px 26px;margin-top:24px;">'
        f'<div style="font-family:\'Courier New\',monospace;font-size:0.72rem;'
        f'letter-spacing:0.12em;color:{GOLD};">ⓘ METHODIK · CASH &amp; FLOWS</div>'
        f'<div style="font-size:1.5rem;font-weight:700;color:{OFFWHITE};margin:4px 0 2px;">'
        f'Logik, Annahmen &amp; <span style="color:{GOLD};">Datenquellen</span></div>'
        f'<hr style="border:none;border-top:1.5px solid {GOLD};margin:8px 0 4px;">'
        f'{meth_sections}</div>',
        unsafe_allow_html=True)

# --- Tab: Rebalancing ---
if page == "🔁 Rebalancing":
    st.markdown("### Rebalancing — Depot von einem Quartal auf ein anderes umschichten")
    history = data.get("history", [])
    prices = data.get("prices", {})
    # Nur Quartale mit auswertbarer Rangliste, aufsteigend sortiert (alt → neu)
    q_hist = sorted((h for h in history if h.get("ranking")),
                    key=lambda h: h["quarter"])
    quarters_all = [h["quarter"] for h in q_hist]
    rank_by_q = {h["quarter"]: h["ranking"] for h in q_hist}

    if len(quarters_all) < 2 or not prices:
        st.info("Für das Rebalancing werden mindestens zwei Meldequartale mit "
                "Ranglisten sowie aktuelle Kurse benötigt — bitte zuerst "
                "`python3 f13_update.py` mit aktueller Version ausführen.")
    else:
        st.caption("Du hältst die F13-Liste eines **Basisquartals** und möchtest sie "
                   "auf ein neueres **Zielquartal** umschichten. Die Frequenz "
                   "(quartalsweise, halbjährlich, jährlich) bestimmt den Abstand — "
                   "das Zielquartal lässt sich aber frei wählen.")

        FREQ_GAP = {"Quartalsweise": 1, "Halbjährlich": 2, "Jährlich": 4}
        # Sinnvolle Startwerte (nur beim ersten Rendern): Ziel = neuestes Quartal,
        # Basis = 4 Quartale davor (jährliches Rebalancing).
        if "reb_freq" not in st.session_state:
            st.session_state.reb_freq = "Jährlich"
        if "reb_target" not in st.session_state:
            st.session_state.reb_target = quarters_all[-1]
        if "reb_base" not in st.session_state:
            st.session_state.reb_base = quarters_all[max(0, len(quarters_all) - 5)]

        def _apply_freq():
            gap = FREQ_GAP[st.session_state.reb_freq]
            bi = quarters_all.index(st.session_state.reb_base)
            st.session_state.reb_target = quarters_all[min(len(quarters_all) - 1,
                                                           bi + gap)]

        r1, r2, r3 = st.columns([2, 2, 2])
        r1.radio("Rebalancing-Frequenz", list(FREQ_GAP), key="reb_freq",
                 on_change=_apply_freq,
                 help="Setzt das Zielquartal auf Basis + 1 / 2 / 4 Quartale. "
                      "Danach frei anpassbar.")
        r2.selectbox("Basisquartal (aktueller Bestand)", quarters_all,
                     key="reb_base", on_change=_apply_freq,
                     help="Stand der F13-Liste, die du derzeit hältst.")
        r3.selectbox("Zielquartal (gewünschter Berichtsmonat)", quarters_all,
                     key="reb_target",
                     help="Stand der F13-Liste, auf die du umschichten möchtest.")

        base_q = st.session_state.reb_base
        target_q = st.session_state.reb_target

        METHODS = ["Equal Weight", "Conviction (Profi)"]
        r4, r5 = st.columns([1, 1])
        pf_value = r4.number_input("Portfoliowert (€)", min_value=0, value=15000,
                                   step=500,
                                   help="Gesamtwert des Depots, das umgeschichtet wird.")
        n_rb = r5.number_input("Anzahl Titel (Top N)", 5, 30, int(data["topN"]), 1,
                               key="reb_n")
        m1, m2 = st.columns([1, 1])
        method_base = m1.radio("Methode Basisquartal (aktueller Bestand)", METHODS,
                               horizontal=True, key="reb_method_base",
                               help="Wie ist dein derzeitiger Bestand gewichtet?")
        method_target = m2.radio("Methode neues Quartal (Rebalancing-Ziel)", METHODS,
                                 horizontal=True, key="reb_method_target",
                                 help="Wie soll das umgeschichtete Depot gewichtet sein?")

        bi, ti = quarters_all.index(base_q), quarters_all.index(target_q)
        if ti <= bi:
            st.warning("Das Zielquartal muss **nach** dem Basisquartal liegen. "
                       "Bitte ein späteres Zielquartal (oder früheres Basisquartal) "
                       "wählen.")
        else:
            n = int(n_rb)
            base_list = rank_by_q[base_q][:n]
            target_list = rank_by_q[target_q][:n]
            w_base = compute_weights(method_base, base_list)
            w_target = compute_weights(method_target, target_list)

            def _tk(e):  # stabiler Schlüssel je Titel
                return e.get("ticker") or e.get("key") or e.get("name")

            # Alt-/Neu-Gewichte und Namen je Titel sammeln
            info = {}
            for e, w in zip(base_list, w_base):
                info.setdefault(_tk(e), {"name": e["name"], "ticker": e.get("ticker"),
                                         "wa": 0.0, "wn": 0.0})["wa"] = w
            for e, w in zip(target_list, w_target):
                d = info.setdefault(_tk(e), {"name": e["name"], "ticker": e.get("ticker"),
                                             "wa": 0.0, "wn": 0.0})
                d["wn"] = w
                d["name"] = e["name"]  # Zielname bevorzugen (aktueller)

            EPS = 0.005  # 0,5 %-Punkte Toleranz für "Halten"
            rows, n_out, n_in, n_adj = [], 0, 0, 0
            buy_sum = sell_sum = 0.0
            for tk, d in info.items():
                wa, wn = d["wa"], d["wn"]
                amt_a, amt_n = pf_value * wa, pf_value * wn
                d_amt = amt_n - amt_a
                if wa == 0:
                    status, n_in = "🟢 Kaufen", n_in + 1
                elif wn == 0:
                    status, n_out = "🔴 Verkaufen", n_out + 1
                elif abs(wn - wa) <= EPS:
                    status = "▪ Halten"
                elif wn > wa:
                    status, n_adj = "🔼 Aufstocken", n_adj + 1
                else:
                    status, n_adj = "🔽 Reduzieren", n_adj + 1
                px = prices.get(tk, {}).get("price")
                if px:
                    d_shares = d_amt * EURUSD / px  # € → $, dann / Kurs
                    shares_txt = f"{de_num(d_shares)}" if abs(d_shares) >= 0.005 else "0"
                    kurs_txt = f"{de_num(px)} $"
                else:
                    shares_txt, kurs_txt = "–", "–"
                if d_amt > 0:
                    buy_sum += d_amt
                elif d_amt < 0:
                    sell_sum += -d_amt
                rows.append({
                    "Aktion": status,
                    "Ticker": tk if d.get("ticker") else "–",
                    "Aktie": d["name"],
                    "Gewicht alt": f"{wa*100:.1f} %",
                    "Gewicht neu": f"{wn*100:.1f} %",
                    "Δ Betrag (€)": f"{'+' if d_amt >= 0 else '−'}{de_num(abs(d_amt), 0)}",
                    "Kurs": kurs_txt,
                    "Δ Stück": (f"{'+' if not shares_txt.startswith('-') and shares_txt != '0' else ''}"
                                f"{shares_txt}" if shares_txt not in ("–", "0")
                                else shares_txt),
                    "_sort": (0 if wn == 0 else 2 if wa == 0 else 1, -abs(d_amt)),
                })
            rows.sort(key=lambda r: r.pop("_sort"))

            # Zusammenfassung
            method_txt = (method_base if method_base == method_target
                          else f"{method_base} → {method_target}")
            st.markdown(
                f'<div class="callout"><b>{base_q} → {target_q}</b> '
                f'({method_txt}, Top {n}, {de_num(pf_value, 0)} €): &nbsp;'
                f'<span style="color:#d9776a;font-weight:700;">🔴 {n_out} raus</span> &nbsp;·&nbsp; '
                f'<span style="color:#5fbf7f;font-weight:700;">🟢 {n_in} rein</span> &nbsp;·&nbsp; '
                f'<span style="color:{GOLD};font-weight:700;">🔁 {n_adj} umgewichtet</span>. &nbsp;'
                f'Umschichtungsvolumen ca. <b>{de_num(max(buy_sum, sell_sum), 0)} €</b> '
                f'({de_num((max(buy_sum, sell_sum) / pf_value * 100) if pf_value else 0, 1)} % '
                f'des Depots).</div>'.replace(",", "."),
                unsafe_allow_html=True)
            st.write("")

            df_rb = pd.DataFrame(rows)

            def _full_height(k):
                return 45 + 35 * max(k, 1)
            st.dataframe(df_rb, use_container_width=True, hide_index=True,
                         height=min(900, _full_height(len(rows))))
            st.download_button(
                "⬇ Rebalancing-Plan als CSV",
                df_rb.to_csv(index=False).encode("utf-8"),
                f"F13-Rebalancing_{base_q}_zu_{target_q}.csv", "text/csv")
            st.caption(
                f"Δ Stück = Veränderung der Positionsgröße zu aktuellen Kursen "
                f"(€ → $ zu {de_num(EURUSD, 4)}); + = zukaufen, − = verkaufen, "
                f"Bruchstücke bei vielen Brokern handelbar. Basis- und Zielquartal "
                f"lassen sich getrennt gewichten (Equal Weight oder Conviction); bei "
                f"beidseitig Equal Weight bleiben gehaltene Titel unverändert und nur "
                f"Ab-/Zugänge werden gehandelt. Kurse Stand "
                f"{EURUSD_ASOF or (data.get('pricesAsOf') or '–')}. "
                f"13F-Daten sind bis zu 45 Tage alt (Quartalslag) und ein Signal, kein "
                f"Echtzeit-Kaufsignal. Keine Anlageberatung.")

st.markdown('<hr class="goldbar">', unsafe_allow_html=True)

# ── Risikohinweis & Haftungsausschluss (Pflichtinformation) ──────────────────
DISCLAIMER = [
    ("01 · BILDUNGSZWECKE",
     "Alle Inhalte von Björn Schnare und der BS IMPACT SCALE GmbH dienen "
     "ausschließlich Bildungs- und Informationszwecken. Sie stellen keine Finanz-, "
     "Anlage-, Steuer- oder Rechtsberatung dar. Nichts in diesem Dashboard ist als "
     "Angebot oder Aufforderung zum Kauf oder Verkauf von Aktien, Futures, Optionen "
     "oder sonstigen Finanzinstrumenten zu verstehen. Alle dargestellten Daten "
     "stammen aus öffentlichen SEC-13F-Meldungen und sind bis zu 45 Tage alt."),
    ("02 · RISIKOKAPITAL",
     "Der Handel mit Wertpapieren und Finanzinstrumenten ist mit einem erheblichen "
     "Verlustrisiko verbunden und eignet sich nicht für alle Anleger. Eingesetztes "
     "Kapital sollte ausschließlich aus verfügbarem Risikokapital bestehen – d.h. "
     "Kapital, dessen möglicher Verlust keine negativen Auswirkungen auf deinen "
     "Lebensstandard hat. Vergangene Wertentwicklungen, ob real oder hypothetisch, "
     "sind kein verlässlicher Indikator für zukünftige Ergebnisse. Du trägst die "
     "alleinige Verantwortung für deine Anlageentscheidungen."),
    ("03 · KEINE GARANTIE",
     "Die dargestellten Positionen und Auswertungen basieren auf öffentlich "
     "gemeldeten 13F-Daten und sind nicht als typische oder garantierte Resultate zu "
     "verstehen. Es werden keine Garantien oder Zusicherungen hinsichtlich der "
     "Richtigkeit, Vollständigkeit oder Zuverlässigkeit der bereitgestellten "
     "Informationen gegeben. Die BS IMPACT SCALE GmbH lehnt jede Haftung für Verluste "
     "oder Schäden ab. Alle Anlageentscheidungen erfolgen auf eigenes Risiko."),
]
sections = "".join(
    f'<div style="border-left:3px solid {GOLD};padding:2px 0 2px 16px;margin:14px 0;">'
    f'<div style="font-family:\'Courier New\',monospace;font-size:0.72rem;'
    f'letter-spacing:0.08em;color:{GOLD};margin-bottom:5px;">{label}</div>'
    f'<div style="color:{SLATE};font-size:0.82rem;line-height:1.5;">{text}</div>'
    f'</div>'
    for label, text in DISCLAIMER)
st.markdown(
    f'<div style="background:{NAVY};border:1px solid #1a3a5c;border-radius:10px;'
    f'padding:20px 26px;margin-top:8px;">'
    f'<div style="font-family:\'Courier New\',monospace;font-size:0.72rem;'
    f'letter-spacing:0.12em;color:{GOLD};">⚠ WICHTIGER HINWEIS · PFLICHTINFORMATION</div>'
    f'<div style="font-size:1.5rem;font-weight:700;color:{OFFWHITE};margin:4px 0 2px;">'
    f'Risikohinweis &amp; <span style="color:{GOLD};">Haftungsausschluss</span></div>'
    f'<hr style="border:none;border-top:1.5px solid {GOLD};margin:8px 0 4px;">'
    f'{sections}</div>',
    unsafe_allow_html=True)

st.markdown('<hr class="goldbar">', unsafe_allow_html=True)
st.markdown(
    f'<div class="mono" style="color:#334455;font-size:0.72rem;text-align:center;">'
    f'BS IMPACT SCALE GmbH © · F13-DASHBOARD · Datenquelle: SEC EDGAR (13F-HR) · '
    f'Stand {generated.strftime("%d.%m.%Y %H:%M")} · '
    f'Risikohinweis · Alle Trades auf eigenes Risiko · Kein Investment-Advice</div>',
    unsafe_allow_html=True)
