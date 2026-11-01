"""Every municipal tree in Madrid (streets and parks, ~800k) with species, height and girth, cut into the building tile grid.

Usage: python3 build_arboles.py OUT_DIR arbolado.csv especies.xlsx parques.xlsx
  arbolado.csv  = datos.madrid.es 300761 "Arbolado ... (detalle)" CSV (X, Y in ETRS89 / UTM 30N)
  especies.xlsx = its species list (300761-2), parques.xlsx = its park list (300761-4)
-> OUT_DIR/data/arb/i_j.json  {"s":[x, y, species, height_m, park, girth_cm, ...]}  (flat, 6 per tree, 1e-5 degrees from "o")
   OUT_DIR/data/arbsp.json    {"o":[lon,lat], "t":["i_j", ...], "sp":[["català","castellano","English","scientific"], ...], "pl":[parks], "nm":[""]}
Same shape as Barcelona's build_arbres_atlas.py, so the page reads both alike (the 4th and 6th slots mean height and girth here).
"""
import csv, json, math, os, sys
import openpyxl

OUT, ARB, ESP, PAR = sys.argv[1:5]
W, S0, TW, TH = -3.89, 40.31, 0.02, 0.015   # same grid as the building tiles (BBOX in build_overture.py)
O = (W, S0)


def utm30(E, N):  # ETRS89 / UTM 30N -> lon, lat
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f); ep2 = e2 / (1 - e2); e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    mu = N / k0 / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    p = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu) \
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    sn, cs = math.sin(p), math.cos(p); T = math.tan(p) ** 2; C = ep2 * cs * cs
    Nn = a / math.sqrt(1 - e2 * sn * sn); R = a * (1 - e2) / (1 - e2 * sn * sn) ** 1.5; D = (E - 500000) / (Nn * k0)
    lat = p - (Nn * math.tan(p) / R) * (D * D / 2 - (5 + 3 * T + 10 * C - 4 * C * C - 9 * ep2) * D ** 4 / 24
                                        + (61 + 90 * T + 298 * C + 45 * T * T - 252 * ep2 - 3 * C * C) * D ** 6 / 720)
    lon = (D - (1 + 2 * T + C) * D ** 3 / 6 + (5 - 2 * C + 28 * T - 3 * C * C + 8 * ep2 + 24 * T * T) * D ** 5 / 120) / cs
    return -3 + math.degrees(lon), math.degrees(lat)


def sheet(path):
    return list(openpyxl.load_workbook(path, read_only=True).worksheets[0].iter_rows(values_only=True))[1:]


names = {r[0]: (r[1] or "", r[2] or "") for r in sheet(ESP) if r[0]}
parks = {str(r[0]): " ".join((r[1] or "").title().split()) for r in sheet(PAR) if r[0]}
num = lambda v: float((v or "0").replace(",", ".") or 0)
sp, spi, pl, pli, tiles, n = [], {}, [""], {"": 0}, {}, 0
with open(ARB, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f, delimiter=";"):
        try:
            x, y = utm30(num(r["X"]), num(r["Y"]))
        except ValueError:
            continue
        code = r["CODIGO_ESPECIE"].strip()
        if code not in spi:
            common, sci = names.get(code, ("", ""))
            sci = sci or (r["ESPECIE"] or "").capitalize()
            common = common or sci
            spi[code] = len(sp); sp.append([common, common, common, sci])
        park = parks.get((r["NUM_PARQUE"] or "").strip().lstrip("0"), "")
        if park not in pli: pli[park] = len(pl); pl.append(park)
        i, j = int((x - W) // TW), int((y - S0) // TH)
        tiles.setdefault(f"{i}_{j}", []).extend([round((x - O[0]) * 1e5), round((y - O[1]) * 1e5), spi[code],
                                                 round(num(r["ALTURA_TOTAL"])), pli[park], round(num(r["PERIMETRO"]))])
        n += 1
d = os.path.join(OUT, "data", "arb"); os.makedirs(d, exist_ok=True)
for k, v in tiles.items():
    json.dump({"s": v}, open(os.path.join(d, k + ".json"), "w"), separators=(",", ":"))
json.dump({"o": O, "t": sorted(tiles), "sp": sp, "pl": pl, "nm": [""]},
          open(os.path.join(OUT, "data", "arbsp.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(n, "trees,", len(sp), "species,", len(pl) - 1, "parks,", len(tiles), "tiles")
