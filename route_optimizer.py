"""
route_optimizer.py: the vacuum truck's route
--------------------------------------------
Turns "these basins need a crew" into "drive them in this order": a numbered stop list, the line to
draw on the map, the total time (driving + cleaning) and Google Maps links the crew can open on a phone.

HOW (and why this way):
1. TRAVEL TIMES. One request to the free OSRM routing server (OpenStreetMap roads, no API key) returns the
   driving time between EVERY pair of stops (the "table" service). Real street times matter: two basins
   200 m apart can be 2 km apart by road (one-way streets, the 20 highway, the railway).
   No internet / server down -> straight-line distance x 1.35 (typical street detour) at 25 km/h, clearly
   labelled as an estimate. The demo never breaks.
2. ORDER. Visiting N basins in the best order is the travelling salesman problem. For the 5-30 stops of a
   day's route we use two classic heuristics that a judge can check by hand:
     * nearest neighbour: from the depot, always drive to the closest basin not yet visited;
     * 2-opt: then keep reversing any stretch of the route that makes it shorter, until nothing improves.
   For this size, 2-opt usually lands within a few percent of the best possible route, in milliseconds.
   (We rejected OSRM's own "trip" service: it can't put the urgent basins first.)
3. URGENT FIRST. With priority_first=True, all 🔴 basins are visited (in their best order) before the 🟠 ones:
   a slightly longer drive, but the basins that will overflow tonight are done first.
4. THE LINE. A second OSRM request ("route") returns the road geometry of the final order, drawn on the map.

The public OSRM server is a free demo service (light use only, no guarantees): fine for a pitch and a pilot
of a few routes a day. A real deployment runs its own OSRM server (open source) on Quebec's road data.
"""

import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import pandas as pd

OSRM_URL = "https://router.project-osrm.org"
USER_AGENT = "DrainShield-student-prototype/0.3 (McGill)"
TIMEOUT_S = 8
DETOUR_FACTOR = 1.35          # streets vs straight line (fallback only)
FALLBACK_SPEED_KMH = 25       # urban truck speed with stops (fallback only)
GOOGLE_MAX_WAYPOINTS = 8      # Google Maps app: about 10 stops per route including start and end

# Dorval Public Works (Travaux publics), 550 boul. Bouchard. Coordinates are APPROXIMATE (next to 530 Bouchard):
# confirm the yard gate with the city.
DORVAL_DEPOT = {"name": "Dorval Public Works, 550 boul. Bouchard", "latitude": 45.4466, "longitude": -73.7360}

SERVICE_MIN = {"Urgent": 20, "Inspect": 15, "Offline": 10}   # minutes on site per stop (vacuum + inspect + log)
DEFAULT_SERVICE_MIN = 15


# ---------------------------------------------------------------------------
# Travel times
# ---------------------------------------------------------------------------
def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def straight_line_matrix(points):
    """(durations_s, distances_m) estimated from straight lines. points = [(lat, lon), ...]"""
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    dur = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                d = haversine_m(*points[i], *points[j]) * DETOUR_FACTOR
                dist[i][j] = d
                dur[i][j] = d / (FALLBACK_SPEED_KMH / 3.6)
    return dur, dist


def _get_json(url, opener=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


def _coord_string(points):
    return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)        # OSRM wants lon,lat


def osrm_matrix(points, opener=None):
    """(durations_s, distances_m) by road from OSRM's table service. Raises on any problem."""
    url = f"{OSRM_URL}/table/v1/driving/{_coord_string(points)}?annotations=duration,distance"
    data = _get_json(url, opener)
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("message", data.get("code")))
    dur, dist = data["durations"], data["distances"]
    if any(v is None for row in dur for v in row):
        raise RuntimeError("some stops are not reachable by road")
    return dur, dist


def osrm_geometry(points, opener=None):
    """Road geometry [(lat, lon), ...] through the points in order, from OSRM's route service."""
    url = f"{OSRM_URL}/route/v1/driving/{_coord_string(points)}?overview=full&geometries=geojson&steps=false"
    data = _get_json(url, opener)
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("message", data.get("code")))
    return [(lat, lon) for lon, lat in data["routes"][0]["geometry"]["coordinates"]]


# ---------------------------------------------------------------------------
# Order of visit
# ---------------------------------------------------------------------------
def route_cost(route, cost):
    return sum(cost[a][b] for a, b in zip(route, route[1:]))


def nearest_neighbor(start, nodes, cost):
    """Greedy order: from `start`, always go to the closest node not yet visited."""
    order, left, here = [], list(nodes), start
    while left:
        nxt = min(left, key=lambda j: (cost[here][j], j))
        order.append(nxt)
        left.remove(nxt)
        here = nxt
    return order


def two_opt(route, cost, block=None, max_rounds=50):
    """Improve a route (first and last node fixed) by reversing stretches while it gets shorter.
    block: optional {node: group}; a stretch is only reversed inside one group, so urgent stays first."""
    best = list(route)
    best_cost = route_cost(best, cost)
    for _ in range(max_rounds):
        improved = False
        for i in range(1, len(best) - 2):
            for k in range(i + 1, len(best) - 1):
                if block is not None and block[best[i]] != block[best[k]]:
                    continue
                candidate = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                c = route_cost(candidate, cost)
                if c < best_cost - 1e-9:
                    best, best_cost, improved = candidate, c, True
        if not improved:
            break
    return best


