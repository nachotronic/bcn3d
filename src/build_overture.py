"""Build the Barcelona 3D page from Overture Maps (OSM-derived) instead of Overpass.

Usage: python3 build_overture.py OUT_DIR   (needs: pip install duckdb)
Writes OUT_DIR/index.html (template + inlined MapLibre CSS), OUT_DIR/data/base.json (sea, parks)
and OUT_DIR/data/t/<i>_<j>.json tiles (buildings, streets) that the page loads for the area in view.
Coordinates are integers in 1e-5 degrees relative to the file's origin "o".
"""
import json, os, sys, duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
REL = os.environ.get("OVERTURE_RELEASE", "2026-10-21.0")
S, W, N, E = 41.30, 2.03, 41.48, 2.30      # Barcelona + surroundings (= the page's maxBounds)
TW, TH = 0.02, 0.015                      # tile size in degrees (~1.7 x 1.7 km)
NX, NY = round((E - W) / TW), round((N - S) / TH)
ROOT = f"s3://overturemaps-us-west-2/release/{REL}"
BOX = f"bbox.xmin < {E} and bbox.xmax > {W} and bbox.ymin < {N} and bbox.ymax > {S}"
ENV = f"ST_MakeEnvelope({W}, {S}, {E}, {N})"

c = duckdb.connect()
c.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
c.sql("CREATE SECRET s (TYPE s3, PROVIDER config, KEY_ID '', SECRET '', REGION 'us-west-2')")


def SRC(theme, typ):
    staged = os.environ.get("OVERTURE_STAGE")  # dir of <type>.parquet pre-cut to the bbox (much faster)
    return f"'{staged}/{typ}.parquet'" if staged else f"'{ROOT}/theme={theme}/type={typ}/*', hive_partitioning=1"


def rows(theme, typ, cols, where="true", clip=False):
    g = f"ST_Intersection(geometry, {ENV})" if clip else "geometry"
    q = f"select {cols}, ST_AsGeoJSON({g}) as g from read_parquet({SRC(theme, typ)}) where {BOX} and {where}"
    return c.sql(q).fetchall()


def enc(ring, o, closed=True):
    pts = ring[:-1] if closed and len(ring) > 1 and ring[0] == ring[-1] else ring
    out, last = [], None
    for x, y in pts:
        q = (round((x - o[0]) * 1e5), round((y - o[1]) * 1e5))
        if q != last: out += q; last = q        # drop points that collapse at 1 m precision
    return out


def tile_of(x, y):
    return min(NX - 1, max(0, int((x - W) / TW))), min(NY - 1, max(0, int((y - S) / TH)))


def origin(t):
    return (round(W + t[0] * TW, 3), round(S + t[1] * TH, 3))


def polys(g):
    g = json.loads(g)
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    if g["type"] == "GeometryCollection":
        return [p for s in g["geometries"] for p in polys(json.dumps(s))]
    return []


