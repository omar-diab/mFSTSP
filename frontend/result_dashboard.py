import json
from pathlib import Path

import pandas as pd
import streamlit as st

# =============================================================================
# Paths
# =============================================================================

FRONTEND_DIR = Path(__file__).resolve().parent
DATA_DIR = FRONTEND_DIR / "frontend_data"
MAPS_GENERATED_DIR = FRONTEND_DIR / "maps" / "generated"

COMPARISON_FILE = DATA_DIR / "comparison_all_100_full_dashboard.csv"
SUMMARY_FILE = DATA_DIR / "comparison_all_100_full_dashboard_summary.csv"
SCORECARD_FILE = DATA_DIR / "comparison_all_100_metric_scorecard.csv"

st.set_page_config(
    page_title="mFSTSP Dashboard",
    page_icon="🏆",
    layout="wide",
)

METRICS = [
    "ofv",
    "totalTime",
    "waitingTruck",
    "waitingUAV",
    "numUAVcust",
    "numTruckCust",
]

METRIC_LABELS = {
    "ofv": "OFV",
    "totalTime": "Runtime",
    "waitingTruck": "Truck Waiting",
    "waitingUAV": "UAV Waiting",
    "numUAVcust": "UAV Customers",
    "numTruckCust": "Truck Customers",
}


# =============================================================================
# Shared helpers
# =============================================================================

@st.cache_data
def load_result_data():
    if not COMPARISON_FILE.exists():
        st.error(f"Missing comparison data: {COMPARISON_FILE}")
        st.info("Run: python frontend/create_comparison_dashboard_data.py")
        st.stop()

    if not SUMMARY_FILE.exists():
        st.error(f"Missing summary data: {SUMMARY_FILE}")
        st.info("Run: python frontend/create_comparison_dashboard_data.py")
        st.stop()

    if not SCORECARD_FILE.exists():
        st.error(f"Missing scorecard data: {SCORECARD_FILE}")
        st.info("Run: python frontend/create_comparison_dashboard_data.py")
        st.stop()

    return (
        pd.read_csv(COMPARISON_FILE),
        pd.read_csv(SUMMARY_FILE),
        pd.read_csv(SCORECARD_FILE),
    )


def winner_badge(value: str) -> str:
    if value == "our":
        return "🟢 Our Win"
    if value == "their":
        return "🔴 Their Win"
    if value == "tie":
        return "🟡 Tie"
    return "⚪ Missing"


def format_value(value, decimals: int = 2):
    if pd.isna(value):
        return "—"
    try:
        numeric = float(value)
        if abs(numeric - round(numeric)) < 1e-9:
            return f"{int(round(numeric)):,}"
        return f"{numeric:,.{decimals}f}"
    except Exception:
        return str(value)


def format_percent(value):
    if pd.isna(value):
        return "—"
    return f"{float(value):.2f}%"


