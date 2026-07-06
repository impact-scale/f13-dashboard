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
generated = datetime.fromisoformat(data["generatedAt"]).astimezone()
quarter = data["investors"][0]["reportDate"] if data["investors"] else "–"
n_ok = len(data["investors"])
n_err = len(data.get("errors", []))

# Stand des Datenimports — prominent oben
st.markdown(
    f'<div class="importbar">'
    f'<span class="importdot"></span>'
    f'<b>Stand des Datenimports:</b>&nbsp; {generated.strftime("%d.%m.%Y · %H:%M Uhr")}'
    f'&nbsp;·&nbsp; {n_ok} Investoren geladen'
    f'{f"&nbsp;·&nbsp; {n_err} mit Fehler" if n_err else ""}'
    f'&nbsp;·&nbsp; Quelle: SEC EDGAR (13F-HR)'
    f'&nbsp;<a href="https://www.sec.gov/edgar/search/#/forms=13F-HR" target="_blank" '
    f'title="Zur Originalquelle: SEC EDGAR 13F-HR" '
    f'style="text-decoration:none;color:{GOLD};font-weight:700;">ⓘ</a>'
    f'</div>',
    unsafe_allow_html=True,
)
st.write("")

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

ranking = with_consensus_delta(data, selected, top_n_per_inv, include_etfs)
ranking = [r for r in ranking if r["count"] >= min_consensus]
if search:
    ranking = [r for r in ranking
               if search in r["name"].lower() or search in r.get("ticker", "").lower()]

# ─── KPI-Zeile ────────────────────────────────────────────────────────────────

rel_label, rel_qe, rel_deadline = next_13f_release()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Investoren aktiv", f"{len(selected)} / {len(all_investors)}")
c2.metric("Meldequartal", quarter)
c3.metric("Konsens-Titel", len(ranking))
c4.metric("Nächste Liste", rel_deadline.strftime("%d.%m.%Y") if rel_deadline else "–",
          help=f"Nächstes Meldequartal {rel_label} (Quartalsende "
               f"{rel_qe.strftime('%d.%m.%Y')}). 13F-Berichte sind spätestens "
               f"45 Tage nach Quartalsende fällig — dann ist die F13-Liste vollständig. "
               f"Meldungen treffen aber laufend im 45-Tage-Fenster ein." if rel_deadline else "")

if data.get("errors"):
    with st.expander(f"⚠ {len(data['errors'])} Investor(en) mit Ladefehlern"):
        for e in data["errors"]:
            st.write(f"- {e['investor']} — {e['error']}")

st.markdown(
    f'<div class="callout"><b>So liest du die Liste:</b> Je mehr Investoren dieselbe '
    f'Aktie in ihren größten Positionen halten, desto stärker der Konsens. Aktuell aus '
    f'<b>{len(all_investors)} Investoren</b> — über die Schnellauswahl links auf die '
    f'<b>15 Super-Investoren</b> oder die <b>Top 30 nach Volumen</b> eingrenzbar.</div>',
    unsafe_allow_html=True,
)
st.write("")

# ─── Tabs ─────────────────────────────────────────────────────────────────────

prev_quarter = data["investors"][0].get("prevReportDate") if data["investors"] else None
ytd_base = data["investors"][0].get("ytdBaseDate") if data["investors"] else None


def delta_str(d):
    return f"▲ +{d}" if d > 0 else (f"▼ {d}" if d < 0 else "=")


tab1, tab2, tab6, tab3, tab4, tab5, tab7 = st.tabs(
    ["📊 F13-Konsensliste", "🔄 Veränderungen", "📈 Verlauf", "🧮 Investment-Rechner",
     "🧩 Struktur", "👤 Investoren-Details", "🎯 Backtest"])

# --- Tab 1: Konsens ---
with tab1:
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
with tab2:
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
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown("**🟢 Gewinnt Investoren**")
            st.dataframe(pd.DataFrame([{
                "Ticker": r.get("ticker") or "–", "Aktie": r["name"],
                "Jetzt": r["count"], "Δ": f"+{r[dkey]}",
            } for r in gainers]) if gainers else pd.DataFrame({"—": ["keine"]}),
                hide_index=True, use_container_width=True)
        with mc2:
            st.markdown("**🔴 Verliert Investoren**")
            st.dataframe(pd.DataFrame([{
                "Ticker": r.get("ticker") or "–", "Aktie": r["name"],
                "Jetzt": r["count"], "Δ": str(r[dkey]),
            } for r in losers]) if losers else pd.DataFrame({"—": ["keine"]}),
                hide_index=True, use_container_width=True)

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
with tab6:
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
with tab7:
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
        st.caption("Rendite gesamt = über den ganzen Zeitraum · Rendite p.a. = auf ein "
                   "Jahr annualisiert (nur ab ~1 Jahr Haltedauer, da kürzere Zeiträume "
                   "hochgerechnet überzeichnen würden). Quartalskurs = Median aus 13F "
                   "(Wert ÷ Aktien) der meldenden Investoren. Aktueller Kurs = letzter "
                   "Schlusskurs (Yahoo). Reine Kursrendite ohne Dividenden/Gebühren. "
                   "Keine Anlageberatung.")


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
with tab3:
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

        calc_rows = []
        for i, t in enumerate(titles):
            row = {"Nr.": i + 1, "Ticker": t.get("ticker") or "–", "Aktie": t["name"]}
            if is_conviction:  # Konsens treibt nur bei Conviction die Gewichtung
                row["Konsens"] = f"{t['count']} / {len(selected)}"
            row["Gewicht"] = f"{weights[i]*100:.2f} %"
            row["Betrag"] = f"{amounts[i]:,.0f} €".replace(",", ".")
            calc_rows.append(row)
        df_calc = pd.DataFrame(calc_rows)
        st.dataframe(df_calc, use_container_width=True, hide_index=True,
                     height=min(620, 45 + 35 * n))
        tag = "equal" if method.startswith("Equal") else "conviction"
        st.download_button("⬇ Kaufliste als CSV",
                           df_calc.to_csv(index=False).encode("utf-8"),
                           f"F13-Kaufliste_{tag}_{quarter}.csv", "text/csv")
        st.caption("13F-Daten sind bis zu 45 Tage alt (Quartalslag) und ein Signal, "
                   "kein Echtzeit-Kaufsignal. Keine Anlageberatung.")

# --- Tab 4: Struktur ---
with tab4:
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
with tab5:
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
