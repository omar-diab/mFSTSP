#!/usr/bin/env python

"""
NO-GUROBI main.py for mFSTSP

Run command example:

python main.py 20170608T121632668184 101 3600 2 3 -1 1 1 3 1

Arguments:
python main.py <problemName> <vehicleFileID> <cutoffTime> <problemType> <numUAVs> <numTrucks> <requireTruckAtDepot> <requireDriver> <Etype> <ITER>

Important:
- This modified version only supports problemType = 2.
- It does NOT call Gurobi.
- It does NOT call solve_mfstsp_IP.py.
- It does NOT call solve_mfstsp_heuristic.py.
- It calls proposed_heuristic_no_gurobi.py instead.
"""

import sys
import datetime
import time
import os
import os.path
from collections import defaultdict

from parseCSV import *
from parseCSVstring import *

import distance_functions

from proposed_heuristic_no_gurobi import proposed_heuristic_no_gurobi, save_solution


# =============================================================
# Global constants
# =============================================================

startTime = time.time()

METERS_PER_MILE = 1609.34

problemTypeString = {
    1: "mFSTSP IP",
    2: "mFSTSP No-Gurobi Heuristic"
}

NODE_TYPE_DEPOT = 0
NODE_TYPE_CUST = 1

TYPE_TRUCK = 1
TYPE_UAV = 2

MODE_CAR = 1
MODE_BIKE = 2
MODE_WALK = 3
MODE_FLY = 4

ACT_TRAVEL = 0
ACT_SERVE_CUSTOMER = 1
ACT_DONE = 2


# =============================================================
# Helper nested dictionary
# =============================================================

def make_dict():
    return defaultdict(make_dict)


# =============================================================
# Data classes
# =============================================================

class make_node:
    def __init__(
        self,
        nodeType,
        latDeg,
        lonDeg,
        altMeters,
        parcelWtLbs,
        serviceTimeTruck,
        serviceTimeUAV,
        address
    ):
        self.nodeType = nodeType
        self.latDeg = latDeg
        self.lonDeg = lonDeg
        self.altMeters = altMeters
        self.parcelWtLbs = parcelWtLbs
        self.serviceTimeTruck = serviceTimeTruck
        self.serviceTimeUAV = serviceTimeUAV
        self.address = address


class make_vehicle:
    def __init__(
        self,
        vehicleType,
        takeoffSpeed,
        cruiseSpeed,
        landingSpeed,
        yawRateDeg,
        cruiseAlt,
        capacityLbs,
        launchTime,
        recoveryTime,
        serviceTime,
        batteryPower,
        flightRange
    ):
        self.vehicleType = vehicleType
        self.takeoffSpeed = takeoffSpeed
        self.cruiseSpeed = cruiseSpeed
        self.landingSpeed = landingSpeed
        self.yawRateDeg = yawRateDeg
        self.cruiseAlt = cruiseAlt
        self.capacityLbs = capacityLbs
        self.launchTime = launchTime
        self.recoveryTime = recoveryTime
        self.serviceTime = serviceTime
        self.batteryPower = batteryPower
        self.flightRange = flightRange


class make_travel:
    def __init__(
        self,
        takeoffTime,
        flyTime,
        landTime,
        totalTime,
        takeoffDistance,
        flyDistance,
        landDistance,
        totalDistance
    ):
        self.takeoffTime = takeoffTime
        self.flyTime = flyTime
        self.landTime = landTime
        self.totalTime = totalTime
        self.takeoffDistance = takeoffDistance
        self.flyDistance = flyDistance
        self.landDistance = landDistance
        self.totalDistance = totalDistance


# =============================================================
# Main controller
# =============================================================

