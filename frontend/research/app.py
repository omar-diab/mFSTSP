"""Five-page read-only research workspace."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from research.algorithms import ALGORITHMS
from research.data import ROOT, METRICS, benchmark_inventory, coordinates, load_results, load_solution, pair_results, signature, solution_files, solution_snapshots
from research.visuals import PALETTE, position, route_distance, route_figure, playback_html

PAGES = ["Comparison dashboard", "Our experimental results", "Original paper results", "Algorithms explained", "3D delivery studio"]
CSS = """<style>
:root{color-scheme:dark}.stApp{background:#070d19;color:#dce6f6;font-family:Inter,system-ui,sans-serif}
[data-testid="stSidebar"]{background:#0b1426;border-right:1px solid #1c2b43}
[data-testid="stHeader"]{background:rgba(7,13,25,.9)}
.block-container{padding-top:2.5rem;max-width:1550px;padding-bottom:4rem}
h1,h2,h3{letter-spacing:-.035em}h1{font-weight:800!important}h3{font-size:1.2rem!important}
.eyebrow{font-size:.72rem;letter-spacing:.18em;color:#49ceee;font-weight:700;margin-bottom:12px}
.hero{padding:28px 30px;border:1px solid #20364f;border-radius:18px;background:radial-gradient(ellipse at 90% 0%,#12324c 0%,#0d192e 55%);margin-bottom:24px}
.hero h1{font-size:2.25rem;margin:0 0 8px;line-height:1.15}.hero p{color:#9bafc9;max-width:900px;margin-bottom:0}
[data-testid="stMetric"]{background:#0e1b30;border:1px solid #21344f;border-radius:14px;padding:18px 20px}
[data-testid="stMetricLabel"]{color:#9bafc9}[data-testid="stMetricValue"]{color:#eef6ff;font-weight:700;font-size:1.85rem}
button{border-radius:9px!important}[data-testid="stDataFrame"]{border:1px solid #203149;border-radius:10px}
.source-tag{display:inline-block;padding:5px 10px;background:#142b3a;border:1px solid #1e4c5b;border-radius:20px;color:#6bd9e8;font-size:.72rem;margin-right:8px;margin-top:15px}
[data-testid="stExpander"]{background:#0b1426;border:1px solid #1e304a;border-radius:10px}
div[data-baseweb="select"]>div{background:#101e33;color:#dce6f6;border-color:#2b3e59}
.stTabs [data-baseweb="tab-list"]{gap:18px;border-bottom:1px solid #203149}.stTabs [aria-selected="true"]{color:#49ceee!important}
@media(max-width:700px){.hero{padding:20px}.hero h1{font-size:1.65rem}.block-container{padding-left:1rem;padding-right:1rem}}
</style>"""


@st.cache_data(show_spinner="Reading recorded experiments…", max_entries=3)
def cached_results(stamp):
    data, issues = load_results()
    inventory = benchmark_inventory()
    for row in inventory.itertuples():
        if row.issue or not row.locations or not row.truck_travel:
            issues.append(f"Benchmark {row.problemName}: {row.issue or 'Missing locations or truck travel CSV'}")
    if inventory.empty:
        issues.append("No benchmark instance folders found in Problems/.")
    return (data, issues), inventory


@st.cache_data(max_entries=20)
def cached_solution(path, modified, snapshot=-1):
    return load_solution(Path(path), snapshot)


def hero(title, subtitle, tag="RECORDED DATA · READ-ONLY"):
    st.markdown(f'<div class="hero"><div class="eyebrow">mFSTSP / RESEARCH WORKSPACE</div><h1>{title}</h1><p>{subtitle}</p><span class="source-tag">{tag}</span><span class="source-tag">TRUCK + MULTIPLE UAVs</span></div>', unsafe_allow_html=True)


def chart(fig, key=None):
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0b1426", plot_bgcolor="#0b1426", font=dict(family="Inter, sans-serif", color="#c6d7eb"), colorway=PALETTE, margin=dict(l=30,r=20,t=45,b=40), legend_title_text="")
    st.plotly_chart(fig, width="stretch", key=key)


def table(df, name):
    styled = df.style.map(lambda value: "background-color: #123c36; color: #65e8c3" if value == "Proposed" else "background-color: #3c2d16; color: #ffcb7a" if value == "Archive" else "", subset=["winner"]) if "winner" in df else df
    st.dataframe(styled, width="stretch", hide_index=True)
    st.download_button("↓ Export CSV", df.to_csv(index=False).encode("utf-8-sig"), name+".csv", "text/csv", key="download_"+name)


def kpis(items):
    for col, (label, value, detail) in zip(st.columns(len(items)), items):
        with col:
            st.metric(label, value)
            with st.popover("About " + label, width="stretch"):
                st.write(detail)


def fmt(value):
    return f"{value:,.2f}" if pd.notna(value) else "Unavailable"


def filter_runs(df, prefix, sizes):
    df = df[df.numCustomers.isin(sizes)].copy()
    a, b = st.columns([1, 2])
    algorithms = a.multiselect("Algorithm", sorted(df.algorithm.unique()), default=sorted(df.algorithm.unique()), key=prefix+"_alg")
    df = df[df.algorithm.isin(algorithms)]
    configs = b.multiselect("Experiment configuration (empty = all)", sorted(df.configuration.unique()), key=prefix+"_config")
    if configs:
        df = df[df.configuration.isin(configs)]
    instances = st.multiselect("Benchmark instance (empty = all)", sorted(df.problemName.unique()), key=prefix+"_instances")
    return df[df.problemName.isin(instances)] if instances else df


def comparison(results, sizes):
    hero("Evidence before improvement.", "Compare our proposed heuristic with archived reference runs under matching benchmark conditions. Every score remains attached to its configuration and source.")
    proposed = results[results.algorithm.str.contains("No-Gurobi", case=False)]
    archive = results[results.source.eq("performance_summary_archive.csv")]
    if proposed.empty or archive.empty:
        st.warning("Both proposed and archived result records are required for comparisons. Check Data quality & provenance for missing or malformed sources.")
        return
    a, b, c = st.columns([2, 2, 1.4])
    source = a.selectbox("Proposed experiment", sorted(proposed.source.unique()))
    baseline_algorithm = b.selectbox("Archived reference algorithm", sorted(archive.algorithm.unique()))
    metric = c.selectbox("Compare metric", list(METRICS), format_func=METRICS.get)
    ours = proposed[proposed.source.eq(source)]
    archive = archive[archive.algorithm.eq(baseline_algorithm)]
    with st.expander("Configure benchmark scope"):
        instances = st.multiselect("Instances", sorted(set(ours.problemName) | set(archive.problemName)))
        vehicle = st.multiselect("Vehicle type", sorted(archive.vehicleFileID.dropna().unique().astype(int)))
        fleet = st.multiselect("UAV fleet size", sorted(archive.numUAVs.dropna().unique().astype(int)))
    for column, values in [("numCustomers", sizes), ("problemName", instances), ("vehicleFileID", vehicle), ("numUAVs", fleet)]:
        if values or column == "numCustomers":
            ours, archive = ours[ours[column].isin(values)], archive[archive[column].isin(values)]
    paired = pair_results(ours, archive, metric)
    valid = paired[paired.comparable & paired.winner.ne("Not comparable")]
    wins, losses = (valid.winner.eq(x).sum() for x in ["Proposed", "Archive"])
    kpis([("Compatible solutions", len(valid), "Both sides have a positive finite objective and the complete comparison key matches."), ("Proposed wins", int(wins), "Wins apply only to the selected metric in compatible configurations."), ("Archive wins", int(losses), "Runtime environments differ; descriptive measurements are not a controlled speed benchmark."), ("Mean improvement", fmt(valid.improvement_percent.mean())+"%" if len(valid) else "Unavailable", "Mean per-pair percentage. Zero reference values have undefined percentages.")])
    st.caption("Matching key: instance, customer count, vehicle type, UAV count, truck flag, depot requirement, driver requirement, endurance model, cutoff and iteration setting. Repeated runs: best makespan per exact configuration; recorded-run counts remain in the export.")
    if metric in ("numUAVcust", "numTruckCust"):
        st.info("Service counts describe workload allocation, not overall solution quality. More UAV customers / fewer truck customers is treated as a utilization preference only.")
    st.caption("Runtime comparisons are uncontrolled across hardware/software. Current source ignores some legacy flags (see main.py); identical recorded flags alone cannot establish full model equivalence. No causal performance claim is inferred.")
    overview, distributions, evidence = st.tabs(["Performance overview", "Distributions & coverage", "Pairing audit"])
    with overview:
        if valid.empty:
            st.warning("No compatible solved pairs in this scope. An improvement or best-algorithm ranking would be unsupported.")
            st.write("Proposed runs generally use vehicle 101, 3 UAVs, Etype 3 and a 3,600-second cutoff. The archived heuristic uses Etype 1 and a 5-second cutoff. These are not treated as equivalent.")
            raw = pd.concat([ours.assign(cohort="Proposed"), archive.assign(cohort="Archive")])
            if len(raw):
                values = raw[raw.solved & raw[metric].ge(0)]
                chart(px.box(values, x="numCustomers", y=metric, color="cohort", points="outliers", labels={metric: METRICS[metric], "numCustomers": "Customers"}, hover_data=["problemName", "configuration"], title="Descriptive distributions only · configurations differ"))
                descriptive = values.groupby(["numCustomers", "cohort"], as_index=False)[metric].mean()
                chart(px.line(descriptive, x="numCustomers", y=metric, color="cohort", markers=True, labels={metric: METRICS[metric], "numCustomers": "Customers"}, title="Descriptive mean by size · unmatched conditions, no improvement inference"))
        else:
            winner = "Tie" if wins == losses else "Proposed" if wins > losses else "Archive"
            st.success(f"Best by compatible-pair win count for {METRICS[metric]}: {winner}. Ties: {valid.winner.eq('Tie').sum()}.")
            long = valid.melt(id_vars=["problemName", "numCustomers"], value_vars=[metric+"_our", metric+"_archive"], var_name="Algorithm", value_name=METRICS[metric])
            chart(px.bar(long, x="problemName", y=METRICS[metric], color="Algorithm", barmode="group", title="Identical benchmark conditions"))
            summary = valid.groupby("numCustomers", as_index=False).improvement_percent.mean()
            chart(px.line(summary, x="numCustomers", y="improvement_percent", markers=True, title="Mean paired improvement by problem size", labels={"improvement_percent": "Improvement (%)", "numCustomers": "Customers"}))
        table(paired.drop(columns="_merge"), "comparison_pairs")
    with distributions:
        if len(valid):
            chart(px.histogram(valid, x="improvement_percent", color="winner", title="Compatible-pair improvement distribution"))
        coverage = pd.concat([ours.assign(cohort="Proposed"), archive.assign(cohort="Archive")])
        if len(coverage):
            count = coverage.groupby(["numCustomers", "cohort", "outcome"], as_index=False).size()
            chart(px.bar(count, x="numCustomers", y="size", color="outcome", facet_col="cohort", title="Recorded outcome coverage", labels={"size": "Runs", "numCustomers": "Customers"}))
        st.info("No record is not the same as an unsolved run. Unsolved status is shown only when recorded or an objective is missing/invalid.")
    with evidence:
        audit = pd.concat([ours.assign(cohort="Proposed"), archive.assign(cohort="Archive")])
        table(audit.groupby(["cohort", "configuration"], dropna=False).size().rename("recorded_runs").reset_index(), "configuration_audit")
        st.warning("Legacy frontend_data comparisons select best runs by instance without requiring equal configurations. Their headline improvements are not reused here.")


def route_browser(instance, prefix, kind=None, animated=False):
    paths = solution_files(instance)
    if kind == "proposed":
        paths = [p for p in paths if "NoGurobi" in p.name]
    elif kind == "archive":
        paths = [p for p in paths if "NoGurobi" not in p.name]
    if not paths:
        st.info("No saved solution is available. A route is not invented from coordinates.")
        return
    default_index = next((i for i, p in enumerate(paths) if "NoGurobi" in p.name), 0) if kind != "archive" else 0
    filename = st.selectbox("Saved solution / vehicle configuration", [p.name for p in paths], index=default_index, key=prefix+"_solution")
    path = next(p for p in paths if p.name == filename)
    try:
        snapshots = solution_snapshots(path)
        snapshot = st.selectbox("Recorded snapshot (file order; dates not recorded)", list(range(len(snapshots))), index=len(snapshots)-1, format_func=lambda i: f"Snapshot {i+1} of {len(snapshots)}", key=prefix+"_snapshot")
        solution = cached_solution(str(path), path.stat().st_mtime_ns, snapshot)
        coords = coordinates(instance)
    except (ValueError, KeyError, OSError, SyntaxError) as error:
        st.error(f"Cannot read saved solution: {error}")
        return
    st.caption(f"Source: {solution['path']}. Saved routes are separate snapshots, not assumed to match a selected summary row or the current algorithm version.")
    if len(snapshots) > 1:
        st.info("This file contains appended solution snapshots. Only the selected block is visualized; histories are never merged. Original-method files can include local reruns and are not authenticated publication routes.")
    for warning in solution["warnings"]:
        st.warning(warning)
    st.caption("Real benchmark coordinates, locally projected in metres. Height is illustrative, not measured altitude. Lines are schematic, not reconstructed road/flight trajectories. Between recorded UAV activities, the marker stays at its last recorded node because its position is unavailable.")
    with st.expander("Saved configuration & validation"):
        st.json(solution["config"])
        st.write("Recorded validation (not independently certified):")
        st.json(solution["validation"] or {"status": "No validation dictionary recorded"})
    if not solution["segments"]:
        st.info("No timed assignments parsed. Playback is unavailable.")
        return
    vehicles = sorted({s["vehicle"] for s in solution["segments"]})
    left, right = st.columns([2, 1])
    selected = left.selectbox("Inspect vehicle", vehicles, key=prefix+"_vehicle")
    speed = right.select_slider("Playback speed", options=[.25, .5, 1., 2., 4.], value=1., format_func=lambda x: f"{x:g}×", key=prefix+"_speed") if animated else 1
    distances = route_distance(solution, coords)
    kpis([("Saved makespan", fmt(solution["ofv"])+" s", "Objective read directly from the saved solution."), ("Vehicles recorded", len(vehicles), "Unique vehicle IDs in saved assignments, not declared fleet size."), ("Selected route geometry", fmt(distances.get(selected, 0)/1000)+" km", "Sum of straight-line segments; not road-network distance.")])
    if animated:
        html = playback_html(solution, coords, speed, selected)
        if hasattr(st, "iframe"):
            st.iframe(html, height=735)
        else:
            components.html(html, height=735, scrolling=False)
        st.download_button("↓ Export interactive playback HTML", html, f"{instance}_playback.html", "text/html", key=prefix+"_html")
    else:
        st.plotly_chart(route_figure(solution, coords, False, speed, selected), width="stretch", key=prefix+"_scene")
    if animated:
        st.caption("Play / Pause / Restart and the schedule slider are inside the scene. Drag to rotate, scroll to zoom, click the legend to toggle vehicles. The inspector is an independent time probe.")
        probe = st.slider("Inspect recorded schedule time (s)", 0., max(solution["duration"], .01), 0., key=prefix+"_time")
        a, b, fraction, status = position(solution["segments"], selected, probe)
        st.info(f"{selected} · {status} · node {a} → {b} · segment progress {fraction:.0%}")
    activity, delivery = st.tabs(["Vehicle activity & events", "Delivery times"])
    with activity:
        table(pd.DataFrame(solution["segments"]), prefix+"_assignments")
        if solution["events"]:
            table(pd.DataFrame(solution["events"]), prefix+"_events")
    with delivery:
        st.caption("Proposed UAV times are illustrative midpoints. Original assignment delivery times and proposed truck service times are recorded.")
        table(pd.DataFrame(solution["deliveries"], columns=["node", "completion_time_s"]), prefix+"_deliveries")
    st.download_button("↓ Download original saved solution", path.read_bytes(), path.name, "text/plain", key=prefix+"_original_download")


def results_page(results, inventory, sizes, original=False):
    prefix = "archive" if original else "ours"
    hero("The reference benchmark." if original else "Every experiment, in context.", "Archived original-method results, kept separate from local experiments. Provenance is the repository archive; publication tables have not been independently verified." if original else "Explore proposed-heuristic runs, recorded outcomes and saved delivery routes. Browsing never runs the optimizer.")
    if original:
        df = results[results.source.eq("performance_summary_archive.csv")]
    else:
        df = results[results.algorithm.str.contains("No-Gurobi", case=False)]
        sources = st.multiselect("Experiment files", sorted(df.source.unique()), default=sorted(df.source.unique()), key=prefix+"_sources")
        df = df[df.source.isin(sources)]
        st.caption("Summary and runner files can describe different experiment versions. They remain separate records; pooled means/counts describe records, not unique benchmark performance.")
    df = filter_runs(df, prefix, sizes)
    solved = df[df.solved]
    kpis([("Recorded runs", len(df), "Repeated experiments are retained."), ("Recorded solutions", len(solved), "Positive finite objective; not an independent feasibility proof."), ("No valid solution", len(df)-len(solved), "Failed status or invalid objective. Absent experiments are not failures."), ("Mean runtime", fmt(solved.totalTime[solved.totalTime.ge(0)].mean())+" s", "Mean of available recorded runtime measurements.")])
    if df.empty:
        st.info("No recorded runs match these filters.")
    else:
        overview, records, routes = st.tabs(["Performance", "Detailed records", "Saved routes"])
        with overview:
            metric = st.selectbox("Performance metric", list(METRICS), format_func=METRICS.get, key=prefix+"_metric")
            plotted = solved[solved[metric].ge(0)].copy()
            plotted["cohort"] = plotted.algorithm+" · "+plotted.source
            if len(plotted):
                chart(px.box(plotted, x="numCustomers", y=metric, color="cohort", points="outliers", hover_data=["problemName", "configuration"], labels={"numCustomers": "Customers", metric: METRICS[metric]}, title="Recorded distribution by benchmark size"))
                chart(px.scatter(plotted, x="totalTime", y="ofv", color="cohort", hover_data=["problemName", "configuration"], labels={"totalTime": "Runtime (s)", "ofv": "Makespan (s)"}, title="Runtime versus solution quality"))
                trend = plotted.groupby(["numCustomers", "cohort"], as_index=False)[metric].mean()
                chart(px.line(trend, x="numCustomers", y=metric, color="cohort", markers=True, labels={metric: METRICS[metric], "numCustomers": "Customers"}, title="Mean recorded metric across problem sizes · mixed configurations may remain"))
        with records:
            status = st.radio("Outcome scope", ["All", "Recorded solutions", "No valid solution"], horizontal=True, key=prefix+"_status")
            shown = df if status == "All" else df[df.solved.eq(status == "Recorded solutions")]
            table(shown, prefix+"_records")
            st.info("isOptimal is an optimality flag, not feasibility validation. bestBound=-1 means no recorded bound. Validation dictionaries, when available, are shown with saved routes.")
        with routes:
            instance = st.selectbox("Instance to inspect", sorted(df.problemName.unique()), key=prefix+"_route_instance")
            route_browser(instance, prefix, "archive" if original else "proposed")
    with st.expander("Benchmark availability and coverage"):
        available = inventory[inventory.numCustomers.isin(sizes)].copy()
        available["has_selected_record"] = available.problemName.isin(set(df.problemName))
        st.caption("Benchmarks without selected records are missing results, not unsolved runs.")
        table(available, prefix+"_inventory")


def algorithms_page():
    hero("Inside the optimization engine.", "Source-grounded explanations of the implemented search, assignment and scheduling components. No solver is imported or executed by this dashboard.")
    selected = st.selectbox("Explore an implemented algorithm", [a["name"] for a in ALGORITHMS])
    algorithm = next(a for a in ALGORITHMS if a["name"] == selected)
    st.subheader(algorithm["role"])
    st.caption(f"Source: {algorithm['source']} · function: {algorithm['function']}")
    a, b = st.columns(2)
    a.markdown("**Inputs**\n\n"+algorithm["inputs"])
    b.markdown("**Outputs**\n\n"+algorithm["outputs"])
    explanation, pseudocode, source = st.tabs(["Walkthrough & flow", "Pseudocode", "Actual implementation"])
    with explanation:
        step = st.slider("Walk through the algorithm", 1, len(algorithm["steps"]), 1)
        for i, text in enumerate(algorithm["steps"], 1):
            (st.info if i == step else st.write)(f"{i}. {text}")
        st.caption("Educational walkthrough; not an actual recorded optimizer execution.")
        nodes = "\n".join(f'n{i} [label={json.dumps(label)}, fillcolor="{"#185978" if i == step-1 else "#12243c"}"];' for i, label in enumerate(algorithm["flow"]))
        edges = "\n".join(f"n{i} -> n{i+1};" for i in range(len(algorithm["flow"])-1))
        st.graphviz_chart('digraph { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fontcolor="#dce6f6", color="#32627e"]; edge [color="#49ceee"];'+nodes+edges+'}')
        a, b = st.columns(2)
        a.success("Strengths: "+algorithm["strengths"])
        b.warning("Limitations: "+algorithm["weaknesses"])
    with pseudocode:
        st.code(algorithm["pseudocode"], language="python")
    with source:
        code = (ROOT / algorithm["source"]).read_text(encoding="utf-8")
        tree = ast.parse(code)
        function = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == algorithm["function"]), None)
        if function:
            st.code("\n".join(code.splitlines()[function.lineno-1:function.end_lineno]), language="python", line_numbers=True)
        else:
            st.warning("Function not found in this source revision.")
    st.subheader("How the approaches differ")
    st.dataframe(pd.DataFrame([{"Algorithm": a["name"], "Role": a["role"], "Output": a["outputs"], "Limitation": a["weaknesses"]} for a in ALGORITHMS]), hide_index=True, width="stretch")
    st.info("Current main.py only accepts problemType=2 and calls proposed_heuristic_no_gurobi. Gurobi solvers remain reference code. Historical experiments are not assumed to use the current source revision.")


def studio(inventory, sizes):
    hero("Watch the delivery system move.", "Inspect recorded truck and drone assignments in 3D. Follow the timeline, compare saved solutions, and examine launch and rendezvous events.", "REAL COORDINATES · ILLUSTRATIVE HEIGHT")
    mode = st.radio("Studio mode", ["Delivery playback", "Algorithm execution"], horizontal=True, key="studio_mode")
    if mode == "Algorithm execution":
        st.warning("No saved population, generation, incumbent-history or optimization trace was found. A final route cannot reconstruct the search trajectory. Real optimization-step playback is unavailable.")
        st.write("Use Algorithms explained for a source-based walkthrough, or Delivery playback for recorded schedule events. No synthetic search steps are presented as experimental evidence.")
        return
    scoped = inventory[inventory.numCustomers.isin(sizes)]
    if scoped.empty:
        st.info("Select at least one customer count in the sidebar.")
        return
    instance = st.selectbox("Benchmark instance", scoped.problemName.tolist(), format_func=lambda x: f"{x} · {int(scoped.set_index('problemName').loc[x, 'numCustomers'])} customers")
    route_browser(instance, "studio", animated=True)
    if st.checkbox("Compare another saved solution side by side"):
        paths = solution_files(instance)
        second_name = st.selectbox("Second saved solution", [p.name for p in paths], key="second_solution")
        other = next(p for p in paths if p.name == second_name)
        try:
            second = cached_solution(str(other), other.stat().st_mtime_ns)
            first_path = next(p for p in paths if p.name == st.session_state.get("studio_solution", paths[0].name))
            first = cached_solution(str(first_path), Path(first_path).stat().st_mtime_ns, st.session_state.get("studio_snapshot", -1))
            coords = coordinates(instance)
            for column, solution in zip(st.columns(2), [first, second]):
                with column:
                    st.caption(solution["path"])
                    st.plotly_chart(route_figure(solution, coords), width="stretch")
            st.caption("Independent configurations. Geometric comparison does not establish a fair performance comparison; playback stays in the primary scene.")
        except (ValueError, KeyError, OSError) as error:
            st.error(f"Cannot compare routes: {error}")


def main():
    st.set_page_config(page_title="mFSTSP · Research workspace", page_icon="🚚", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    (results, issues), inventory = cached_results(signature())
    with st.sidebar:
        st.markdown("### ◈ mFSTSP\n**Optimization research lab**")
        st.caption("One truck. Multiple drones. Evidence-led research.")
        st.divider()
        page = st.radio("Workspace", PAGES, label_visibility="collapsed", key="workspace")
        st.divider()
        sizes = st.multiselect("Customer counts", [8, 10, 25, 50, 100], default=[8, 10, 25, 50, 100])
        st.caption(f"{len(inventory)} benchmark instances · {len(results):,} recorded result rows")
        st.caption("Sources are read-only. No solver runs while browsing.")
        if st.button("Refresh recorded data", width="stretch"):
            st.cache_data.clear()
            st.rerun()
        with st.expander("Data quality & provenance"):
            st.write("Sources: performance_summary.csv, performance_summary_archive.csv, results/all_*.csv, Problems/*/tbl_locations.csv and saved tbl_solutions files.")
            st.write("Precomputed comparison scores are excluded. Archive attribution is by file provenance, not independently verified publication tables.")
            if issues:
                st.warning(f"{len(issues)} parsing / source issues")
                st.text("\n".join(issues))
            else:
                st.success("No malformed result records detected.")
    if page == PAGES[0]:
        comparison(results, sizes)
    elif page in PAGES[1:3]:
        results_page(results, inventory, sizes, original=page == PAGES[2])
    elif page == PAGES[3]:
        algorithms_page()
    else:
        studio(inventory, sizes)
    st.divider()
    st.caption("mFSTSP research workspace · Recorded evidence, explicit assumptions, reproducible exports · No benchmark or result files are written by this application.")


if __name__ == "__main__":
    main()
