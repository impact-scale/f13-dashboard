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
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─── Konfiguration ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="F13-Liste — Super-Investoren",
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


def compute_ranking(data, selected_investors, top_n_per_inv, include_etfs):
    """Konsens-Rangliste dynamisch aus den holdings berechnen."""
    overlap = {}
    for inv in data["investors"]:
        if inv["person"] not in selected_investors:
            continue
        picks = [h for h in inv.get("holdings", []) if include_etfs or not h["isEtf"]]
        for pos in picks[:top_n_per_inv]:
            slot = overlap.setdefault(pos["key"], {
                "names": Counter(), "investors": [], "combined": 0.0, "isEtf": pos["isEtf"],
            })
            slot["names"][pos["name"]] += 1
            slot["investors"].append({
                "person": inv["person"], "weight": pos["weight"], "value": pos["value"],
            })
            slot["combined"] += pos["value"]
    ranking = [{
        "key": k, "name": s["names"].most_common(1)[0][0],
        "count": len(s["investors"]),
        "investors": sorted(s["investors"], key=lambda x: -x["value"]),
        "combined": s["combined"], "isEtf": s["isEtf"],
    } for k, s in overlap.items()]
    ranking.sort(key=lambda x: (-x["count"], -x["combined"]))
    return ranking


# ─── Kopf ─────────────────────────────────────────────────────────────────────

data = load_data()

st.markdown('<div class="tag">F13-LISTE · SUPER-INVESTOREN</div>',
            unsafe_allow_html=True)
st.markdown("# Super-Investoren Dashboard")
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
    f'</div>',
    unsafe_allow_html=True,
)
st.write("")

# ─── Sidebar-Filter ───────────────────────────────────────────────────────────

INV_KEYS = {p: f"inv_{p}" for p in all_investors}


def _toggle_all_investors():
    val = st.session_state["inv_all"]
    for k in INV_KEYS.values():
        st.session_state[k] = val


with st.sidebar:
    st.markdown('<div class="tag">FILTER</div>', unsafe_allow_html=True)
    st.markdown('<hr class="goldbar">', unsafe_allow_html=True)

    top_n_per_inv = st.slider(
        "Positionen pro Investor", 5, 25, 15,
        help="Wie viele der größten Positionen jedes Investors zählen als "
             "'Top-Pick'? Standard: Top 15.",
    )
    min_consensus = st.slider(
        "Mindest-Konsens (Investoren)", 1, 10, 2,
        help="Zeige nur Aktien, die von mindestens so vielen Investoren gehalten werden.",
    )
    include_etfs = st.toggle(
        "ETFs / Indexfonds einbeziehen", value=False,
        help="Fokus auf Einzelaktien. Standard: ETFs ausgeblendet.",
    )
    search = st.text_input("Aktie suchen", "").strip().lower()

    st.markdown('<hr class="goldbar">', unsafe_allow_html=True)
    st.markdown("**Investoren einbeziehen**")
    # Standard beim ersten Laden: alle eingeschaltet
    if "inv_all" not in st.session_state:
        st.session_state["inv_all"] = True
        for k in INV_KEYS.values():
            st.session_state[k] = True

    st.checkbox("Alle ein-/ausschalten", key="inv_all",
                on_change=_toggle_all_investors)
    st.markdown('<hr style="border-color:#1a3a5c;margin:2px 0 6px;">',
                unsafe_allow_html=True)
    for p in all_investors:
        st.checkbox(p, key=INV_KEYS[p])

    selected = [p for p in all_investors if st.session_state.get(INV_KEYS[p], True)]
    st.caption(f"{len(selected)} von {len(all_investors)} Investoren aktiv"
               " · Empfehlung: mindestens 10.")

if not selected:
    st.warning("Bitte mindestens einen Investor auswählen.")
    st.stop()

ranking = compute_ranking(data, selected, top_n_per_inv, include_etfs)
ranking = [r for r in ranking if r["count"] >= min_consensus]
if search:
    ranking = [r for r in ranking if search in r["name"].lower()]

# ─── KPI-Zeile ────────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("Investoren aktiv", f"{len(selected)} / {len(all_investors)}")
c2.metric("Meldequartal", quarter)
c3.metric("Konsens-Titel", len(ranking))
c4.metric("Daten-Stand", generated.strftime("%d.%m.%Y"))

if data.get("errors"):
    with st.expander(f"⚠ {len(data['errors'])} Investor(en) mit Ladefehlern"):
        for e in data["errors"]:
            st.write(f"- {e['investor']} — {e['error']}")

