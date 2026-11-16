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

export type ReproductionData = {
  generatedAt: string;
  paper: PaperRun[];
  ours: OurRun[];
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

export const runKey = (r: Pick<Common, "problemName" | "vehicleFileID" | "method" | "numUAVs">) => `${r.problemName}|${r.vehicleFileID}|${r.method}|${r.numUAVs}`;
