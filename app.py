import streamlit as st
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "frontend_data"

COMPARISON_FILE = DATA_DIR / "comparison_all_100.csv"
SUMMARY_FILE = DATA_DIR / "comparison_all_100_summary.csv"


st.set_page_config(
    page_title="mFSTSP Comparison Dashboard",
    page_icon="🚚",
    layout="wide"
)


def load_data():
    if not COMPARISON_FILE.exists():
        st.error(f"Missing file: {COMPARISON_FILE}")
        st.stop()

    if not SUMMARY_FILE.exists():
        st.error(f"Missing file: {SUMMARY_FILE}")
        st.stop()

    comparison = pd.read_csv(COMPARISON_FILE)
    summary = pd.read_csv(SUMMARY_FILE)

    return comparison, summary


def format_seconds(seconds):
    if pd.isna(seconds):
        return ""

    seconds = float(seconds)
    minutes = int(seconds // 60)
    sec = int(seconds % 60)

    return f"{minutes}m {sec}s"


def winner_badge(value):
    if value == "our":
        return "🟢 Our"
    if value == "their":
        return "🔴 Their"
    if value == "tie":
        return "🟡 Tie"
    return "⚪ Missing"


def main():
    comparison, summary = load_data()

    st.title("mFSTSP Heuristic Comparison")
    st.caption("Comparison between our no-Gurobi heuristic and their archived heuristic results.")

    # =========================================================
    # Top metrics
    # =========================================================
    total_matched = len(comparison)
    total_groups = comparison["numCustomers"].nunique()

    avg_our_ofv = comparison["ofv_our"].mean()
    avg_their_ofv = comparison["ofv_their"].mean()

    if avg_their_ofv and avg_their_ofv != 0:
        avg_improvement = ((avg_their_ofv - avg_our_ofv) / avg_their_ofv) * 100
    else:
        avg_improvement = 0

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Matched Problems", total_matched)
    col2.metric("Customer Groups", total_groups)
    col3.metric("Avg Our OFV", f"{avg_our_ofv:.2f}")
    col4.metric("Avg OFV Improvement", f"{avg_improvement:.2f}%")

    st.divider()

    # =========================================================
    # Filters
    # =========================================================
    st.sidebar.title("Filters")

    customer_options = sorted(comparison["numCustomers"].dropna().unique())
    selected_customers = st.sidebar.multiselect(
        "Customer Count",
        options=customer_options,
        default=customer_options
    )

    uav_options = sorted(comparison["numUAVs"].dropna().unique()) if "numUAVs" in comparison.columns else []
    selected_uavs = st.sidebar.multiselect(
        "Number of UAVs",
        options=uav_options,
        default=uav_options
    )

    filtered = comparison.copy()

    if selected_customers:
        filtered = filtered[filtered["numCustomers"].isin(selected_customers)]

    if selected_uavs and "numUAVs" in filtered.columns:
        filtered = filtered[filtered["numUAVs"].isin(selected_uavs)]

    # =========================================================
    # Summary table
    # =========================================================
    st.subheader("Summary by Customer Count")

    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # =========================================================
    # Charts
    # =========================================================
    st.subheader("Average Objective Function Value")

    ofv_chart = (
        filtered
        .groupby("numCustomers")[["ofv_our", "ofv_their"]]
        .mean()
        .reset_index()
        .rename(columns={
            "ofv_our": "Our Heuristic",
            "ofv_their": "Their Heuristic"
        })
    )

    st.bar_chart(
        ofv_chart,
        x="numCustomers",
        y=["Our Heuristic", "Their Heuristic"],
        use_container_width=True
    )

    st.subheader("Average Runtime")

    runtime_chart = (
        filtered
        .groupby("numCustomers")[["totalTime_our", "totalTime_their"]]
        .mean()
        .reset_index()
        .rename(columns={
            "totalTime_our": "Our Runtime",
            "totalTime_their": "Their Runtime"
        })
    )

    st.bar_chart(
        runtime_chart,
        x="numCustomers",
        y=["Our Runtime", "Their Runtime"],
        use_container_width=True
    )

    st.subheader("Average Waiting Times")

    wait_chart = (
        filtered
        .groupby("numCustomers")[
            [
                "waitingTruck_our",
                "waitingTruck_their",
                "waitingUAV_our",
                "waitingUAV_their",
            ]
        ]
        .mean()
        .reset_index()
        .rename(columns={
            "waitingTruck_our": "Our Truck Waiting",
            "waitingTruck_their": "Their Truck Waiting",
            "waitingUAV_our": "Our UAV Waiting",
            "waitingUAV_their": "Their UAV Waiting",
        })
    )

    st.bar_chart(
        wait_chart,
        x="numCustomers",
        y=[
            "Our Truck Waiting",
            "Their Truck Waiting",
            "Our UAV Waiting",
            "Their UAV Waiting",
        ],
        use_container_width=True
    )

    st.divider()

    # =========================================================
    # Detailed comparison table
    # =========================================================
    st.subheader("Detailed Problem Comparison")

    display_cols = [
        "problemName",
        "numCustomers",
        "numUAVs",
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
        "numTruckCust_our",
        "numTruckCust_their",
    ]

    available_cols = [col for col in display_cols if col in filtered.columns]

    table = filtered[available_cols].copy()

    for col in [
        "ofv_winner",
        "totalTime_winner",
        "waitingTruck_winner",
        "waitingUAV_winner",
    ]:
        if col in table.columns:
            table[col] = table[col].apply(winner_badge)

    if "ofv_our_improvement_percent" in table.columns:
        table["ofv_our_improvement_percent"] = table["ofv_our_improvement_percent"].round(2)

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True
    )

    # =========================================================
    # Single problem viewer
    # =========================================================
    st.divider()
    st.subheader("Inspect One Problem")

    problem_names = sorted(filtered["problemName"].dropna().unique())

    if problem_names:
        selected_problem = st.selectbox("Select problem", problem_names)

        row = filtered[filtered["problemName"] == selected_problem].iloc[0]

        c1, c2, c3 = st.columns(3)

        c1.metric("Our OFV", f"{row['ofv_our']:.2f}")
        c2.metric("Their OFV", f"{row['ofv_their']:.2f}")

        if "ofv_our_improvement_percent" in row and pd.notna(row["ofv_our_improvement_percent"]):
            c3.metric("Our Improvement", f"{row['ofv_our_improvement_percent']:.2f}%")
        else:
            c3.metric("Our Improvement", "N/A")

        st.write("Full row:")
        st.dataframe(
            pd.DataFrame([row]),
            use_container_width=True,
            hide_index=True
        )


if __name__ == "__main__":
    main()