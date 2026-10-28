export type Cohort = "proposed" | "archive" | "rerun";

export type Row = {
  source: string;
  cohort: Cohort;
  algorithm: string;
  problemName: string;
  numCustomers: number | null;
  vehicleFileID: number | null;
  numUAVs: number | null;
  numTrucks: number | null;
  requireTruckAtDepot: number | null;
  requireDriver: number | null;
  Etype: number | null;
  cutoffTime: number | null;
  ITER: number | null;
  timestamp: string;
  ofv: number | null;
  bestBound: number | null;
  totalTime: number | null;
  isOptimal: number | null;
  numUAVcust: number | null;
  numTruckCust: number | null;
  waitingTruck: number | null;
  waitingUAV: number | null;
  solved: boolean;
  outcome: string;
  strategy?: string;
};

export type Benchmark = {
  problemName: string;
  numCustomers: number | null;
  locations: boolean;
  truckTravel: boolean;
  savedSolutions: number;
  issue: string;
};

export type ResultsData = {
  generatedAt: string;
  results: Row[];
  inventory: Benchmark[];
  savedFiles: number;
  issues: string[];
};

// vehicle, start, end, from node, to node, status
export type Segment = [string, number, number, number, number, string];

export type Sortie = {
  uav: number;
  launch: number;
  customer: number;
  recovery: number;
  launch_time: number;
  arrival_to_recovery_time: number;
  sortie_duration?: number;
  recovery_truck_arrival_time?: number;
};

export type Snapshot = {
  ofv: number | null;
  runtime: number | null;
  config: Record<string, string>;
  validation: Record<string, unknown> | null;
  route: number[];
  sorties: Sortie[];
  segments: Segment[];
  deliveries: [number, number][];
  events: { vehicle: string; type: string; node: number; time: number }[];
  warnings: string[];
  duration: number;
};

export type SolutionFile = {
  file: string;
  vehicleFileID: number | null;
  numUAVs: number | null;
  kind: "proposed" | "original";
  algorithm: string;
  snapshots: Snapshot[];
};

// nodeID, lon, lat, parcel weight
export type Coord = [number, number, number, number];

export type InstanceData = {
  problemName: string;
  coords: Coord[];
  solutions: SolutionFile[];
};

export type SourceExcerpt = { file: string; line: number; code: string };

export const METRICS = {
  ofv: "Makespan (s)",
  totalTime: "Runtime (s)",
  waitingTruck: "Truck waiting (s)",
  waitingUAV: "UAV waiting (s)",
  numUAVcust: "UAV customers",
  numTruckCust: "Truck customers",
} as const;

export type Metric = keyof typeof METRICS;

export const SIZES = [8, 10, 25, 50, 100] as const;
