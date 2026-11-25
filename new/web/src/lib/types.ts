export type Method = "IP" | "Heuristic";

// solved: finished · time_capped: exact model stopped at our shorter time limit
// license_needed: too big for the free Gurobi license · error: crashed · not_run: not reached yet
export type Status = "solved" | "time_capped" | "license_needed" | "error" | "not_run";

type Common = {
  problemName: string;
  numCustomers: number | null;
  vehicleFileID: number | null;
  method: Method;
  numUAVs: number | null;
  cutoffTime: number | null;
  ofv: number | null;
  bestBound: number | null;
  totalTime: number | null;
  isOptimal: boolean | null;
  numUAVcust: number | null;
  numTruckCust: number | null;
  waitingTruck: number | null;
  waitingUAV: number | null;
};

export type PaperRun = Common;
export type OurRun = Common & { status: Status; message: string; timestamp: string };

// One ALNS run (new/results/alns/alns_results.csv). status: solved | invalid | error
export type AlnsRun = {
  problemName: string;
  numCustomers: number | null;
  vehicleFileID: number | null;
  numUAVs: number | null;
  etype: number | null;
  seed: number | null;
  timeLimit: number | null;
  status: string;
  ofv: number | null;
  initialOfv: number | null;
  runtime: number | null;
  iterations: number | null;
  evaluations: number | null;
  numUAVcust: number | null;
  numTruckCust: number | null;
  waitingTruck: number | null;
  waitingUAV: number | null;
  verified: boolean | null;
  message: string;
  timestamp: string;
};

// Our evaluator re-timing the paper's saved solutions, per method and size.
export type ValidationRow = {
  method: Method;
  numCustomers: number;
  plans: number;
  feasible: number;
  verified: number;
  exact: number;
  meanDiffPct: number | null;
  minDiffPct: number | null;
  maxDiffPct: number | null;
  provenOptimal: number;
  provenOptimalExact: number;
  provenOptimalMinDiffPct: number | null;
};

// public/data/alns/<problem>_<vehicle>_<uavs>.json
export type AlnsSolution = {
  problemName: string;
  vehicleFileID: number;
  numUAVs: number;
  numCustomers: number;
  makespan: number;
  truck_route: number[];
  sorties: { uav: number; launch: number; customer: number; recovery: number; launch_start: number; launch_end: number; ready: number; recovery_start: number; recovery_end: number; hover: number; airborne: number; endurance: number }[];
  truck_arrival: number[];
  truck_departure: number[];
  operations: [number, "L" | "R" | "S", number, number, number][];
  history: { time: number; iteration: number; makespan: number }[];
  nodes: { id: number; lat: number; lon: number; parcelLbs: number }[];
};

export type ReproductionData = {
  generatedAt: string;
  paper: PaperRun[];
  ours: OurRun[];
  alns: AlnsRun[];
  validation: ValidationRow[];
  operatorTotals: { destroy: Record<string, number>; repair: Record<string, number> };
};

export const SIZES = [8, 10, 25, 50, 100] as const;
export const UAV_COUNTS = [1, 2, 3, 4] as const;
export const METHODS = ["IP", "Heuristic"] as const;

export const METHOD_LABEL: Record<Method, string> = {
  IP: "Exact model (IP)",
  Heuristic: "Paper's heuristic",
};

// From the comment line at the top of old/Problems/tbl_vehicles_10x.csv
export const VEHICLE_LABEL: Record<number, string> = {
  101: "High speed / Low range",
  102: "High speed / High range",
  103: "Low speed / Low range",
  104: "Low speed / High range",
};

export const STATUS_LABEL: Record<Status, string> = {
  solved: "Solved",
  time_capped: "Time-capped",
  license_needed: "License needed",
  error: "Error",
  not_run: "Not run yet",
};

export const alnsKey = (r: { problemName: string; vehicleFileID: number | null; numUAVs: number | null }) => `${r.problemName}|${r.vehicleFileID}|${r.numUAVs}`;

export const runKey = (r: Pick<Common, "problemName" | "vehicleFileID" | "method" | "numUAVs">) => `${r.problemName}|${r.vehicleFileID}|${r.method}|${r.numUAVs}`;
