from pathlib import Path

frontend = Path(__file__).resolve().parent
builder = frontend / "maps" / "map_builder.py"
dashboard = frontend / "result_dashboard.py"

builder_text = builder.read_text(encoding="utf-8", errors="ignore")
dashboard_text = dashboard.read_text(encoding="utf-8", errors="ignore")

print("Frontend folder:", frontend)
print("Project root should be:", frontend.parent)
print()
print("Dashboard has Maps Page:", "Maps Page" in dashboard_text)
print("Map builder parses 'Truck Route':", "Truck Route" in builder_text)
print("Map builder parses 'UAV Sorties':", "UAV Sorties" in builder_text)
print("Map builder targets NoGurobiHeuristic summaries:", "NoGurobiHeuristic" in builder_text)
print()
print("Expected result: all four lines above should be True.")
