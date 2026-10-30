"""Build data/transit.json (metro, FGC, tram lines + stations) from GTFS feeds.

Usage: python3 build_transit.py GTFS_ROOT OUT_DIR
GTFS_ROOT holds unzipped feeds from files.mobilitydatabase.org:
  g2359 = TMB (metro, funicular), g1003 / g1004 = TRAM, g1856 = FGC;
  grenfe = Renfe Cercanías (ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip), of which
  only Rodalies de Catalunya (route_id 51...) is kept.
Output: {"o":[lon,lat], "lines":[{"n","c","k","p":[flat 1e5 coords]}], "stations":[[x,y,"name","L1 L3","kind","tmb codes"]]}
"tmb codes" are TMB stop / platform codes ("126,326") for the live arrivals API (api.tmb.cat itransit), empty for others.
kind is metro / fgc / tram / rodalies / funicular / bus; bus stops are kept apart from rail stations.
"""
import csv, json, os, sys
from collections import defaultdict

ROOT, OUT = sys.argv[1], sys.argv[2]
O = (2.12, 41.36)
W, S, E, N = 2.03, 41.30, 2.30, 41.48           # map maxBounds
FEEDS = {"g2359": "metro", "g1003": "tram", "g1004": "tram", "g1856": "fgc", "grenfe": "rodalies"}
TRAM_COLOR = "00A28A"


def rows(feed, name):
    with open(os.path.join(ROOT, feed, name), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):  # Renfe pads every field with spaces
            yield {k.strip(): (v or "").strip() for k, v in r.items() if k}


def inside(lon, lat):
    return W <= lon <= E and S <= lat <= N


def xy(lon, lat):
    return [round((lon - O[0]) * 1e5), round((lat - O[1]) * 1e5)]


lines, stations = [], {}
for feed, kind in FEEDS.items():
    routes = {}
    for r in rows(feed, "routes.txt"):
        rt = int(r["route_type"])
        if feed == "grenfe" and not r["route_id"].startswith("51"):
            continue
        if r["route_short_name"] in ("MM", "RL1", "RL2") or r["route_long_name"].startswith("Cremallera"):
            continue
        routes[r["route_id"]] = {"n": r["route_short_name"], "c": TRAM_COLOR if kind == "tram" else (r.get("route_color") or "666666").upper(),
                                 "k": "bus" if rt == 3 else "funicular" if rt == 7 else kind}
    shapes_of, trip_of_shape = defaultdict(set), {}
    for t in rows(feed, "trips.txt"):
        if t["route_id"] in routes and t.get("shape_id"):
            shapes_of[(t["route_id"], t.get("direction_id", "0"))].add(t["shape_id"])
            trip_of_shape.setdefault(t["shape_id"], t["trip_id"])
    wanted = {s for ss in shapes_of.values() for s in ss}
    pts = defaultdict(list)
    for p in rows(feed, "shapes.txt"):
        if p["shape_id"] in wanted:
            pts[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]), float(p["shape_pt_lat"])))
    # one drawn line per route and direction: its longest shape, kept to the map area
    best_trip = {}
    for (rid, _), ss in shapes_of.items():
        sid = max(ss, key=lambda s: len(pts[s]))
        seq = [(x, y) for _, x, y in sorted(pts[sid])]
        cur, segs = [], []
        for x, y in seq:
            if inside(x, y):
                cur += xy(x, y)
            elif cur:
                segs.append(cur); cur = []
        if cur: segs.append(cur)
        for sg in segs:
            if len(sg) >= 4:
                lines.append({**routes[rid], "p": sg})
        best_trip[trip_of_shape[sid]] = (routes[rid]["n"], routes[rid]["k"])
    # stations served by those trips, merged by parent station
    stops = {s["stop_id"]: s for s in rows(feed, "stops.txt")}
    for st in rows(feed, "stop_times.txt"):
        if st["trip_id"] not in best_trip: continue
        name, k = best_trip[st["trip_id"]]
        k = "bus" if k == "bus" else "rail"
        s = stops.get(st["stop_id"])
        if not s: continue
        code = s.get("stop_code", "") if feed == "g2359" else ""
        s = stops.get(s.get("parent_station") or "", s)
        lon, lat = float(s["stop_lon"]), float(s["stop_lat"])
        if not inside(lon, lat): continue
        key = (k, s["stop_name"].strip(), round(lon, 3), round(lat, 3))
        e = stations.setdefault(key, [*xy(lon, lat), s["stop_name"].strip(), [], k, []])
        if name not in e[3]: e[3].append(name)
        if code and code not in e[5]: e[5].append(code)

out = {"o": O, "lines": lines, "stations": [[x, y, n, " ".join(ls), k, ",".join(cs)] for x, y, n, ls, k, cs in stations.values()]}
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump(out, open(os.path.join(OUT, "data", "transit.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(lines), "line pieces,", len(stations), "stations")
