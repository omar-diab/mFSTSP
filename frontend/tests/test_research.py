"""Research correctness, saved-data parsing and Streamlit interaction regression tests."""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.data import ROOT, KEYS, benchmark_inventory, coordinates, load_results, load_solution, normalize, pair_results, read_csv, solution_snapshots
from research.visuals import route_figure, route_distance, playback_html
from research.algorithms import ALGORITHMS


class ResearchDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.issues = load_results()

    def pair(self, ours=80, archive=100, metric="ofv", changes=None):
        row = dict(problemName="instance", numCustomers=8, vehicleFileID=101, numUAVs=3, numTrucks=-1, requireTruckAtDepot=1, requireDriver=1, Etype=3, cutoffTime=3600, ITER=1, ofv=ours, numUAVcust=ours)
        left = normalize(pd.DataFrame([row]), "proposed")
        row.update(ofv=archive, numUAVcust=archive)
        row.update(changes or {})
        right = normalize(pd.DataFrame([row]), "archive")
        return pair_results(left, right, metric)

    def test_improvement_directions_and_zero_reference(self):
        result = self.pair()
        self.assertAlmostEqual(result.iloc[0].improvement_percent, 20)
        self.assertEqual(result.iloc[0].winner, "Proposed")
        result = self.pair(120, 100, "numUAVcust")
        self.assertAlmostEqual(result.iloc[0].improvement_percent, 20)
        self.assertEqual(result.iloc[0].winner, "Proposed")
        result = self.pair(80, 100, "numUAVcust", {"numUAVcust": 0})
        self.assertTrue(pd.isna(result.iloc[0].improvement_percent))

    def test_incompatible_and_unknown_configuration_never_pair(self):
        for changes in [{"Etype": 1}, {"numUAVs": 4}, {"cutoffTime": 5}, {"vehicleFileID": None}]:
            result = self.pair(changes=changes)
            self.assertEqual(len(result), 2)
            self.assertFalse(result.comparable.any())

    def test_unsolved_and_ties(self):
        self.assertFalse(self.pair(ours=-1).comparable.any())
        self.assertEqual(self.pair(100, 100).iloc[0].winner, "Tie")

    def test_recorded_configuration_gap(self):
        self.assertFalse(self.issues)
        ours = self.data[self.data.algorithm.str.contains("No-Gurobi")]
        archive = self.data[self.data.source.eq("performance_summary_archive.csv")]
        for algorithm in archive.algorithm.unique():
            self.assertFalse(pair_results(ours, archive[archive.algorithm.eq(algorithm)]).comparable.any())

    def test_benchmark_inventory(self):
        inventory = benchmark_inventory()
        self.assertEqual(len(inventory), 100)
        self.assertTrue(inventory.locations.all() and inventory.truck_travel.all())
        self.assertEqual(inventory.groupby("numCustomers").size().to_dict(), {8:20,10:20,25:20,50:20,100:20})

    def test_bad_csv_record_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"test.csv"
            path.write_text("a,b\n1,2\n3,4,5\n", encoding="utf-8")
            frame, notes = read_csv(path)
            self.assertEqual(len(frame), 1)
            self.assertEqual(len(notes), 1)

    def test_snapshots_are_not_merged(self):
        path = ROOT/"Problems/20170608T121355407419/tbl_solutions_101_1_IP.csv"
        blocks = solution_snapshots(path)
        self.assertGreater(len(blocks), 1)
        for index in range(len(blocks)):
            result = load_solution(path, index)
            self.assertEqual(result["snapshot_index"], index)
            self.assertFalse(result["warnings"])
            self.assertLessEqual(max(s["end"] for s in result["segments"]), result["ofv"] + .01)

    def test_all_saved_solution_snapshots_parse(self):
        paths = list((ROOT/"Problems").glob("*/tbl_solutions_*.csv"))
        self.assertEqual(len(paths), 2020)
        for path in paths:
            for index in range(len(solution_snapshots(path))):
                result = load_solution(path, index)
                self.assertTrue(result["segments"], str(path))
                self.assertGreater(result["duration"], 0)
                self.assertTrue(all(s["end"] >= s["start"] for s in result["segments"]))

    def test_3d_uses_real_nodes_and_serializes_animation(self):
        instance = "20170608T121949065533"
        path = ROOT/"Problems"/instance/"tbl_solutions_101_3_NoGurobiHeuristic.csv"
        result = load_solution(path)
        coords = coordinates(instance)
        self.assertTrue(result["validation"]["valid"])
        self.assertTrue(any("before its previous rendezvous" in w for w in result["warnings"]))
        figure = route_figure(result, coords, animated=True)
        self.assertEqual(len(figure.frames), 65)
        self.assertEqual(len(figure.data[0].x), len(coords))
        self.assertIn('"frames"', figure.to_json())
        self.assertGreater(route_distance(result, coords)["Truck 1"], 0)
        html = playback_html(result, coords)
        self.assertIn('id="timeline"', html)
        self.assertIn('id="restart"', html)
        self.assertNotIn('"label":"▶ Play"', html)

    def test_algorithm_explanations_reference_real_functions(self):
        for algorithm in ALGORITHMS:
            tree = ast.parse((ROOT/algorithm["source"]).read_text(encoding="utf-8"))
            functions = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            self.assertIn(algorithm["function"], functions)


class DashboardInteractionTests(unittest.TestCase):
    def test_all_pages_and_empty_scope(self):
        from streamlit.testing.v1 import AppTest
        from research.app import PAGES
        app = AppTest.from_file(str(ROOT/"app.py"), default_timeout=45).run()
        for page in PAGES:
            app.radio(key="workspace").set_value(page).run()
            self.assertFalse(app.exception, page)
            app.sidebar.multiselect[0].set_value([]).run()
            self.assertFalse(app.exception, page+" empty")
            app.sidebar.multiselect[0].set_value([8,10,25,50,100]).run()
        app.radio(key="studio_mode").set_value("Algorithm execution").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("trace" in x.value for x in app.warning))

    def test_algorithm_choices_and_route_controls(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT/"app.py"), default_timeout=45).run()
        app.radio(key="workspace").set_value("Algorithms explained").run()
        for algorithm in ALGORITHMS:
            app.selectbox[0].set_value(algorithm["name"]).run()
            self.assertFalse(app.exception)
        app.radio(key="workspace").set_value("3D delivery studio").run()
        app.select_slider(key="studio_speed").set_value(2.).run()
        app.slider(key="studio_time").set_value(100.).run()
        app.checkbox[0].set_value(True).run()
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
