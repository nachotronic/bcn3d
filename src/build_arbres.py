"""Municipal tree inventory (Open Data BCN arbrat-zona / arbrat-viari CSV) with species and planting date.

Usage: python3 build_arbres.py OUT_DIR OD_Arbrat_Zona_BCN.csv [OD_Arbrat_Viari_BCN.csv ...]  -> OUT_DIR/data/arbres.json
The portal refuses cloud servers, so download the CSVs in a browser and pass them here.
Output: {"o":[lon,lat], "sp":[["castellano","català","scientific"], ...], "pl":["place", ...], "s":[[x, y, species, year, place], ...]}
"""
import csv, json, os, sys

OUT, SRCS = sys.argv[1], sys.argv[2:]
O = (2.03, 41.30)
sp, spi, pl, pli, out = [], {}, [], {}, []
for src in SRCS:
    with open(src, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                x, y = float(r["longitud"]), float(r["latitud"])
            except (KeyError, ValueError):
                continue
            key = (r.get("cat_nom_castella", "").strip(), r.get("cat_nom_catala", "").strip(), r.get("cat_nom_cientific", "").strip())
            if key not in spi:
                spi[key] = len(sp); sp.append(list(key))
            year = (r.get("data_plantacio") or "")[:4]
            place = (r.get("espai_verd") or r.get("adreca") or "").strip()
            if place not in pli:
                pli[place] = len(pl); pl.append(place)
            out.append([round((x - O[0]) * 1e5), round((y - O[1]) * 1e5), spi[key], int(year) if year.isdigit() else 0, pli[place]])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "sp": sp, "pl": pl, "s": out}, open(os.path.join(OUT, "data", "arbres.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(out), "trees,", len(sp), "species")
