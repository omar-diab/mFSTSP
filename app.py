import pandas as pd
import streamlit as st
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "frontend_data" / "comparison_8_10_25.csv"

st.set_page_config(
    page_title="mFSTSP Solver Comparison",
    layout="wide"
)

st.title("mFSTSP Solver Comparison")
st.write("Our heuristic results vs archive results for 8, 10, and 25 customers.")

df = pd.read_csv(DATA_FILE)

metrics = [
    "totalTime",
    "ofv",
    "waitingTruck",
    "waitingUAV",
    "numUAVcust",
    "numTruckCust",
]

customer_options = ["All"] + sorted(df["numCustomers"].dropna().unique().astype(int).tolist())

selected_customer = st.sidebar.selectbox("Filter by customer count", customer_options)

if selected_customer != "All":
    df = df[df["numCustomers"] == selected_customer]

st.subheader("Summary")

col1, col2, col3 = st.columns(3)
col1.metric("Problems", df["problemName"].nunique())
col2.metric("Rows", len(df))
col3.metric("Customer Groups", df["numCustomers"].nunique())

st.subheader("Comparison Table")

display_cols = [
    "problemName",
    "numCustomers",
]

for metric in metrics:
    display_cols += [
        f"{metric}_our",
        f"{metric}_their",
        f"{metric}_winner",
    ]

table_df = df[display_cols].copy()


def highlight_cells(row):
    styles = [""] * len(row)

    for metric in metrics:
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"
        winner_col = f"{metric}_winner"

        if our_col not in row.index:
            continue

        our_idx = row.index.get_loc(our_col)
        their_idx = row.index.get_loc(their_col)

        winner = row[winner_col]

        if winner == "our":
            styles[our_idx] = "background-color: #dcfce7; color: #166534; font-weight: bold;"
            styles[their_idx] = "background-color: #fee2e2; color: #991b1b;"
        elif winner == "their":
            styles[their_idx] = "background-color: #dcfce7; color: #166534; font-weight: bold;"
            styles[our_idx] = "background-color: #fee2e2; color: #991b1b;"
        else:
            styles[our_idx] = "background-color: #fef9c3; color: #854d0e;"
            styles[their_idx] = "background-color: #fef9c3; color: #854d0e;"

    return styles


st.dataframe(
    table_df.style.apply(highlight_cells, axis=1).format(precision=2),
    use_container_width=True,
    height=600
)

st.subheader("Average Comparison")

avg_rows = []

for metric in metrics:
    our_avg = df[f"{metric}_our"].mean()
    their_avg = df[f"{metric}_their"].mean()

    if our_avg < their_avg:
        winner = "Our"
    elif their_avg < our_avg:
        winner = "Their"
    else:
        winner = "Tie"

    avg_rows.append({
        "Metric": metric,
        "Our Average": our_avg,
        "Their Average": their_avg,
        "Winner": winner,
    })

avg_df = pd.DataFrame(avg_rows)

st.dataframe(
    avg_df.style.format({
        "Our Average": "{:.2f}",
        "Their Average": "{:.2f}",
    }),
    use_container_width=True
)

st.subheader("Charts")

selected_metric = st.selectbox("Choose metric", metrics)

chart_df = df[[
    "problemName",
    "numCustomers",
    f"{selected_metric}_our",
    f"{selected_metric}_their",
]].copy()

chart_df = chart_df.rename(columns={
    f"{selected_metric}_our": "Our Result",
    f"{selected_metric}_their": "Their Result",
})

st.bar_chart(
    chart_df.set_index("problemName")[["Our Result", "Their Result"]]
)

st.subheader("Download Data")

st.download_button(
    label="Download comparison CSV",
    data=df.to_csv(index=False),
    file_name="comparison_results.csv",
    mime="text/csv"
)