"""Network for the fictional Plant X (Waluj MIDC area, Maharashtra). Real town and road names, invented companies.

Every number here is a declared modelling assumption (see docs/ASSUMPTIONS.md).
Waypoint tuple: (code, name, lat, lon, is_decision_node, speed_kmh_to_next).
Distances are never hand-entered: d = haversine * circuity.
"""

CIRCUITY = 1.2

PLANT = ("PLANT", "Plant X Gate, Waluj MIDC", 20.00, 75.00)

ROUTES = {
    "R1": {
        "name": "Waluj to Pithampur", "cost_per_km": 55.0, "destination": "Sharma Mouldings gate, Pithampur",
        "waypoints": [
            ("R1-W0", "Plant X Gate, Waluj MIDC", 20.00, 75.00, False, 45),
            ("R1-W1", "Chalisgaon Junction", 20.55, 75.10, True, 45),
            ("R1-W2", "Jalgaon Bypass", 21.10, 75.25, False, 45),
            ("R1-W3", "Tapi River Bridge", 21.60, 75.30, False, 45),
            ("R1-W4", "Sendhwa Toll Plaza", 22.15, 75.40, False, 45),
            ("R1-W5", "Sharma Mouldings gate, Pithampur", 22.60, 75.55, False, 45),
        ],
    },
    "R1A": {
        "name": "Dhule Bypass", "cost_per_km": 55.0, "destination": "Sendhwa Toll Plaza (rejoin)",
        "alternative_of": "R1", "entry": "R1-W1", "rejoin": "R1-W4",
        "waypoints": [
            ("R1A-W0", "Chalisgaon Junction", 20.55, 75.10, False, 42),
            ("R1A-W1", "Dhule Link Road", 21.00, 75.72, False, 42),
            ("R1A-W2", "Shirpur Road", 21.65, 75.86, False, 42),
            ("R1A-W3", "Sendhwa Toll Plaza", 22.15, 75.40, False, 42),
        ],
    },
    "R2": {
        "name": "Waluj to Amravati", "cost_per_km": 52.0, "destination": "Vidarbha Flexi Films gate, Amravati",
        "waypoints": [
            ("R2-W0", "Plant X Gate, Waluj MIDC", 20.00, 75.00, False, 48),
            ("R2-W1", "Jalna Junction", 20.10, 75.60, True, 48),
            ("R2-W2", "Buldhana Market Town", 20.25, 76.25, False, 40),
            ("R2-W3", "Purna River Bridge", 20.30, 76.90, False, 48),
            ("R2-W4", "Vidarbha Flexi Films gate, Amravati", 20.45, 77.50, False, 48),
        ],
    },
    "R2A": {
        "name": "Jalna Ring Road", "cost_per_km": 52.0, "destination": "Purna River Bridge (rejoin)",
        "alternative_of": "R2", "entry": "R2-W1", "rejoin": "R2-W3",
        "waypoints": [
            ("R2A-W0", "Jalna Junction", 20.10, 75.60, False, 46),
            ("R2A-W1", "Jalna Ring Road South", 19.75, 76.25, False, 46),
            ("R2A-W2", "Purna River Bridge", 20.30, 76.90, False, 46),
        ],
    },
    "R3": {
        "name": "Waluj to Satara", "cost_per_km": 58.0, "destination": "Sahyadri Packaging gate, Satara",
        "waypoints": [
            ("R3-W0", "Plant X Gate, Waluj MIDC", 20.00, 75.00, False, 42),
            ("R3-W1", "Ahmednagar Junction", 19.45, 74.85, True, 42),
            ("R3-W2", "Supa Toll Plaza", 18.85, 74.60, False, 38),
            ("R3-W3", "Shirwal Link Road", 18.30, 74.45, False, 42),
            ("R3-W4", "Sahyadri Packaging gate, Satara", 17.85, 74.30, False, 42),
        ],
    },
    "R4": {
        "name": "Waluj to Bhiwandi", "cost_per_km": 50.0, "destination": "Sahyadri Packaging warehouse gate, Bhiwandi",
        "waypoints": [
            ("R4-W0", "Plant X Gate, Waluj MIDC", 20.00, 75.00, False, 50),
            ("R4-W1", "Nashik Junction", 19.90, 74.35, True, 50),
            ("R4-W2", "Kasara Ghat", 19.70, 73.70, False, 44),
            ("R4-W3", "Sahyadri Packaging warehouse gate, Bhiwandi", 19.40, 73.10, False, 50),
        ],
    },
}

CUSTOMERS = {
    "CUST-A": {"name": "Sharma Mouldings Pvt Ltd (fictional)", "route": "R1"},
    "CUST-B": {"name": "Vidarbha Flexi Films Pvt Ltd (fictional)", "route": "R2"},
    "CUST-C": {"name": "Sahyadri Packaging Industries (fictional)", "route": "R3"},
}

TRANSPORTERS = {
    "TR-1": {"name": "Sai Krupa Roadlines (fictional)", "sigma_factor": 1.0},
    "TR-2": {"name": "Deccan Bulk Carriers (fictional)", "sigma_factor": 1.15},
    "TR-3": {"name": "Konkan Express Logistics (fictional)", "sigma_factor": 1.3},
}

# Short destination codes used in order references, e.g. ORD-PTH-1116-01 = Pithampur, 16 Nov, number 1.
ROUTE_CODE = {"R1": "PTH", "R2": "AMV", "R3": "SAT", "R4": "BHW"}

# Each primary route ends at one customer's receiving gate (used when a coordinator creates an order).
ROUTE_CUSTOMER = {"R1": "CUST-A", "R2": "CUST-B", "R3": "CUST-C", "R4": "CUST-C"}
PRODUCTS = ["PP-H110", "HDPE-B52", "LDPE-F20", "FILM-L30", "PACK-P40", "CAP-H08"]
