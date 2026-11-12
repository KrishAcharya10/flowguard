"""Fictional network for Plant X. Generic coordinates, invented names.

Every number here is a declared modelling assumption (see docs/ASSUMPTIONS.md).
Waypoint tuple: (code, name, lat, lon, is_decision_node, speed_kmh_to_next).
Distances are never hand-entered: d = haversine * circuity.
"""

CIRCUITY = 1.2

PLANT = ("PLANT", "Plant X Gate", 20.00, 75.00)

ROUTES = {
    "R1": {
        "name": "North Corridor", "cost_per_km": 55.0, "destination": "Northfield receiving gate",
        "waypoints": [
            ("R1-W0", "Plant X Gate", 20.00, 75.00, False, 45),
            ("R1-W1", "Junction N1", 20.55, 75.10, True, 45),
            ("R1-W2", "River Crossing South", 21.10, 75.25, False, 45),
            ("R1-W3", "River Crossing North", 21.60, 75.30, False, 45),
            ("R1-W4", "Ridge Toll", 22.15, 75.40, False, 45),
            ("R1-W5", "Northfield receiving gate", 22.60, 75.55, False, 45),
        ],
    },
    "R1A": {
        "name": "North Bypass", "cost_per_km": 55.0, "destination": "Ridge Toll (rejoin)",
        "alternative_of": "R1", "entry": "R1-W1", "rejoin": "R1-W4",
        "waypoints": [
            ("R1A-W0", "Junction N1", 20.55, 75.10, False, 42),
            ("R1A-W1", "Bypass East", 21.00, 75.72, False, 42),
            ("R1A-W2", "Plateau Road", 21.65, 75.86, False, 42),
            ("R1A-W3", "Ridge Toll", 22.15, 75.40, False, 42),
        ],
    },
    "R2": {
        "name": "East Corridor", "cost_per_km": 52.0, "destination": "Eastgate receiving gate",
        "waypoints": [
            ("R2-W0", "Plant X Gate", 20.00, 75.00, False, 48),
            ("R2-W1", "Junction E1", 20.10, 75.60, True, 48),
            ("R2-W2", "Market Town", 20.25, 76.25, False, 40),
            ("R2-W3", "Canal Bridge", 20.30, 76.90, False, 48),
            ("R2-W4", "Eastgate receiving gate", 20.45, 77.50, False, 48),
        ],
    },
    "R2A": {
        "name": "East Ring Road", "cost_per_km": 52.0, "destination": "Canal Bridge (rejoin)",
        "alternative_of": "R2", "entry": "R2-W1", "rejoin": "R2-W3",
        "waypoints": [
            ("R2A-W0", "Junction E1", 20.10, 75.60, False, 46),
            ("R2A-W1", "Ring Road South", 19.75, 76.25, False, 46),
            ("R2A-W2", "Canal Bridge", 20.30, 76.90, False, 46),
        ],
    },
    "R3": {
        "name": "South Coastal", "cost_per_km": 58.0, "destination": "Southbay receiving gate",
        "waypoints": [
            ("R3-W0", "Plant X Gate", 20.00, 75.00, False, 42),
            ("R3-W1", "Junction S1", 19.45, 74.85, True, 42),
            ("R3-W2", "Coast Road", 18.85, 74.60, False, 38),
            ("R3-W3", "Harbour Link", 18.30, 74.45, False, 42),
            ("R3-W4", "Southbay receiving gate", 17.85, 74.30, False, 42),
        ],
    },
    "R4": {
        "name": "West Link", "cost_per_km": 50.0, "destination": "Southbay west warehouse gate",
        "waypoints": [
            ("R4-W0", "Plant X Gate", 20.00, 75.00, False, 50),
            ("R4-W1", "Junction W1", 19.90, 74.35, True, 50),
            ("R4-W2", "Quarry Pass", 19.70, 73.70, False, 44),
            ("R4-W3", "Southbay west warehouse gate", 19.40, 73.10, False, 50),
        ],
    },
}

CUSTOMERS = {
    "CUST-A": {"name": "Northfield Mouldings (fictional)", "route": "R1"},
    "CUST-B": {"name": "Eastgate Films (fictional)", "route": "R2"},
    "CUST-C": {"name": "Southbay Packaging (fictional)", "route": "R3"},
}

TRANSPORTERS = {
    "TR-1": {"name": "Swiftline Haulage (fictional)", "sigma_factor": 1.0},
    "TR-2": {"name": "Meridian Bulk Carriers (fictional)", "sigma_factor": 1.15},
    "TR-3": {"name": "Coastwise Logistics (fictional)", "sigma_factor": 1.3},
}

# Each primary route ends at one customer's receiving gate (used when a coordinator creates an order).
ROUTE_CUSTOMER = {"R1": "CUST-A", "R2": "CUST-B", "R3": "CUST-C", "R4": "CUST-C"}
PRODUCTS = ["PP-H110", "HDPE-B52", "LDPE-F20", "FILM-L30", "PACK-P40", "CAP-H08"]
