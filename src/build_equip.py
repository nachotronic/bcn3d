"""Public facilities (health, education, culture, sport, markets, administration) from Overture places.

Usage: OVERTURE_STAGE=dir python3 build_equip.py OUT_DIR  -> OUT_DIR/data/equip.json
dir holds the bbox-staged Overture parquet files (place.parquet), as for build_overture.py.
Output: {"o":[lon,lat], "g":["salud", ...], "s":[[x, y, group, "name", "address", "category"], ...]}
"""
import json, os, sys
import duckdb

OUT, STAGE = sys.argv[1], os.environ["OVERTURE_STAGE"]
O = (2.03, 41.30)
GROUPS = {
    "salud": ["hospital", "outpatient_care_facility", "pharmacy_and_drug_store"],
    "educacion": ["preschool", "elementary_school", "high_school", "college_university", "education"],
    "cultura": ["library", "museum", "theatre_venue", "movie_theater", "cultural_center", "art_gallery", "music_venue"],
    "deporte": ["sport_or_fitness_facility", "stadium_arena", "sports_and_recreation"],
    "mercados": [],  # by name below: municipal markets have no category of their own
    "admin": ["government_office", "community_center"],
}
cat = {c: g for g, cs in GROUPS.items() for c in cs}
gi = {g: i for i, g in enumerate(GROUPS)}

c = duckdb.connect(); c.execute('INSTALL spatial; LOAD spatial')
rows = c.sql(f"""
  select ST_X(geometry) x, ST_Y(geometry) y, names.primary n, basic_category k, addresses[1].freeform a
  from '{STAGE}/place.parquet'
  where confidence > 0.6 and names.primary is not null
    and (basic_category in ({','.join(f"'{k}'" for k in cat)})
         or regexp_matches(names.primary, '^(Mercat|Mercado) (de |del |d.|dels )?[A-ZÀ-Ú]'))
""").fetchall()

out, seen = [], set()
for x, y, n, k, a in rows:
    g = "mercados" if n.startswith(("Mercat ", "Mercado ")) else cat.get(k)
    key = (n.lower(), round(x, 4), round(y, 4))
    if not g or key in seen: continue
    seen.add(key)
    out.append([round((x - O[0]) * 1e5), round((y - O[1]) * 1e5), gi[g], n.strip(), (a or "").strip(), k or ""])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "g": list(GROUPS), "s": out}, open(os.path.join(OUT, "data", "equip.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "facilities:", {g: sum(1 for r in out if r[2] == i) for g, i in gi.items()})
