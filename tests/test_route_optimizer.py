import io
import itertools
import json
import urllib.parse

import pandas as pd

import route_optimizer as ro


def grid_stops(n=7):
    pts = [(45.440 + 0.004 * (i % 3), -73.760 + 0.006 * (i // 3)) for i in range(n)]
    return pd.DataFrame({"basin_id": [f"B{i}" for i in range(n)], "latitude": [p[0] for p in pts],
                         "longitude": [p[1] for p in pts],
                         "category": ["Urgent" if i in (2, 5) else "Inspect" for i in range(n)],
                         "address": [f"{i} rue Test" for i in range(n)]})


def brute_force(cost, nodes):
    return min(ro.route_cost([0, *p, 0], cost) for p in itertools.permutations(nodes))


def test_two_opt_close_to_optimal():
    s = grid_stops(7)
    pts = [(ro.DORVAL_DEPOT["latitude"], ro.DORVAL_DEPOT["longitude"])] + list(zip(s.latitude, s.longitude))
    dur, _ = ro.straight_line_matrix(pts)
    route = ro.order_stops(dur, [list(range(1, 8))])
    assert route[0] == 0 and route[-1] == 0 and sorted(route[1:-1]) == list(range(1, 8))
    assert ro.route_cost(route, dur) <= 1.05 * brute_force(dur, range(1, 8))     # within 5% of the best


def test_urgent_first_and_all_visited():
    plan = ro.plan_route(grid_stops(7), use_osrm=False, start_time="2026-11-16 07:00")
    cats = list(plan.stops["category"])
    assert cats[:2] == ["Urgent", "Urgent"] and set(cats[2:]) == {"Inspect"}
    assert sorted(plan.stops["basin_id"]) == sorted(grid_stops(7)["basin_id"])
    assert plan.source == "straight-line estimate"
    assert abs(plan.service_min - (2 * 20 + 5 * 15)) < 1e-9
    assert plan.stops["arrive"].iloc[0] > "07:00"


def test_offline_osrm_falls_back():
    def broken(*a, **k):
        raise OSError("no network")
    plan = ro.plan_route(grid_stops(4), use_osrm=True, opener=broken)
    assert plan.source == "straight-line estimate" and "straight-line" in plan.note


def test_osrm_responses_are_used():
    s = grid_stops(3)
    n = 4

    def fake(req, timeout=None):
        url = req.full_url
        if "/table/" in url:
            body = {"code": "Ok", "durations": [[0 if i == j else 60 * (i + j) for j in range(n)] for i in range(n)],
                    "distances": [[0 if i == j else 500 * (i + j) for j in range(n)] for i in range(n)]}
        else:
            body = {"code": "Ok", "routes": [{"geometry": {"coordinates": [[-73.7, 45.4], [-73.71, 45.41]]}}]}
        return io.BytesIO(json.dumps(body).encode())

    plan = ro.plan_route(s, use_osrm=True, opener=fake, priority_first=False)
    assert plan.source == "OSRM road network"
    assert plan.geometry == [(45.4, -73.7), (45.41, -73.71)]
    assert plan.drive_s == ro.route_cost([0, *[int(b[1:]) + 1 for b in plan.stops["basin_id"]], 0],
                                         [[0 if i == j else 60 * (i + j) for j in range(n)] for i in range(n)])


def test_google_links_chunked():
    plan = ro.plan_route(grid_stops(7).assign(category="Inspect"), use_osrm=False)
    big = pd.concat([plan.stops] * 3, ignore_index=True)          # 21 stops
    links = ro.google_maps_links(ro.DORVAL_DEPOT, big)
    for link in links:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        assert len(q.get("waypoints", [""])[0].split("|")) <= ro.GOOGLE_MAX_WAYPOINTS
    first = urllib.parse.parse_qs(urllib.parse.urlparse(links[0]).query)
    last = urllib.parse.parse_qs(urllib.parse.urlparse(links[-1]).query)
    depot = f"{ro.DORVAL_DEPOT['latitude']:.6f},{ro.DORVAL_DEPOT['longitude']:.6f}"
    assert first["origin"][0] == depot and last["destination"][0] == depot
    total_waypoints = sum(len(urllib.parse.parse_qs(urllib.parse.urlparse(l).query).get("waypoints", [""])[0].split("|"))
                          for l in links)
    assert total_waypoints + (len(links) - 1) == 21                # every stop appears once (leg ends included)


def test_crew_sheet_csv():
    plan = ro.plan_route(grid_stops(3), use_osrm=False)
    text = ro.crew_sheet_csv(plan).decode()
    assert text.splitlines()[0].startswith("stop,basin_id,address")
    assert len(text.splitlines()) == 4