class missionControl:
    def __init__(self):
        timestamp = datetime.datetime.strftime(
            datetime.datetime.now(),
            "%Y-%m-%d %H:%M:%S"
        )

        # ---------------------------------------------------------
        # Read command-line arguments
        # ---------------------------------------------------------
        if len(sys.argv) == 11:
            problemName = sys.argv[1]
            vehicleFileID = int(sys.argv[2])
            cutoffTime = float(sys.argv[3])
            problemType = int(sys.argv[4])
            numUAVs = int(sys.argv[5])
            numTrucks = int(sys.argv[6])
            requireTruckAtDepot = bool(int(sys.argv[7]))
            requireDriver = bool(int(sys.argv[8]))
            Etype = int(sys.argv[9])
            ITER = int(sys.argv[10])

            self.locationsFile = "Problems/%s/tbl_locations.csv" % problemName
            self.vehiclesFile = "Problems/tbl_vehicles_%d.csv" % vehicleFileID
            self.distmatrixFile = "Problems/%s/tbl_truck_travel_data_PG.csv" % problemName

            if problemType == 2:
                indicator = "NoGurobiHeuristic"
            else:
                indicator = "Unsupported"

            self.solutionSummaryFile = (
                "Problems/%s/tbl_solutions_%d_%d_%s.csv"
                % (problemName, vehicleFileID, numUAVs, indicator)
            )

        else:
            print("ERROR: You passed %d input parameters." % (len(sys.argv) - 1))
            print("")
            print("Correct usage:")
            print(
                "python main.py <problemName> <vehicleFileID> <cutoffTime> "
                "<problemType> <numUAVs> <numTrucks> "
                "<requireTruckAtDepot> <requireDriver> <Etype> <ITER>"
            )
            quit()

        # ---------------------------------------------------------
        # This modified file only supports no-Gurobi heuristic
        # ---------------------------------------------------------
        if problemType != 2:
            print("ERROR: This modified main.py only supports problemType = 2.")
            print("Do not use problemType = 1 because it uses the full IP/MILP.")
            print("")
            print("Use this format:")
            print(
                "python main.py %s %d %s 2 %d %d %d %d %d %d"
                % (
                    problemName,
                    vehicleFileID,
                    cutoffTime,
                    numUAVs,
                    numTrucks,
                    int(requireTruckAtDepot),
                    int(requireDriver),
                    Etype,
                    ITER
                )
            )
            quit()

        # ---------------------------------------------------------
        # Define data structures
        # ---------------------------------------------------------
        self.node = {}
        self.vehicle = {}
        self.travel = defaultdict(make_dict)

        # ---------------------------------------------------------
        # Read vehicle, location, and truck travel data
        # ---------------------------------------------------------
        self.readData(numUAVs)

        # ---------------------------------------------------------
        # Calculate UAV travel times
        # ---------------------------------------------------------
        for vehicleID in self.vehicle:
            if self.vehicle[vehicleID].vehicleType == TYPE_UAV:
                for i in self.node:
                    for j in self.node:
                        if j == i:
                            self.travel[vehicleID][i][j] = make_travel(
                                0.0, 0.0, 0.0, 0.0,
                                0.0, 0.0, 0.0, 0.0
                            )
                        else:
                            [
                                takeoffTime,
                                flyTime,
                                landTime,
                                totalTime,
                                takeoffDistance,
                                flyDistance,
                                landDistance,
                                totalDistance
                            ] = distance_functions.calcMultirotorTravelTime(
                                self.vehicle[vehicleID].takeoffSpeed,
                                self.vehicle[vehicleID].cruiseSpeed,
                                self.vehicle[vehicleID].landingSpeed,
                                self.vehicle[vehicleID].yawRateDeg,
                                self.node[i].altMeters,
                                self.vehicle[vehicleID].cruiseAlt,
                                self.node[j].altMeters,
                                self.node[i].latDeg,
                                self.node[i].lonDeg,
                                self.node[j].latDeg,
                                self.node[j].lonDeg,
                                -361,
                                -361
                            )

                            self.travel[vehicleID][i][j] = make_travel(
                                takeoffTime,
                                flyTime,
                                landTime,
                                totalTime,
                                takeoffDistance,
                                flyDistance,
                                landDistance,
                                totalDistance
                            )

        # ---------------------------------------------------------
        # Build no-Gurobi problem object
        # ---------------------------------------------------------
        print("Building no-Gurobi problem object...")
        problem = self.build_no_gurobi_problem(problemName, Etype)

        # ---------------------------------------------------------
        # Call no-Gurobi heuristic
        # ---------------------------------------------------------
        print("Calling NO-GUROBI proposed heuristic...")
        solution = proposed_heuristic_no_gurobi(problem)
        print("NO-GUROBI heuristic is done.")

        # ---------------------------------------------------------
        # Extract summary values
        # ---------------------------------------------------------
        objVal = solution["makespan"]
        bestBound = -1
        isOptimal = False

        waitingTruck = solution.get("truck_waiting_time", 0)
        waitingUAV = solution.get("uav_waiting_time", 0)

        numUAVcust = solution.get("num_uav_customers", 0)
        numTruckCust = solution.get("num_truck_customers", 0)

        total_time = time.time() - startTime

        print("")
        print("Total time for the whole process: %f" % total_time)
        print("Objective Function Value: %f" % objVal)
        print("Truck Waiting Time: %f" % waitingTruck)
        print("UAV Waiting Time: %f" % waitingUAV)
        print("Number of Truck Customers: %d" % numTruckCust)
        print("Number of UAV Customers: %d" % numUAVcust)
        print("Truck route:", solution.get("truck_route", []))
        print("UAV sorties:", solution.get("uav_sorties", []))
        print("")

        # ---------------------------------------------------------
        # Save separate no-Gurobi result CSV
        # ---------------------------------------------------------
        save_solution(solution, "results/no_gurobi_heuristic_results.csv")

        # ---------------------------------------------------------
        # Write in performance_summary.csv
        # ---------------------------------------------------------
        runString = " ".join(sys.argv[0:])

        with open("performance_summary.csv", "a") as myFile:
            header_part = (
                "%s, %d, %f, %d, %s, %d, %d, %s, %s, %d, %d, %s,"
                % (
                    problemName,
                    vehicleFileID,
                    cutoffTime,
                    problemType,
                    problemTypeString[problemType],
                    numUAVs,
                    numTrucks,
                    requireTruckAtDepot,
                    requireDriver,
                    Etype,
                    ITER,
                    runString
                )
            )
            myFile.write(header_part)

            numCustomers = len([
                nodeID for nodeID in self.node
                if self.node[nodeID].nodeType == NODE_TYPE_CUST
            ])

            result_part = (
                "%d, %s, %f, %f, %f, %s, %d, %d, %f, %f \n"
                % (
                    numCustomers,
                    timestamp,
                    objVal,
                    bestBound,
                    total_time,
                    isOptimal,
                    numUAVcust,
                    numTruckCust,
                    waitingTruck,
                    waitingUAV
                )
            )
            myFile.write(result_part)

        print("See 'performance_summary.csv' for statistics.")

        # ---------------------------------------------------------
        # Write simple solution summary file
        # ---------------------------------------------------------
        self.write_simple_solution_file(
            problemName=problemName,
            vehicleFileID=vehicleFileID,
            cutoffTime=cutoffTime,
            problemType=problemType,
            numUAVs=numUAVs,
            numTrucks=numTrucks,
            requireTruckAtDepot=requireTruckAtDepot,
            requireDriver=requireDriver,
            Etype=Etype,
            ITER=ITER,
            objVal=objVal,
            waitingTruck=waitingTruck,
            waitingUAV=waitingUAV,
            numTruckCust=numTruckCust,
            numUAVcust=numUAVcust,
            solution=solution
        )

        print("")
        print("See '%s' for no-Gurobi solution summary." % self.solutionSummaryFile)
        print("")

    # =============================================================
    # Convert old mFSTSP structures into new heuristic problem object
    # =============================================================

    def build_no_gurobi_problem(self, problemName, Etype):
        """
        Convert:
        self.node
        self.vehicle
        self.travel

        into the dictionary format used by proposed_heuristic_no_gurobi().
        """

        depot = 0

        customers = [
            nodeID for nodeID in self.node
            if self.node[nodeID].nodeType == NODE_TYPE_CUST
        ]

        # Find truck vehicle ID.
        truck_id = None
        for vehicleID in self.vehicle:
            if self.vehicle[vehicleID].vehicleType == TYPE_TRUCK:
                truck_id = vehicleID
                break

        if truck_id is None:
            raise ValueError("No truck vehicle found.")

        # Find UAV vehicle IDs.
        uavs = [
            vehicleID for vehicleID in self.vehicle
            if self.vehicle[vehicleID].vehicleType == TYPE_UAV
        ]

        if len(uavs) == 0:
            print("WARNING: No UAVs found. The solution will be truck-only.")

        # Droneable customers: parcel weight must fit at least one UAV.
        droneable_customers = []

        for j in customers:
            for v in uavs:
                if self.node[j].parcelWtLbs <= self.vehicle[v].capacityLbs:
                    droneable_customers.append(j)
                    break

        all_nodes = list(self.node.keys())

        # Truck travel time matrix.
        truck_time = {}

        for i in all_nodes:
            truck_time[i] = {}
            for j in all_nodes:
                if i == j:
                    truck_time[i][j] = 0.0
                else:
                    truck_time[i][j] = self.travel[truck_id][i][j].totalTime

        # UAV travel time matrix.
        uav_time = {}

        for v in uavs:
            uav_time[v] = {}
            for i in all_nodes:
                uav_time[v][i] = {}
                for j in all_nodes:
                    if i == j:
                        uav_time[v][i][j] = 0.0
                    else:
                        uav_time[v][i][j] = self.travel[v][i][j].totalTime

        # Truck service time.
        truck_service_time = {}

        for j in customers:
            truck_service_time[j] = self.node[j].serviceTimeTruck

        # UAV service time.
        uav_service_time = {}

        for v in uavs:
            uav_service_time[v] = {}
            for j in customers:
                uav_service_time[v][j] = self.node[j].serviceTimeUAV

        # UAV endurance.
        #
        # This is a simple no-Gurobi approximation:
        # Etype 4 = unlimited
        # otherwise:
        #   low range  = 700 seconds
        #   high range = 1400 seconds
        #
        # You can tune these values later if your professor wants closer paper behavior.
        uav_endurance = {}

        for v in uavs:
            if Etype == 4:
                uav_endurance[v] = float("inf")
            else:
                flight_range = str(self.vehicle[v].flightRange).lower()

                if flight_range == "high":
                    uav_endurance[v] = 1400.0
                else:
                    uav_endurance[v] = 700.0

        # Launch and recovery times.
        launch_time = {}
        recovery_time = {}

        for v in uavs:
            launch_time[v] = {
                "default": self.vehicle[v].launchTime
            }
            recovery_time[v] = {
                "default": self.vehicle[v].recoveryTime
            }

        problem = {
            "problem_id": problemName,
            "depot": depot,
            "customers": customers,
            "droneable_customers": droneable_customers,
            "uavs": uavs,
            "truck_time": truck_time,
            "uav_time": uav_time,
            "truck_service_time": truck_service_time,
            "uav_service_time": uav_service_time,
            "uav_endurance": uav_endurance,
            "launch_time": launch_time,
            "recovery_time": recovery_time,
        }

        return problem

    # =============================================================
    # Write simple no-Gurobi solution file
    # =============================================================

    def write_simple_solution_file(
        self,
        problemName,
        vehicleFileID,
        cutoffTime,
        problemType,
        numUAVs,
        numTrucks,
        requireTruckAtDepot,
        requireDriver,
        Etype,
        ITER,
        objVal,
        waitingTruck,
        waitingUAV,
        numTruckCust,
        numUAVcust,
        solution
    ):
        with open(self.solutionSummaryFile, "w") as myFile:
            myFile.write("NO-GUROBI HEURISTIC SOLUTION\n")
            myFile.write("====================================\n\n")

            myFile.write("problemName: %s\n" % problemName)
            myFile.write("vehicleFileID: %d\n" % vehicleFileID)
            myFile.write("cutoffTime: %f\n" % cutoffTime)
            myFile.write("problemType: %d\n" % problemType)
            myFile.write("problemTypeString: %s\n" % problemTypeString[problemType])
            myFile.write("numUAVs: %d\n" % numUAVs)
            myFile.write("numTrucks: %d\n" % numTrucks)
            myFile.write("requireTruckAtDepot: %s\n" % requireTruckAtDepot)
            myFile.write("requireDriver: %s\n" % requireDriver)
            myFile.write("Etype: %d\n" % Etype)
            myFile.write("ITER: %d\n\n" % ITER)

            myFile.write("Objective Function Value: %f\n" % objVal)
            myFile.write("Truck Waiting Time: %f\n" % waitingTruck)
            myFile.write("UAV Waiting Time: %f\n" % waitingUAV)
            myFile.write("Number of Truck Customers: %d\n" % numTruckCust)
            myFile.write("Number of UAV Customers: %d\n" % numUAVcust)
            myFile.write("Runtime: %f\n\n" % solution.get("runtime", 0))

            myFile.write("Validation:\n")
            myFile.write(str(solution.get("validation", {})))
            myFile.write("\n\n")

            myFile.write("Truck Customers:\n")
            myFile.write(str(solution.get("truck_customers", [])))
            myFile.write("\n\n")

            myFile.write("UAV Customers:\n")
            myFile.write(str(solution.get("uav_customers", [])))
            myFile.write("\n\n")

            myFile.write("Truck Route:\n")
            myFile.write(str(solution.get("truck_route", [])))
            myFile.write("\n\n")

            myFile.write("UAV Sorties:\n")
            for sortie in solution.get("uav_sorties", []):
                myFile.write(str(sortie) + "\n")

            myFile.write("\nActivity Log:\n")
            for activity in solution.get("activity_log", []):
                myFile.write(str(activity) + "\n")

    # =============================================================
    # Read input data
    # =============================================================

    def readData(self, numUAVs):
        # ---------------------------------------------------------
        # b) tbl_vehicles.csv
        # ---------------------------------------------------------
        tmpUAVs = 0

        rawData = parseCSVstring(
            self.vehiclesFile,
            returnJagged=False,
            fillerValue=-1,
            delimiter=",",
            commentChar="%"
        )

        for i in range(0, len(rawData)):
            vehicleID = int(rawData[i][0])
            vehicleType = int(rawData[i][1])
            takeoffSpeed = float(rawData[i][2])
            cruiseSpeed = float(rawData[i][3])
            landingSpeed = float(rawData[i][4])
            yawRateDeg = float(rawData[i][5])
            cruiseAlt = float(rawData[i][6])
            capacityLbs = float(rawData[i][7])
            launchTime = float(rawData[i][8])
            recoveryTime = float(rawData[i][9])
            serviceTime = float(rawData[i][10])
            batteryPower = float(rawData[i][11])
            flightRange = str(rawData[i][12])

            if vehicleType == TYPE_UAV:
                tmpUAVs += 1

                if tmpUAVs <= numUAVs:
                    self.vehicle[vehicleID] = make_vehicle(
                        vehicleType,
                        takeoffSpeed,
                        cruiseSpeed,
                        landingSpeed,
                        yawRateDeg,
                        cruiseAlt,
                        capacityLbs,
                        launchTime,
                        recoveryTime,
                        serviceTime,
                        batteryPower,
                        flightRange
                    )
            else:
                self.vehicle[vehicleID] = make_vehicle(
                    vehicleType,
                    takeoffSpeed,
                    cruiseSpeed,
                    landingSpeed,
                    yawRateDeg,
                    cruiseAlt,
                    capacityLbs,
                    launchTime,
                    recoveryTime,
                    serviceTime,
                    batteryPower,
                    flightRange
                )

        if tmpUAVs < numUAVs:
            print(
                "WARNING: You requested %d UAVs, but we only have data on %d UAVs."
                % (numUAVs, tmpUAVs)
            )
            print("We'll solve the problem with %d UAVs." % tmpUAVs)

        # ---------------------------------------------------------
        # a) tbl_locations.csv
        # ---------------------------------------------------------
        rawData = parseCSVstring(
            self.locationsFile,
            returnJagged=False,
            fillerValue=-1,
            delimiter=",",
            commentChar="%"
        )

        for i in range(0, len(rawData)):
            nodeID = int(rawData[i][0])
            nodeType = int(rawData[i][1])
            latDeg = float(rawData[i][2])
            lonDeg = float(rawData[i][3])
            altMeters = float(rawData[i][4])
            parcelWtLbs = float(rawData[i][5])

            if len(rawData[i]) == 10:
                addressStreet = str(rawData[i][6])
                addressCity = str(rawData[i][7])
                addressST = str(rawData[i][8])
                addressZip = str(rawData[i][9])
                address = "%s, %s, %s, %s" % (
                    addressStreet,
                    addressCity,
                    addressST,
                    addressZip
                )
            else:
                address = ""

            serviceTimeTruck = self.vehicle[1].serviceTime

            if numUAVs > 0 and 2 in self.vehicle:
                serviceTimeUAV = self.vehicle[2].serviceTime
            else:
                serviceTimeUAV = 0

            self.node[nodeID] = make_node(
                nodeType,
                latDeg,
                lonDeg,
                altMeters,
                parcelWtLbs,
                serviceTimeTruck,
                serviceTimeUAV,
                address
            )

        # ---------------------------------------------------------
        # c) tbl_truck_travel_data_PG.csv
        # ---------------------------------------------------------
        if os.path.isfile(self.distmatrixFile):
            rawData = parseCSV(
                self.distmatrixFile,
                returnJagged=False,
                fillerValue=-1,
                delimiter=","
            )

            for i in range(0, len(rawData)):
                tmpi = int(rawData[i][0])
                tmpj = int(rawData[i][1])
                tmpTime = float(rawData[i][2])
                tmpDist = float(rawData[i][3])

                for vehicleID in self.vehicle:
                    if self.vehicle[vehicleID].vehicleType == TYPE_TRUCK:
                        self.travel[vehicleID][tmpi][tmpj] = make_travel(
                            0.0,
                            tmpTime,
                            0.0,
                            tmpTime,
                            0.0,
                            tmpDist,
                            0.0,
                            tmpDist
                        )

        else:
            print("ERROR: Truck travel data is not available.")
            print("Missing file:")
            print(self.distmatrixFile)
            print("")
            print("Please provide a CSV file in this format:")
            print("from node ID | to node ID | travel time [seconds] | travel distance [meters]")
            exit()


# =============================================================
# Run
# =============================================================

if __name__ == "__main__":
    try:
        missionControl()
    except Exception as e:
        print("There was a problem. Sorry things didn't work out.")
        print("Error:")
        print(e)
        raise