def order_stops(cost, groups, start=0, end=0):
    """Visit order over matrix indices. groups = lists of indices visited group after group (urgent first):
    nearest neighbour group by group, then 2-opt on the whole loop, never mixing groups."""
    route, here, block = [start], start, {}
    for g_num, g in enumerate(groups):
        part = nearest_neighbor(here, g, cost)
        route += part
        block.update({j: g_num for j in part})
        if part:
            here = part[-1]
    route.append(end)
    return two_opt(route, cost, block)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
@dataclass
class RoutePlan:
    stops: pd.DataFrame                    # crew sheet, one row per basin in visit order
    geometry: list                         # [(lat, lon), ...] line to draw
    drive_s: float
    drive_m: float
    service_min: float
    source: str                            # "OSRM road network" or "straight-line estimate"
    google_links: list = field(default_factory=list)
    note: str = ""

    @property
    def total_min(self):
        return self.drive_s / 60 + self.service_min


def google_maps_links(depot, stops, max_waypoints=GOOGLE_MAX_WAYPOINTS):
    """Google Maps directions links for the route, split in legs the app can open (~10 stops each).
    Each leg starts where the previous one ended; the last one returns to the depot."""
    pts = [(depot["latitude"], depot["longitude"])] + list(zip(stops["latitude"], stops["longitude"])) \
        + [(depot["latitude"], depot["longitude"])]
    links, i = [], 0
    while i < len(pts) - 1:
        leg = pts[i:i + max_waypoints + 2]                          # origin + waypoints + destination
        q = {"api": "1", "origin": f"{leg[0][0]:.6f},{leg[0][1]:.6f}",
             "destination": f"{leg[-1][0]:.6f},{leg[-1][1]:.6f}", "travelmode": "driving"}
        if len(leg) > 2:
            q["waypoints"] = "|".join(f"{a:.6f},{b:.6f}" for a, b in leg[1:-1])
        links.append("https://www.google.com/maps/dir/?" + urllib.parse.urlencode(q, safe=",|"))
        i += len(leg) - 1
    return links


def plan_route(stops, depot=DORVAL_DEPOT, start_time=None, priority_first=True, use_osrm=True,
               service_min=SERVICE_MIN, opener=None):
    """stops: DataFrame with basin_id, latitude, longitude, category ('Urgent'/'Inspect'), and optionally
    address, priority, reason. Returns a RoutePlan."""
    stops = stops.dropna(subset=["latitude", "longitude"]).drop_duplicates("basin_id").reset_index(drop=True)
    if stops.empty:
        raise ValueError("no basin to visit")
    if "category" not in stops:
        stops["category"] = "Inspect"
    points = [(depot["latitude"], depot["longitude"])] + list(zip(stops["latitude"], stops["longitude"]))

    source, note = "straight-line estimate", ""
    if use_osrm:
        try:
            dur, dist = osrm_matrix(points, opener)
            source = "OSRM road network"
        except Exception as e:                                       # offline, server busy, bad point...
            note = ("Couldn't reach the online road-routing service, so drive times are estimated from "
                    "straight-line distance (× 1.35 for streets).")
    if source != "OSRM road network":
        dur, dist = straight_line_matrix(points)

    idx = {i + 1 for i in range(len(stops))}
    if priority_first:
        urgent = [i + 1 for i, c in enumerate(stops["category"]) if c == "Urgent"]
        groups = [urgent, sorted(idx - set(urgent))]
    else:
        groups = [sorted(idx)]
    route = order_stops(dur, groups)

    geometry = [points[i] for i in route]
    if source == "OSRM road network":
        try:
            geometry = osrm_geometry([points[i] for i in route], opener)
        except Exception:
            note = "Road line unavailable: drawn as straight segments (times are still by road)."

    t = pd.Timestamp(start_time) if start_time is not None else pd.Timestamp.now().normalize() + pd.Timedelta(hours=7)
    rows, drive_s, drive_m, service_total = [], 0.0, 0.0, 0.0
    for n, (a, b) in enumerate(zip(route, route[1:]), start=1):
        leg_s, leg_m = dur[a][b], dist[a][b]
        drive_s += leg_s
        drive_m += leg_m
        t += pd.Timedelta(seconds=leg_s)
        if b == 0:                                                   # back at the depot
            back = t
            break
        s = stops.iloc[b - 1]
        svc = service_min.get(s["category"], DEFAULT_SERVICE_MIN)
        rows.append({"stop": n, "basin_id": s["basin_id"], "address": s.get("address", "") or "",
                     "category": s["category"], "priority": s.get("priority", s["category"]),
                     "reason": s.get("reason", "") or "",
                     "drive_min": round(leg_s / 60, 1), "drive_km": round(leg_m / 1000, 2),
                     "arrive": t.strftime("%H:%M"), "service_min": svc,
                     "depart": (t + pd.Timedelta(minutes=svc)).strftime("%H:%M"),
                     "latitude": s["latitude"], "longitude": s["longitude"],
                     "done": ""})
        t += pd.Timedelta(minutes=svc)
        service_total += svc
    sheet = pd.DataFrame(rows)
    plan = RoutePlan(stops=sheet, geometry=geometry, drive_s=drive_s, drive_m=drive_m, service_min=service_total,
                     source=source, note=note)
    plan.google_links = google_maps_links(depot, sheet)
    plan.back_at_depot = back.strftime("%H:%M")
    return plan


def crew_sheet_csv(plan):
    cols = ["stop", "basin_id", "address", "priority", "reason", "arrive", "service_min", "depart",
            "drive_min", "drive_km", "latitude", "longitude", "done"]
    return plan.stops[[c for c in cols if c in plan.stops]].to_csv(index=False).encode("utf-8")