def lines(g):
    g = json.loads(g)
    return [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []


def height(h, floors, typ):
    if h is None and floors:
        h = floors * 3.3 + 1
    return round(min(h if h is not None else 12.0, 250), 1)


TAPER = {"pyramidal": lambda z: 1 - z, "cone": lambda z: 1 - z,
         "dome": lambda z: (1 - z * z) ** 0.5, "round": lambda z: (1 - z * z) ** 0.5,
         "onion": lambda z: max(0.0, 1.15 * (1 - z) ** 0.7 * (1 + 0.6 * z) - 0.15)}


def shrink(ring, k):
    """Scale a ring about its vertex centroid (k=1 unchanged)."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    cx = sum(x for x, _ in pts) / len(pts); cy = sum(y for _, y in pts) / len(pts)
    return [[cx + (x - cx) * k, cy + (y - cy) * k] for x, y in pts]


def solid(ring, base, top, extra):
    f = {"h": round(top, 1), "r": ring, **extra}   # ring encoded later, relative to its tile
    if base > 0.05: f["m"] = round(base, 1)
    return f


buildings = []
cols = "height, num_floors, min_height, min_floor, names.primary, roof_shape, roof_height, facade_color"
# names of buildings modelled from parts, so hovering a tower still says "Sagrada Família"
part_names = dict(c.sql(
    f"select id, names.primary from read_parquet({SRC('buildings', 'building')}) where {BOX} and has_parts "
    "and names.primary is not null").fetchall())
# street address of each building: the first address point that falls inside its footprint
addr = dict(c.sql(
    f"select b.id, first(a.street || ' ' || coalesce(a.number, '') order by a.number) "
    f"from read_parquet({SRC('buildings', 'building')}) b join read_parquet({SRC('addresses', 'address')}) a "
    f"on ST_Contains(b.geometry, a.geometry) where a.street is not null group by b.id").fetchall())


# census section of each building (index into data/sections.json), when build_sections.py ran first
sec = {}
if os.path.exists(os.path.join(OUT, "sections.geojson")):
    sec = dict(c.sql(
        f"select b.id, first(s.i) from read_parquet({SRC('buildings', 'building')}) b "
        f"join ST_Read('{os.path.join(OUT, 'sections.geojson')}') s on ST_Contains(ST_SetCRS(s.geom, 'OGC:CRS84'), ST_PointOnSurface(b.geometry)) "
        f"where {BOX.replace('bbox.', 'b.bbox.')} group by b.id").fetchall())


def nice(a):
    return " ".join(w if w.isupper() and len(w) <= 3 and any(ch.isdigit() for ch in w) else w.capitalize()
                    for w in a.split()) if a else a


# buildings described by parts (e.g. Sagrada Família towers) are drawn from their parts instead
plain = rows("buildings", "building", cols + ", id as building_id", "not coalesce(has_parts, false)")
parts = rows("buildings", "building_part", cols + ", building_id")
for h, fl, mh, mf, name, shape, rh, fc, bid, g in plain + parts:
    top = height(h, fl, None)
    m = mh if mh is not None else (mf * 3.3 if mf else 0)
    extra = {}
    name = name or part_names.get(bid)
    if name: extra["n"] = name
    if addr.get(bid): extra["a"] = nice(addr[bid].strip())
    if bid in sec: extra["sc"] = sec[bid]
    if bid in part_names: extra["s"] = 1       # part of a named, modelled landmark: drawn in stone colour
    if fc and fc.startswith("#") and len(fc) == 7: extra["fc"] = fc
    for p in polys(g):
        ring = p[0]
        if len(ring) < 4:
            continue
        taper = TAPER.get(shape)
        if taper and rh and 0 < rh < top - m + 0.01:
            # body, then the roof as stacked shrinking slices (spires, domes)
            eaves = top - rh
            if eaves - m > 0.5:
                buildings.append(solid(ring, m, eaves, extra))
            steps = 10 if rh >= 20 else 5
            for i in range(steps):
                z0, z1 = i / steps, (i + 1) / steps
                k = taper((z0 + z1) / 2)
                if k > 0.03:
                    buildings.append(solid(shrink(ring, k), eaves + rh * z0, eaves + rh * z1, extra))
        else:
            if shape in ("gabled", "hipped", "skillion") and rh and rh < top - m:
                top -= rh / 2                    # flat stand-in at mid-roof height
            buildings.append(solid(ring, m, top, extra))

BO = (W, S)
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
parks = []
for (g,) in [r[1:] for r in rows("base", "land_use", "subtype",
                                  "subtype in ('park', 'recreation') or class in ('park', 'grass', 'garden')", True)]:
    parks += [{"r": [enc(p[0], BO)]} for p in polys(g) if p and len(p[0]) >= 4]

sea = []
for (g,) in [r[1:] for r in rows("base", "water", "subtype", "subtype = 'ocean' or class in ('ocean', 'sea', 'bay')", True)]:
    sea += [{"r": [enc(r, BO) for r in p]} for p in polys(g) if p and len(p[0]) >= 4]

WD = {"motorway": 8, "trunk": 7, "primary": 6, "secondary": 5, "tertiary": 4}
streets = []
for cls, g in rows("transportation", "segment", "class",
                   "subtype = 'road' and class in ('motorway','trunk','primary','secondary','tertiary','residential',"
                   "'pedestrian','living_street','unclassified')"):
    streets += [(WD.get(cls, 2), ln) for ln in lines(g) if len(ln) >= 2]

trees = [json.loads(g)["coordinates"] for (g,) in
         c.sql(f"select ST_AsGeoJSON(geometry) from read_parquet({SRC('base', 'land')}) where {BOX} "
               "and class = 'tree' and ST_GeometryType(geometry) = 'POINT'").fetchall()]


def pois(cls, named=False):
    q = (f"select ST_AsGeoJSON(ST_Centroid(geometry)), names.primary from read_parquet({SRC('base', 'infrastructure')}) "
         f"where {BOX} and class = '{cls}'")
    out = []
    for g, n in c.sql(q).fetchall():
        x, y = json.loads(g)["coordinates"]
        out.append([*enc([[x, y]], BO, closed=False)] + ([n or ""] if named else []))
    return out


json.dump({"o": BO, "signals": pois("traffic_signals"), "chargers": pois("charging_station", True),
           "parking": pois("parking", True), "water": pois("drinking_water")},
          open(os.path.join(OUT, "data", "pois.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

tiles = {}
for f in buildings:
    t = tile_of(*f["r"][0]); o = origin(t)
    f["r"] = [enc(f["r"], o)]
    if len(f["r"][0]) >= 6:
        tiles.setdefault(t, {"o": o, "b": [], "s": []})["b"].append(f)
for x, y in trees:
    t = tile_of(x, y)
    tiles.setdefault(t, {"o": origin(t), "b": [], "s": []}).setdefault("tr", []).extend(enc([[x, y]], origin(t), closed=False))
for w, ln in streets:
    t = tile_of(*ln[0]); o = origin(t)
    a = enc(ln, o, closed=False)
    if len(a) >= 4:
        tiles.setdefault(t, {"o": o, "b": [], "s": []})["s"].append([w] + a)
os.makedirs(os.path.join(OUT, "data", "t"), exist_ok=True)  # (data/ itself exists: pois.json)
index = []
for (i, j), d in sorted(tiles.items()):
    json.dump(d, open(os.path.join(OUT, "data", "t", f"{i}_{j}.json"), "w"), separators=(",", ":"))
    index.append([i, j, len(d["b"])])
json.dump({"o": BO, "tile": [W, S, TW, TH], "tiles": index, "count": len(buildings), "parks": parks, "sea": sea},
          open(os.path.join(OUT, "data", "base.json"), "w"), separators=(",", ":"))
page = open(os.path.join(HERE, "template.html")).read().replace(
    "/*MAPLIBRE_CSS*/", open(os.path.join(HERE, "maplibre-gl.css")).read()).replace("/*TMB_KEY*/", os.environ.get("TMB_KEY", ""))  # e.g. app_id=...&app_key=... (public, read-only)
open(os.path.join(OUT, "index.html"), "w").write(page)
print(len(tiles), "tiles,", len(buildings), "buildings,", len(parks), "parks,", len(streets), "streets,", len(sea), "sea ->", OUT)
