"""License smoke test, separate from benchmark experiments. No credential contents logged."""
import json
import sys
import time
from pathlib import Path

import gurobipy as gp

HERE = Path(__file__).resolve().parent
output = HERE / "environment_check.json"
if output.exists():
    raise FileExistsError(output)
record = {"python": sys.executable, "python_version": sys.version, "gurobi_version": ".".join(map(str, gp.gurobi.version()))}
started = time.perf_counter()
try:
    with gp.Env() as env, gp.Model("license_smoke_test", env=env) as model:
        model.Params.TimeLimit = 10
        model.Params.LogFile = str(HERE / "license_smoke_solver.log")
        x = model.addVar(vtype=gp.GRB.BINARY)
        model.setObjective(x, gp.GRB.MAXIMIZE)
        model.optimize()
        record.update(status=model.Status, solution_count=model.SolCount, objective=model.ObjVal if model.SolCount else None)
except gp.GurobiError as error:
    record.update(error_code=error.errno, error=str(error))
finally:
    record["elapsed_seconds"] = time.perf_counter()-started
    output.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