def metric_card(title: str, value: str, subtitle: str, state: str = "neutral"):
    border = {
        "our": "#10b981",
        "their": "#ef4444",
        "tie": "#f59e0b",
        "neutral": "#374151",
    }.get(state, "#374151")

    st.markdown(
        f"""
        <div style="
            border:1px solid {border};
            border-radius:18px;
            padding:1rem 1.1rem;
            background:#111827;
            min-height:118px;
        ">
            <div style="font-size:0.86rem;color:#9ca3af;font-weight:600;">{title}</div>
            <div style="font-size:1.7rem;color:#f9fafb;font-weight:800;margin-top:0.25rem;">{value}</div>
            <div style="font-size:0.82rem;color:#9ca3af;margin-top:0.35rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def scorecard_style(df: pd.DataFrame):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for idx in df.index:
        our = df.at[idx, "Our Wins"] if "Our Wins" in df.columns else 0
        their = df.at[idx, "Their Wins"] if "Their Wins" in df.columns else 0

        if our > their:
            styles.loc[idx, :] = "background-color:#d1fae5;color:#065f46;font-weight:700;"
        elif their > our:
            styles.loc[idx, :] = "background-color:#fee2e2;color:#991b1b;font-weight:700;"
        else:
            styles.loc[idx, :] = "background-color:#fef3c7;color:#92400e;font-weight:700;"
    return styles


def comparison_style(raw_df: pd.DataFrame):
    styles = pd.DataFrame("", index=raw_df.index, columns=raw_df.columns)

    for metric in METRICS:
        our = f"{metric}_our"
        their = f"{metric}_their"
        winner = f"{metric}_winner"

        if our not in raw_df.columns or their not in raw_df.columns or winner not in raw_df.columns:
            continue

        for idx in raw_df.index:
            result = raw_df.at[idx, winner]

            if result == "our":
                styles.at[idx, our] = "background-color:#d1fae5;color:#065f46;font-weight:700;"
                styles.at[idx, their] = "background-color:#fee2e2;color:#991b1b;font-weight:700;"
                styles.at[idx, winner] = "background-color:#d1fae5;color:#065f46;font-weight:700;"
            elif result == "their":
                styles.at[idx, our] = "background-color:#fee2e2;color:#991b1b;font-weight:700;"
                styles.at[idx, their] = "background-color:#d1fae5;color:#065f46;font-weight:700;"
                styles.at[idx, winner] = "background-color:#fee2e2;color:#991b1b;font-weight:700;"
            elif result == "tie":
                styles.at[idx, our] = "background-color:#fef3c7;color:#92400e;font-weight:700;"
                styles.at[idx, their] = "background-color:#fef3c7;color:#92400e;font-weight:700;"
                styles.at[idx, winner] = "background-color:#fef3c7;color:#92400e;font-weight:700;"

    return styles


def full_side_table(row: pd.Series, side: str) -> pd.DataFrame:
    suffix = f"_{side}"
    rows = []
    for col in row.index:
        if col.endswith(suffix):
            rows.append({"Field": col[:-len(suffix)], "Value": row[col]})
    return pd.DataFrame(rows)


# =============================================================================
# Results Dashboard Page
# =============================================================================

def render_results_page():
    comparison, summary, scorecard = load_result_data()

    st.title("🏆 mFSTSP Result Dashboard")
    st.caption("Green = winner, red = loser, yellow = tie.")

    st.sidebar.header("Result Filters")

    customer_options = sorted(comparison["numCustomers"].dropna().unique().tolist())
    selected_customers = st.sidebar.multiselect(
        "Customer count",
        options=customer_options,
        default=customer_options,
    )

    ofv_options = [v for v in ["our", "their", "tie", "missing"] if v in comparison["ofv_winner"].dropna().unique()]
    selected_ofv = st.sidebar.multiselect(
        "OFV result",
        options=ofv_options,
        default=ofv_options,
        format_func=winner_badge,
    )

    uav_options = [v for v in ["our", "their", "tie", "missing"] if v in comparison["numUAVcust_winner"].dropna().unique()]
    selected_uav = st.sidebar.multiselect(
        "UAV-customer result",
        options=uav_options,
        default=uav_options,
        format_func=winner_badge,
    )

    problem_search = st.sidebar.text_input("Search problem name").strip()

    filtered = comparison.copy()

    if selected_customers:
        filtered = filtered[filtered["numCustomers"].isin(selected_customers)]
    if selected_ofv:
        filtered = filtered[filtered["ofv_winner"].isin(selected_ofv)]
    if selected_uav:
        filtered = filtered[filtered["numUAVcust_winner"].isin(selected_uav)]
    if problem_search:
        filtered = filtered[filtered["problemName"].astype(str).str.contains(problem_search, case=False, na=False)]

    matched = len(filtered)

    ofv_our = int((filtered["ofv_winner"] == "our").sum())
    ofv_their = int((filtered["ofv_winner"] == "their").sum())
    ofv_ties = int((filtered["ofv_winner"] == "tie").sum())

    uav_our = int((filtered["numUAVcust_winner"] == "our").sum())
    uav_their = int((filtered["numUAVcust_winner"] == "their").sum())
    uav_ties = int((filtered["numUAVcust_winner"] == "tie").sum())

    avg_our_ofv = filtered["ofv_our"].mean() if not filtered.empty else 0
    avg_their_ofv = filtered["ofv_their"].mean() if not filtered.empty else 0
    avg_improvement = ((avg_their_ofv - avg_our_ofv) / avg_their_ofv * 100) if avg_their_ofv else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Matched Problems", format_value(matched, 0), "After current filters", "neutral")
    with c2:
        metric_card("Avg OFV Improvement", format_percent(avg_improvement), "Higher is better for us", "our" if avg_improvement > 0 else "their")
    with c3:
        metric_card("OFV Wins", f"{ofv_our} / {matched}", f"Their: {ofv_their} • Ties: {ofv_ties}", "our" if ofv_our >= ofv_their else "their")
    with c4:
        metric_card("UAV-Customer Wins", f"{uav_our} / {matched}", f"Their: {uav_their} • Ties: {uav_ties}", "our" if uav_our >= uav_their else "their")

    st.divider()

    st.subheader("Win / Loss / Tie Scorecard")
    scorecard_display = scorecard.copy()
    scorecard_display["metric"] = scorecard_display["metric"].map(METRIC_LABELS).fillna(scorecard_display["metric"])
    scorecard_display = scorecard_display.rename(columns={
        "metric": "Metric",
        "our_wins": "Our Wins",
        "their_wins": "Their Wins",
        "ties": "Ties",
        "missing": "Missing",
        "avg_our": "Average Our",
        "avg_their": "Average Their",
        "avg_our_improvement_percent": "Avg Our Improvement %",
        "avg_our_advantage_percent": "Avg Our Advantage %",
    })
    st.dataframe(scorecard_display.style.apply(scorecard_style, axis=None), use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Summary by Customer Count")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.divider()

    left, right = st.columns(2)
    with left:
        st.subheader("Average OFV")
        chart = filtered.groupby("numCustomers")[["ofv_our", "ofv_their"]].mean().reset_index()
        chart = chart.rename(columns={"ofv_our": "Our OFV", "ofv_their": "Their OFV"})
        st.bar_chart(chart, x="numCustomers", y=["Our OFV", "Their OFV"], use_container_width=True)
    with right:
        st.subheader("Average UAV Customers")
        chart = filtered.groupby("numCustomers")[["numUAVcust_our", "numUAVcust_their"]].mean().reset_index()
        chart = chart.rename(columns={"numUAVcust_our": "Our UAV Customers", "numUAVcust_their": "Their UAV Customers"})
        st.bar_chart(chart, x="numCustomers", y=["Our UAV Customers", "Their UAV Customers"], use_container_width=True)

    st.divider()

    st.subheader("Detailed Problem Comparison")
    display_columns = [
        "problemName",
        "numCustomers",
        "ofv_our",
        "ofv_their",
        "ofv_our_improvement_percent",
        "ofv_winner",
        "totalTime_our",
        "totalTime_their",
        "totalTime_winner",
        "waitingTruck_our",
        "waitingTruck_their",
        "waitingTruck_winner",
        "waitingUAV_our",
        "waitingUAV_their",
        "waitingUAV_winner",
        "numUAVcust_our",
        "numUAVcust_their",
        "numUAVcust_winner",
        "numTruckCust_our",
        "numTruckCust_their",
        "numTruckCust_winner",
        "our_metric_wins",
        "their_metric_wins",
        "metric_ties",
    ]
    display_columns = [col for col in display_columns if col in filtered.columns]

    raw = filtered[display_columns].copy()
    display = raw.copy()

    for col in [c for c in display.columns if c.endswith("_winner")]:
        display[col] = display[col].apply(winner_badge)

    if "ofv_our_improvement_percent" in display.columns:
        display["ofv_our_improvement_percent"] = display["ofv_our_improvement_percent"].round(2)

    st.dataframe(
        display.style.apply(lambda _: comparison_style(raw), axis=None),
        use_container_width=True,
        hide_index=True,
        height=620,
    )

    st.divider()

    st.subheader("Inspect One Problem")
    problem_labels = filtered["numCustomers"].astype(str) + " customers | " + filtered["problemName"].astype(str)

    if problem_labels.empty:
        st.info("No problems match the selected filters.")
        return

    selected_label = st.selectbox("Problem", problem_labels.tolist())
    selected_idx = problem_labels[problem_labels == selected_label].index[0]
    row = filtered.loc[selected_idx]

    our_col, their_col = st.columns(2)
    with our_col:
        st.markdown("### 🟢 Our Full Result")
        st.dataframe(full_side_table(row, "our"), use_container_width=True, hide_index=True)
    with their_col:
        st.markdown("### 🔴 Their Full Result")
        st.dataframe(full_side_table(row, "their"), use_container_width=True, hide_index=True)


# =============================================================================
# Maps Page
# =============================================================================

def load_map_metadata(scenario: int):
    image_path = MAPS_GENERATED_DIR / f"scenario_{scenario}_best_map.png"
    metadata_path = MAPS_GENERATED_DIR / f"scenario_{scenario}_best_map.json"

    if metadata_path.exists():
        try:
            return image_path, json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return image_path, None

    return image_path, None


def render_maps_page():
    st.title("🗺️ Scenario Maps")
    st.caption("Each map shows the best problem selected for one customer-count scenario.")

    st.sidebar.header("Map Filters")
    scenario = st.sidebar.selectbox("Customer scenario", [8, 10, 25, 50, 100], index=0)

    image_path, metadata = load_map_metadata(scenario)

    st.subheader(f"Scenario {scenario}")

    if metadata:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card("Best Problem", str(metadata.get("problemName", "—")), "Lowest OFV for this scenario", "neutral")
        with c2:
            metric_card("OFV", format_value(metadata.get("ofv")), "Lower is better", "our")
        with c3:
            metric_card("UAV Customers", format_value(metadata.get("numUAVcust"), 0), "Selected best problem", "neutral")
        with c4:
            metric_card("Truck Customers", format_value(metadata.get("numTruckCust"), 0), "Selected best problem", "neutral")

        st.write("**Route status:**", metadata.get("route_status"))
        st.write("**Summary file:**", metadata.get("summary_file"))
        st.write("**Coordinate source:**", metadata.get("coordinate_source"))
        st.write("**Truck route length:**", metadata.get("truck_route_length"))
        st.write("**UAV sorties parsed:**", metadata.get("uav_sortie_count"))
        st.write("**Truck line drawn:**", metadata.get("truck_line_drawn"))
        st.write("**UAV lines drawn:**", metadata.get("uav_line_count_drawn"))

    if image_path.exists():
        st.image(str(image_path), use_container_width=True)
    else:
        st.warning("This map image has not been generated yet.")
        st.code(f"python frontend/maps/map_best_{scenario}.py")

    st.divider()
    st.subheader("All Map Status")

    rows = []
    for s in [8, 10, 25, 50, 100]:
        img, meta = load_map_metadata(s)
        rows.append({
            "Scenario": s,
            "Image Exists": img.exists(),
            "Best Problem": None if not meta else meta.get("problemName"),
            "Route Status": None if not meta else meta.get("route_status"),
            "Truck Route Length": None if not meta else meta.get("truck_route_length"),
            "UAV Sorties Parsed": None if not meta else meta.get("uav_sortie_count"),
            "UAV Lines Drawn": None if not meta else meta.get("uav_line_count_drawn"),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# =============================================================================
# App
# =============================================================================

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Page", ["Results Dashboard", "Maps Page"])

    if page == "Maps Page":
        render_maps_page()
    else:
        render_results_page()


if __name__ == "__main__":
    main()
