"""Build madrid/data/transit.json (Metro, Metro Ligero, Cercanías, EMT buses) from the CRTM GTFS feeds.

Usage: python3 build_transit.py GTFS_ROOT OUT_DIR
GTFS_ROOT holds the unzipped feeds from datos.crtm.es (https://crtm.maps.arcgis.com/sharing/rest/content/items/<id>/data):
  metro = 5c7f2951962540d69ffe8f640d94c246, ml = aaed26cc0ff64b0c947ac0bc3e033196 (Metro Ligero),
  cer = 1a25440bf66f499bae2657ec7fb40144 (Cercanías), emt = 868df0e58fca47e79b942902dffd7da0 (EMT buses).
Output (same shape as Barcelona's): {"o":[lon,lat], "lines":[{"n","c","k","p":[flat 1e5 coords]}],
  "stations":[[x,y,"name","L1 L3","kind","stop codes"]]}; kind is rail or bus for stations, metro / ml / cercanias / bus for lines.
"""
import csv, json, os, sys
from collections import defaultdict

ROOT, OUT = sys.argv[1], sys.argv[2]
O = (-3.70, 40.42)
W, S, E, N = -3.95, 40.28, -3.45, 40.68          # map maxBounds
FEEDS = {"metro": "metro", "ml": "ml", "cer": "cercanias", "emt": "bus"}


def rows(feed, name):
    with open(os.path.join(ROOT, feed, name), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            yield {k.strip(): (v or "").strip() for k, v in r.items() if k}


def inside(lon, lat):
    return W <= lon <= E and S <= lat <= N


def xy(lon, lat):
    return [round((lon - O[0]) * 1e5), round((lat - O[1]) * 1e5)]


def nice(n):  # "PLAZA DE CASTILLA" -> "Plaza de Castilla"
    if n != n.upper(): return n
    small = {"de", "del", "la", "las", "los", "el", "y", "a"}
    return " ".join(w if i and w in small else w[:1].upper() + w[1:] for i, w in enumerate(n.lower().split()))


lines, stations = [], {}
for feed, kind in FEEDS.items():
    routes = {}
    for r in rows(feed, "routes.txt"):
        c = (r.get("route_color") or "666666").upper()
        if c == "FFFFFF": c = (r.get("route_text_color") or "005AA9").upper()   # Ramal Ópera-Príncipe Pío
        routes[r["route_id"]] = {"n": r["route_short_name"], "c": c, "k": kind}
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
    best_trip, drawn = {}, set()
    for (rid, _), ss in shapes_of.items():
        sid = max(ss, key=lambda s: len(pts[s]))
        seq = [(x, y) for _, x, y in sorted(pts[sid])]
        cur, segs = [], []
        for x, y in seq:
            if inside(x, y):
                q = xy(x, y)
                if not cur or abs(q[0] - cur[-2]) + abs(q[1] - cur[-1]) >= 4:   # drop points under ~4 m apart
                    cur += q
            elif cur:
                segs.append(cur); cur = []
        if cur: segs.append(cur)
        key = (routes[rid]["n"], tuple(segs[0][:4]) if segs else ())
        if kind == "cercanias" and key in drawn: continue   # Cercanías lists each direction as its own route
        drawn.add(key)
        for sg in segs:
            if len(sg) >= 4:
                lines.append({**routes[rid], "p": sg})
        best_trip[trip_of_shape[sid]] = (routes[rid]["n"], kind)
    # stations served by those trips, merged by parent station (bus stops by stop)
    stops = {s["stop_id"]: s for s in rows(feed, "stops.txt")}
    for st in rows(feed, "stop_times.txt"):
        if st["trip_id"] not in best_trip: continue
        name, k = best_trip[st["trip_id"]]
        k = "bus" if k == "bus" else "rail"
        s = stops.get(st["stop_id"])
        if not s: continue
        code = s.get("stop_code", "") if feed == "emt" else ""
        s = stops.get(s.get("parent_station") or "", s)
        lon, lat = float(s["stop_lon"]), float(s["stop_lat"])
        if not inside(lon, lat): continue
        sname = nice(s["stop_name"].strip())
        key = (k, sname.lower(), round(lon, 3), round(lat, 3))
        e = stations.setdefault(key, [*xy(lon, lat), sname, [], k, []])
        if name not in e[3]: e[3].append(name)
        if code and code not in e[5]: e[5].append(code)

out = {"o": O, "lines": lines, "stations": [[x, y, n, " ".join(ls), k, ",".join(cs)] for x, y, n, ls, k, cs in stations.values()]}
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump(out, open(os.path.join(OUT, "data", "transit.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(lines), "line pieces,", len(stations), "stations")
