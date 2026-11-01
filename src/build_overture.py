"""Build the Barcelona 3D page from Overture Maps (OSM-derived) instead of Overpass.

Usage: python3 build_overture.py OUT_DIR   (needs: pip install duckdb)
Writes OUT_DIR/index.html (template + inlined MapLibre CSS), OUT_DIR/data/base.json (sea, parks)
and OUT_DIR/data/t/<i>_<j>.json tiles (buildings, streets) that the page loads for the area in view.
Coordinates are integers in 1e-5 degrees relative to the file's origin "o".
"""
import json, math, os, sys, duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
REL = os.environ.get("OVERTURE_RELEASE", "2026-10-21.0")
# Barcelona + surroundings by default; another city passes BBOX="S,W,N,E" (and TEMPLATE, WATER)
S, W, N, E = map(float, os.environ.get("BBOX", "41.30,2.03,41.48,2.30").split(","))
TEMPLATE = os.environ.get("TEMPLATE", os.path.join(HERE, "template.html"))
# which water polygons to draw: the sea for Barcelona; rivers, lakes and ponds inland (Madrid)
WATER = os.environ.get("WATER", "subtype = 'ocean' or class in ('ocean', 'sea', 'bay')")
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

# pitched roofs, as (across, along) scale of the footprint's oriented rectangle at height fraction z;
# "across" is the short side (the slope), "along" the ridge. w_l = short side / long side.
_steep = lambda z: 1 - 0.75 * min(1, z / 0.55) - 0.25 * max(0, (z - 0.55) / 0.45)   # gambrel / mansard profile
PITCH = {"gabled": lambda z, w_l: (1 - z, 1), "saltbox": lambda z, w_l: (1 - z, 1),
         "hipped": lambda z, w_l: (1 - z, 1 - z * w_l), "half_hipped": lambda z, w_l: (1 - z, 1 - 0.5 * z * w_l),
         "gambrel": lambda z, w_l: (_steep(z), 1),
         "mansard": lambda z, w_l: (_steep(z), 1 - (1 - _steep(z)) * w_l),
         "skillion": None}
# roof height when the data names a shape but not its height, as a share of the footprint's short side
ROOF_SHARE = {"dome": 0.5, "round": 0.5, "onion": 0.9, "pyramidal": 0.5, "cone": 1.2, "gabled": 0.3, "saltbox": 0.3,
              "hipped": 0.3, "half_hipped": 0.3, "gambrel": 0.35, "mansard": 0.3, "skillion": 0.15}
# hand fixes for landmarks the data leaves flat or without a height: LANDMARKS = path of a JSON list of
# {"n": name, "area": [min, max] m2 of the part (optional), "h": height, "roof": shape, "rh": roof height}
LANDMARKS = json.load(open(os.environ["LANDMARKS"], encoding="utf-8")) if os.environ.get("LANDMARKS") else []


def area_m2(ring):
    lat0 = ring[0][1]; kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    return abs(sum((x0 * kx) * (y1 * ky) - (x1 * kx) * (y0 * ky) for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))) / 2


def frame(ring):
    """Oriented minimum-area rectangle of a ring: centre, unit axes (across, along) and their half-lengths, in metres."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    lat0 = sum(y for _, y in pts) / len(pts)
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    P = [(x * kx, y * ky) for x, y in pts]
    best = None
    for i in range(len(P)):
        (x0, y0), (x1, y1) = P[i], P[(i + 1) % len(P)]
        d = math.hypot(x1 - x0, y1 - y0)
        if d < 0.5: continue
        ux, uy = (x1 - x0) / d, (y1 - y0) / d
        a = [px * ux + py * uy for px, py in P]; b = [-px * uy + py * ux for px, py in P]
        area = (max(a) - min(a)) * (max(b) - min(b))
        if best is None or area < best[0]:
            best = (area, ux, uy, min(a), max(a), min(b), max(b))
    if not best: return None
    _, ux, uy, a0, a1, b0, b1 = best
    ca, cb = (a0 + a1) / 2, (b0 + b1) / 2
    la, lb = (a1 - a0) / 2, (b1 - b0) / 2
    cx, cy = ca * ux - cb * uy, ca * uy + cb * ux
    long_ax, short_ax = ((ux, uy), (-uy, ux)) if la >= lb else ((-uy, ux), (ux, uy))
    return {"c": (cx, cy), "k": (kx, ky), "s": short_ax, "l": long_ax, "hs": min(la, lb), "hl": max(la, lb)}


def squeeze(ring, f, ks, kl, shift=0.0):
    """Scale a ring about its rectangle centre: ks across the short side, kl along the ridge; shift moves it across."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    (cx, cy), (kx, ky), (sx, sy), (lx, ly) = f["c"], f["k"], f["s"], f["l"]
    out = []
    for x, y in pts:
        px, py = x * kx - cx, y * ky - cy
        a, b = px * sx + py * sy, px * lx + py * ly
        a = a * ks + shift
        b *= kl
        out.append([(cx + a * sx + b * lx) / kx, (cy + a * sy + b * ly) / ky])
    return out


