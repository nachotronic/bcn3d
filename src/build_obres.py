"""Road works in public space under way (Open Data BCN "obres", updated daily), as a snapshot for the map.

Usage: python3 build_obres.py obres_espai_public.json OUT_DIR  -> OUT_DIR/data/obres.json
The portal refuses cloud servers, so download the JSON in a browser and pass it here; the page then
reads the current file from each visitor's browser and falls back to this snapshot.
Output: {"o":[lon,lat], "t":"YYYY-MM-DD", "s":[[{props}, [[x, y, x, y, ...], ...]], ...]}  rings in 1e-5 degrees.
"""
import json, os, sys
import duckdb

SRC, OUT = sys.argv[1], sys.argv[2]
O = (2.03, 41.30)
KEEP = ("codi", "titol", "tipusobra", "ubicacio", "data_inici", "data_fi", "estat", "promotor", "url_web_obres")
rows = [r for r in json.load(open(SRC, encoding="utf-8")) if r.get("estat") != "Finalitzada" and r.get("geometria_etrs89")]
c = duckdb.connect(); c.execute("INSTALL spatial; LOAD spatial")
out = []
for r in rows:
    gj = c.execute("select ST_AsGeoJSON(ST_Transform(ST_GeomFromText(?), 'EPSG:25831', 'EPSG:4326', always_xy := true))", [r["geometria_etrs89"]]).fetchone()[0]
    g = json.loads(gj)
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]] if g["type"] == "Polygon" else []
    rings = []
    for poly in polys:
        for ring in poly[:1]:  # outer rings only
            pts = []
            for x, y in ring:
                pts += [round((x - O[0]) * 1e5), round((y - O[1]) * 1e5)]
            rings.append(pts)
    if rings:
        p = {k: (r.get(k) or "").strip() if isinstance(r.get(k), str) else r.get(k) for k in KEEP}
        for k in ("data_inici", "data_fi"):
            p[k] = (p[k] or "")[:10]
        out.append([p, rings])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
stamp = max((p["data_inici"] for p, _ in out), default="")
json.dump({"o": O, "t": stamp, "s": out}, open(os.path.join(OUT, "data", "obres.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(out), "works under way")
