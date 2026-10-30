"""Census sections (INE 2023) of the map area with socioeconomic and electoral indicators.

Usage: python3 build_sections.py ABST_REPO OUT_DIR
ABST_REPO is a checkout of nachotronic/abstencio-catalunya (mapaelectoral.es), whose data/ folder has the
per-section tables (INE, SERPAVI, Ministerio del Interior). Writes:
  OUT_DIR/data/sections.json   compact polygons + indicators for the page
  OUT_DIR/sections.geojson     full-precision polygons with "i" (index into sections.json) for build_overture.py
"""
import csv, gzip, json, os, sys

ABST, OUT = sys.argv[1], sys.argv[2]
W, S, E, N = 2.03, 41.30, 2.30, 41.48
O = (W, S)
D = os.path.join(ABST, "data")


def rd(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def num(v, k=1, nd=1):
    try:
        return round(float(v) * k, nd)
    except (TypeError, ValueError):
        return None


def bbox_hit(geom):
    xs, ys = [], []
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for p in polys:
        for x, y in p[0]:
            xs.append(x); ys.append(y)
    return min(xs) < E and max(xs) > W and min(ys) < N and max(ys) > S


gj = json.load(open(os.path.join(D, "catalunya_secciones_2023.geojson")))
feats = [f for f in gj["features"] if bbox_hit(f["geometry"])]
codes = [f["properties"]["tract_code"] for f in feats]
want = set(codes)

barrio = {r["tract_code"]: (r["barrio"], r["distrito"]) for r in rd(os.path.join(D, "barrios", "secciones_barrio.csv"))
          if r["tract_code"] in want}
gen = {r["tract_code"]: r for r in rd(os.path.join(ABST, "generales-2026", "descargas", "secciones.csv")) if r["tract_code"] in want}
rent = {}
for r in rd(os.path.join(D, "censo", "alquiler_secciones.csv.gz")):
    if r["seccion"] in want and r["alq_m2_pisos"] and (r["seccion"] not in rent or r["anyo"] > rent[r["seccion"]]["anyo"]):
        rent[r["seccion"]] = r
tour = {}
for r in rd(os.path.join(D, "censo", "viviendas_turisticas_secciones.csv.gz")):
    if r["seccion"] in want and (r["seccion"] not in tour or r["periodo"] > tour[r["seccion"]]["periodo"]):
        tour[r["seccion"]] = r

PARTIES = ["PSOE", "SUMAR", "PP", "VOX", "ERC", "JUNTS"]
out, geo = [], []
for i, f in enumerate(feats):
    p, c = f["properties"], f["properties"]["tract_code"]
    g, b, rn, tu = gen.get(c, {}), barrio.get(c, ("", "")), rent.get(c, {}), tour.get(c, {})
    v = {
        "renta": num(p.get("net_income_pc"), 1, 0), "edad": num(p.get("mean_age")), "may65": num(p.get("pct_over65")),
        "extr": num(p.get("pct_foreign"), 100), "nacfuera": num(p.get("pct_foreign_born"), 100),
        "estsup": num(p.get("pct_higher_ed_completed"), 100), "paro": num(p.get("unemployment_rate"), 100),
        "alquilados": num(p.get("pct_rented"), 100), "alqm2": num(rn.get("alq_m2_pisos")), "alqmes": num(rn.get("alq_mes_pisos"), 1, 0),
        "turist": num(tu.get("pct_viviendas"), 1, 2), "part": num(g.get("2023_07_part") or p.get("t2023_07"), 100),
        "pob": num(p.get("population"), 1, 0),
    }
    for k in PARTIES:
        v["v_" + k] = num(g.get("2023_07_" + k), 100)
    v = {k: x for k, x in v.items() if x is not None}
    polys = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
    rings = []
    for poly in polys:
        for ring in poly[:1]:
            a, last = [], None
            for x, y in ring[:-1]:
                q = (round((x - O[0]) * 1e5), round((y - O[1]) * 1e5))
                if q != last: a += q; last = q
            if len(a) >= 6: rings.append(a)
    out.append({"c": c, "m": p.get("mun_name", ""), "b": b[0], "d": b[1], "g": g.get("2023_07_gana", ""), "v": v, "r": rings})
    geo.append({"type": "Feature", "properties": {"i": i}, "geometry": f["geometry"]})

os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "src": {"rent": max((r["anyo"] for r in rent.values()), default=""),
                           "tour": max((r["periodo"] for r in tour.values()), default="")}, "s": out},
          open(os.path.join(OUT, "data", "sections.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
json.dump({"type": "FeatureCollection", "features": geo}, open(os.path.join(OUT, "sections.geojson"), "w"))
print(len(out), "sections;", sum(1 for s in out if s["b"]), "with barrio;", len(rent), "with rent;", len(tour), "with tourist flats")
