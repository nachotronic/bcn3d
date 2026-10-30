"""Strategic noise map of Barcelona (2017) by street section, from Open Data BCN tramer-mapa-estrategic-soroll.

Usage: python3 build_noise.py 2017_tramer_mapa_estrategic_soroll_bcn.csv OUT_DIR  -> OUT_DIR/data/noise.json
The portal refuses cloud servers, so download the CSV in a browser and pass it here.
Output: {"o":[lon,lat], "src":[...], "s":[[day, evening, night, day_source, night_source, x, y, x, y, ...], ...]}
Levels are bands: 0 = <40 dB(A), 1 = 40-45, ... 8 = 75-80, 9 = >80. Sources index "src".
"""
import json, os, re, sys
import duckdb

SRC, OUT = sys.argv[1], sys.argv[2]
O = (2.03, 41.30)
SOURCES = ["TRANSIT", "GI_TR", "FFCC", "INDUST", "VIANANTS", "OCI", "PATIS"]  # traffic, main roads, rail, industry, pedestrians, nightlife, school yards


def band(v):
    if not v: return 0
    if v.startswith("<"): return 0
    if v.startswith(">"): return 9
    m = re.match(r"(\d+)", v)
    return max(0, min(9, (int(m.group(1)) - 35) // 5)) if m else 0


def loudest(row, period):
    best = max(((band(row.get(f"{s}_{period}")), i) for i, s in enumerate(SOURCES) if row.get(f"{s}_{period}")), default=(0, 0))
    return best[1] if best[0] > 0 else -1


c = duckdb.connect(); c.execute("INSTALL spatial; LOAD spatial")
rel = c.sql(f"""
  select *, ST_AsGeoJSON(ST_Transform(ST_GeomFromText(GEOM_WKT), 'EPSG:25831', 'EPSG:4326', always_xy := true)) gj
  from read_csv('{SRC}', all_varchar = true, max_line_size = 100000000)""")
cols = rel.columns
out = []
for r in rel.fetchall():
    row = dict(zip(cols, r))
    g = json.loads(row["gj"])
    lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
    head = [band(row["TOTAL_D"]), band(row["TOTAL_E"]), band(row["TOTAL_N"]), loudest(row, "D"), loudest(row, "N")]
    for ln in lines:
        pts, last = [], None
        for x, y in ln:
            q = (round((x - O[0]) * 1e5), round((y - O[1]) * 1e5))
            if q != last: pts += q; last = q
        if len(pts) >= 4: out.append(head + pts)
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "src": SOURCES, "s": out}, open(os.path.join(OUT, "data", "noise.json"), "w"), separators=(",", ":"))
print(len(out), "street pieces")
