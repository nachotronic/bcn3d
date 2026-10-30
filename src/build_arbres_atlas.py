"""Every municipal tree (street, park and zone) from the Biodiversity Atlas, with species, cut into the building tile grid.

Usage: python3 build_arbres_atlas.py OUT_DIR ab_vw_arbrat_geometries.csv ab_vw_arbrat_geom_especie.csv ab_vw_arbrat_especies.csv [OD_Arbrat_Zona_BCN.csv]
  -> OUT_DIR/data/arb/i_j.json  {"s":[x, y, species, year, place, name, x, y, ...]}  (flat, 6 per tree, 1e-5 degrees from "o")
     OUT_DIR/data/arbsp.json    {"o":[lon,lat], "t":["i_j", ...], "sp":[["català","castellano","English","scientific"], ...], "pl":[...], "nm":[...]}
     OUT_DIR/data/arbdesc.json  [["descripció","descripción","description"], ...]  (by species index, read when a tree is tapped)
The optional zone inventory adds planting year and park name to trees within ~6 m of one of its points.
"""
import csv, json, os, re, sys

OUT, GEOM, REL, SPEC = sys.argv[1:5]
ZONA = sys.argv[5] if len(sys.argv) > 5 else None
O = (2.03, 41.30)
W, S0, TW, TH = 2.03, 41.30, 0.02, 0.015  # same grid as the building tiles


def rows(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


tidy = lambda s: re.sub(r"\s+", " ", (s or "").split(",")[0]).strip()  # "Trémol,  trèmol" -> "Trémol"
spec = {r["especie_id"]: r for r in rows(SPEC)}
rel = {r["geom_fid"]: r["especie_id"] for r in rows(REL)}

year = {}
if ZONA:
    for r in rows(ZONA):
        try:
            zx, zy = float(r["longitud"]), float(r["latitud"])
        except (KeyError, ValueError):
            continue
        y = (r.get("data_plantacio") or "")[:4]
        year.setdefault((round(zx * 1e4), round(zy * 1e4)), []).append((zx, zy, int(y) if y.isdigit() else 0, (r.get("espai_verd") or r.get("adreca") or "").strip()))

sp, spi, desc, pl, pli, nm, nmi, tiles, n = [], {}, [], [""], {"": 0}, [""], {"": 0}, {}, 0
idx = lambda table, index, v: index.setdefault(v, len(table)) if v in index or not table.append(v) else index[v]
for r in rows(GEOM):
    m = re.match(r"POINT \(([-\d.]+) ([-\d.]+)\)", r["geom_wgs84"] or "")
    if not m: continue
    x, y = float(m.group(1)), float(m.group(2))
    s = spec.get(rel.get(r["geom_fid"]))
    if not s: continue
    if s["especie_id"] not in spi:
        spi[s["especie_id"]] = len(sp)
        sp.append([tidy(s["nom_cat"]), tidy(s["nom_cas"]), tidy(s["nom_eng"]), s["nom_ctf"].strip()])
        desc.append([s["desc_cat"].strip(), s["desc_cas"].strip(), s["desc_eng"].strip()])
    yr, place, best = 0, "", 6e-5 ** 2  # nearest zone record within ~6 m
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for zx, zy, zyr, zpl in year.get((round(x * 1e4) + dx, round(y * 1e4) + dy), ()):
                dd = ((zx - x) * 0.75) ** 2 + (zy - y) ** 2
                if dd < best: best, yr, place = dd, zyr, zpl
    name = (r["nom_cat"] or "").strip()
    i, j = int((x - W) // TW), int((y - S0) // TH)
    tiles.setdefault(f"{i}_{j}", []).extend([round((x - O[0]) * 1e5), round((y - O[1]) * 1e5), spi[s["especie_id"]], yr,
                                             idx(pl, pli, place), idx(nm, nmi, name)])
    n += 1
d = os.path.join(OUT, "data", "arb"); os.makedirs(d, exist_ok=True)
for k, v in tiles.items():
    json.dump({"s": v}, open(os.path.join(d, k + ".json"), "w"), separators=(",", ":"))
json.dump({"o": O, "t": sorted(tiles), "sp": sp, "pl": pl, "nm": nm}, open(os.path.join(OUT, "data", "arbsp.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
json.dump(desc, open(os.path.join(OUT, "data", "arbdesc.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(n, "trees,", len(sp), "species,", len(tiles), "tiles,", sum(1 for k in year), "zone records")
