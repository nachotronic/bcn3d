"""Road pieces for the live traffic layer: each Informo measuring point snapped to its nearest Overture road segment.

Usage: OVERTURE_STAGE=dir python3 build_tramos.py OUT_DIR   (needs duckdb; reads informo.madrid.es/informo/tmadrid/pm.xml)
Output: OUT_DIR/data/tramos.json {"o":[lon,lat], "t": {"idelem": ["description", [flat 1e5 coords]]}}
The page then reads pm.xml live (CORS *) every 5 minutes and colours each piece by its service level.
The piece is the stretch of the segment within ~120 m of the sensor, so long avenues are not painted end to end.
"""
import json, os, sys, urllib.request, xml.etree.ElementTree as ET
import duckdb

OUT, STAGE = sys.argv[1], os.environ["OVERTURE_STAGE"]
O = (-3.95, 40.28)
req = urllib.request.Request("https://informo.madrid.es/informo/tmadrid/pm.xml", headers={"User-Agent": "madrid3d-map/1.0"})
root = ET.fromstring(urllib.request.urlopen(req, timeout=120).read())
pms = []
for pm in root.iter("pm"):
    g = {c.tag: (c.text or "").strip() for c in pm}
    if g.get("st_x") and g.get("st_y"):
        pms.append((g["idelem"], g.get("descripcion", ""), float(g["st_x"].replace(",", ".")), float(g["st_y"].replace(",", "."))))

c = duckdb.connect(); c.execute("LOAD spatial")
c.execute("create table pm (id varchar, d varchar, x double, y double)")
c.executemany("insert into pm values (?, ?, ?, ?)", pms)
# sensors are in ETRS89 / UTM 30N; work in metres there
c.execute("create table p as select id, d, ST_Point(x, y) g from pm")
c.execute(f"""create table r as select id, class, ST_Transform(geometry, 'OGC:CRS84', 'EPSG:25830', always_xy := true) g
  from '{STAGE}/segment.parquet' where class in ('motorway','trunk','primary','secondary','tertiary','residential','unclassified','living_street')""")
c.execute("create index ri on r using rtree (g)")
rows = c.sql("""
  with near as (
    select p.id, p.d, p.g pg, r.g rg, ST_Distance(p.g, r.g) dist,
      row_number() over (partition by p.id order by ST_Distance(p.g, r.g)) k
    from p join r on ST_DWithin(p.g, r.g, 60))
  select id, d, ST_AsGeoJSON(ST_Transform(
      ST_LineSubstring(rg, greatest(0, f - 120 / len), least(1, f + 120 / len)), 'EPSG:25830', 'OGC:CRS84', always_xy := true))
  from (select *, ST_LineLocatePoint(rg, pg) f, greatest(ST_Length(rg), 1) len from near where k = 1)""").fetchall()
t = {}
for i, d, g in rows:
    co = json.loads(g)["coordinates"]
    a = []
    for x, y in co:
        a += [round((x - O[0]) * 1e5), round((y - O[1]) * 1e5)]
    if len(a) >= 4: t[i] = [d, a]
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "t": t}, open(os.path.join(OUT, "data", "tramos.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(pms), "sensors,", len(t), "snapped to a road")