def shrink(ring, k):
    """Scale a ring about its vertex centroid (k=1 unchanged)."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    cx = sum(x for x, _ in pts) / len(pts); cy = sum(y for _, y in pts) / len(pts)
    return [[cx + (x - cx) * k, cy + (y - cy) * k] for x, y in pts]


def solid(ring, base, top, extra):
    f = {"h": round(top, 1), "r": ring, **extra}   # ring encoded later, relative to its tile
    if base > 0.05: f["m"] = round(base, 1)
    return f


def roofed(ring, m, top, shape, rh, extra):
    """A footprint as solids: the body, then its roof as stacked slices (domes, spires, pitched roofs)."""
    taper, pitch = TAPER.get(shape), PITCH.get(shape, False)
    if not taper and pitch is False:
        return [solid(ring, m, top, extra)]
    f = frame(ring)
    if not f or f["hs"] < 1:
        return [solid(ring, m, top, extra)]
    if not rh:   # shape without a height: guess it from the footprint, only where it reads well
        rh = min(ROOF_SHARE.get(shape, 0.3) * 2 * f["hs"], 40 if taper else 8)
    if rh < 0.8:
        return [solid(ring, m, top, extra)]
    eaves = top - rh if top - rh - m > 1.5 else top    # roof inside the height when the body can hold it, else on top
    out = [solid(ring, m, eaves, extra)] if eaves - m > 0.5 else []
    steps = 12 if rh >= 20 else 8 if rh >= 6 else 4
    w_l = f["hs"] / max(f["hl"], 0.1)
    for i in range(steps):
        z0, z1 = i / steps, (i + 1) / steps
        zm = (z0 + z1) / 2
        if taper:
            k = taper(zm)
            if k <= 0.03: continue
            q = shrink(ring, k)
        elif pitch is None:   # skillion: one slope, the high side kept
            ks = 1 - zm
            q = squeeze(ring, f, ks, 1, shift=f["hs"] * (1 - ks))
        else:
            ks, kl = pitch(zm, w_l)
            if ks <= 0.03 or kl <= 0.03: continue
            q = squeeze(ring, f, ks, kl)
        if (taper and k * f["hs"] < 0.4) or (not taper and f["hs"] * (1 - zm) < 0.4):
            continue   # thinner than the 1 m grid
        out.append(solid(q, eaves + rh * z0, eaves + rh * z1, extra))
    return out


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
# some buildings only have their upper parts modelled (Torre Mapfre: a 144-154 m crown and nothing below):
# fill the gap from the ground up to the lowest part with the building's own footprint
lowest = {}
for p in parts:
    mh, bid = p[2], p[8]
    lowest[bid] = min(lowest.get(bid, 1e9), mh or 0)
gaps = {bid: z for bid, z in lowest.items() if z > 3}
if gaps:
    for r in rows("buildings", "building", cols + ", id as building_id", "coalesce(has_parts, false)"):
        if r[8] in gaps:
            plain.append((gaps[r[8]], None, 0, None, *r[4:5], None, None, *r[7:]))
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
        t, sh, r = top, shape, rh
        for L in LANDMARKS:
            if L["n"] == name and ("area" not in L or L["area"][0] <= area_m2(ring) <= L["area"][1]):
                t, sh, r = L.get("h", t), L.get("roof", sh), L.get("rh", r)
                break
        buildings.extend(roofed(ring, m, t, sh, r, extra))

BO = (W, S)
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
parks = []
for (g,) in [r[1:] for r in rows("base", "land_use", "subtype",
                                  "subtype in ('park', 'recreation') or class in ('park', 'grass', 'garden')", True)]:
    parks += [{"r": [enc(p[0], BO)]} for p in polys(g) if p and len(p[0]) >= 4]

sea = []
for (g,) in [r[1:] for r in rows("base", "water", "subtype", WATER, True)]:
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
page = open(TEMPLATE).read().replace(
    "/*MAPLIBRE_CSS*/", open(os.path.join(HERE, "maplibre-gl.css")).read()).replace("/*TMB_KEY*/", os.environ.get("TMB_KEY", "")).replace("/*EMT_KEY*/", os.environ.get("EMT_KEY", ""))  # e.g. app_id=...&app_key=... (public, read-only)
open(os.path.join(OUT, "index.html"), "w").write(page)
print(len(tiles), "tiles,", len(buildings), "buildings,", len(parks), "parks,", len(streets), "streets,", len(sea), "sea ->", OUT)