st.markdown(
    '<div class="callout"><b>So liest du die Liste:</b> Je mehr Super-Investoren '
    'dieselbe Aktie in ihren größten Positionen halten, desto stärker der Konsens. '
    'Die obersten Titel bilden deine F13-Liste zum gleichgewichteten Investieren.</div>',
    unsafe_allow_html=True,
)
st.write("")

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📊 F13-Konsensliste", "🧮 Investment-Rechner",
                            "👤 Investoren-Details"])

# --- Tab 1: Konsens ---
with tab1:
    if not ranking:
        st.info("Keine Titel mit diesen Filtern. Konsens-Schwelle senken oder mehr "
                "Investoren wählen.")
    else:
        top_chart = ranking[:20][::-1]
        fig = go.Figure(go.Bar(
            x=[r["count"] for r in top_chart],
            y=[r["name"] for r in top_chart],
            orientation="h",
            marker_color=GOLD,
            text=[f"{r['count']}" for r in top_chart],
            textposition="outside",
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

        rows = [{
            "Rang": i + 1,
            "Aktie": r["name"] + ("  ⓔ" if r["isEtf"] else ""),
            "Investoren": f"{r['count']} / {len(selected)}",
            "Gehalten von": ", ".join(inv["person"] for inv in r["investors"]),
            "Summe Wert": fmt_money(r["combined"]),
        } for i, r in enumerate(ranking)]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     height=min(560, 45 + 35 * len(rows)))
        st.caption("ⓔ = ETF / Indexfonds")

# --- Tab 2: Rechner ---
with tab2:
    st.markdown("### Investment-Rechner (Equal Weight)")
    ic1, ic2 = st.columns([1, 2])
    with ic1:
        capital = st.number_input(
            "Investitionsvolumen (€)", min_value=0, value=15000, step=500,
            help="Betrag eingeben — die Verteilung berechnet sich sofort neu.",
        )
    with ic2:
        n_titles = st.number_input(
            "Anzahl Aktien", min_value=1,
            max_value=max(1, len(ranking)) if ranking else 1,
            value=min(data["topN"], len(ranking)) if ranking else 1, step=1,
            help="Auf wie viele der obersten Konsens-Titel soll gleichmäßig "
                 "verteilt werden? Standard: 15.",
        )
    st.write("")

    n = int(min(n_titles, len(ranking)))
    if n == 0:
        st.info("Keine Titel mit diesen Filtern.")
    else:
        per = capital / n if n else 0
        st.markdown(
            f'<div class="callout">Bei <b>{capital:,.0f} €</b> auf <b>{n}</b> Aktien '
            f'gleichgewichtet → <b>ca. {per:,.0f} €</b> pro Aktie '
            f'({100/n:.2f} % je Position).</div>'.replace(",", "."),
            unsafe_allow_html=True)
        st.write("")
        rows = [{
            "Nr.": i + 1,
            "Aktie": r["name"],
            "Anteil": f"{100/n:.2f} %",
            "Betrag": f"{per:,.0f} €".replace(",", "."),
            "Konsens": f"{r['count']} / {len(selected)}",
        } for i, r in enumerate(ranking[:n])]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     height=min(620, 45 + 35 * n))
        st.caption("Equal-Weight-Methode — kein Übergewichten, keine "
                   "Bauchentscheidungen. 13F-Daten sind bis zu 45 Tage alt (Quartalslag) "
                   "und ein Signal, kein Echtzeit-Kaufsignal.")

# --- Tab 3: Investoren ---
with tab3:
    for inv in data["investors"]:
        if inv["person"] not in selected:
            continue
        fdate = datetime.strptime(inv["filingDate"], "%Y-%m-%d").strftime("%d.%m.%Y")
        with st.expander(
            f"{inv['person']} — {inv['firm']}  ·  {fmt_money(inv['portfolioValue'])}  "
            f"·  Filing {fdate} ({inv['form']})"
        ):
            picks = [h for h in inv.get("holdings", [])
                     if include_etfs or not h["isEtf"]][:top_n_per_inv]
            df = pd.DataFrame([{
                "Position": p["name"] + ("  ⓔ" if p["isEtf"] else ""),
                "Gewicht": f"{p['weight']:.1f} %",
                "Wert": fmt_money(p["value"]),
            } for p in picks])
            st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown('<hr class="goldbar">', unsafe_allow_html=True)
st.markdown(
    f'<div class="mono" style="color:#334455;font-size:0.72rem;text-align:center;">'
    f'BS IMPACT SCALE GmbH © · F13-DASHBOARD · Datenquelle: SEC EDGAR (13F-HR) · '
    f'Stand {generated.strftime("%d.%m.%Y %H:%M")} · Keine Anlageberatung</div>',
    unsafe_allow_html=True)
