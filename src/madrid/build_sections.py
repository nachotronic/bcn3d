"""Census sections of the city of Madrid with income, demography (INE ADRH) and the July 2023 general election.

Usage: python3 build_sections.py RAW_DIR OUT_DIR
RAW_DIR holds:
  secciones.json  geoportal.madrid.es .../LIMITES_ADMINISTRATIVOS/Seccionado/TopoJSON/Secciones_Censales.json
  ine31097.csv    INE ADRH "Indicadores de renta media y mediana", Madrid province (www.ine.es/jaxiT3/files/t/es/csv_bdsc/31097.csv)
  ine31105.csv    INE ADRH "Indicadores demográficos", Madrid province (.../31105.csv)
  gen23.xlsx      datos.madrid.es 210278 "Elecciones Congreso de los Diputados. Julio 2023" (results by polling station)
Writes the same files as Barcelona's build_sections.py:
  OUT_DIR/data/sections.json   compact polygons + indicators for the page
  OUT_DIR/sections.geojson     full-precision polygons with "i" for build_overture.py (building -> section)
"""
import csv, json, os, sys
import openpyxl

RAW, OUT = sys.argv[1], sys.argv[2]
O = (-3.89, 40.31)

# --- polygons (TopoJSON, quantized) ---
tj = json.load(open(os.path.join(RAW, "secciones.json")))
sx, sy = tj["transform"]["scale"]; tx, ty = tj["transform"]["translate"]
arcs = []
for a in tj["arcs"]:
    x = y = 0; pts = []
    for dx, dy in a:
        x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)


def ring(ids):
    pts = []
    for i in ids:
        p = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts += p if not pts else p[1:]
    if pts and pts[0] != pts[-1]: pts.append(pts[0])
    return pts


geoms = tj["objects"]["Secciones_Censales"]["geometries"]


def polygons(g):
    return [[ring(r) for r in poly] for poly in (g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]])]


# --- INE ADRH: latest year per section and indicator ---
def ine(name, wanted):
    best = {}
    with open(os.path.join(RAW, name), encoding="utf-8-sig") as f:
        for r in csv.reader(f, delimiter=";"):
            if not r[0].startswith("28079 ") or "sección" not in r[2] or r[3] not in wanted or not r[5].strip():
                continue
            code, k = r[2].split()[0][5:], wanted[r[3]]
            try: v = float(r[5].replace(".", "").replace(",", "."))
            except ValueError: continue   # "." = no data
            if (code, k) not in best or r[4] > best[(code, k)][0]:
                best[(code, k)] = (r[4], v)
    out = {}
    for (code, k), (yr, v) in best.items():
        out.setdefault(code, {})[k] = v
    return out, max((y for y, _ in best.values()), default="")


renta, yr_r = ine("ine31097.csv", {"Renta neta media por persona": "renta", "Renta neta media por hogar": "rhog"})
demo, yr_d = ine("ine31105.csv", {"Edad media de la población": "edad", "Porcentaje de población de 65 y más años": "may65",
                                  "Porcentaje de población menor de 18 años": "men18", "Porcentaje de población española": "esp",
                                  "Porcentaje de hogares unipersonales": "unip", "Tamaño medio del hogar": "thog", "Población": "pob"})

# --- general election July 2023, summed from polling stations to sections ---
rows = list(openpyxl.load_workbook(os.path.join(RAW, "gen23.xlsx"), read_only=True).worksheets[0].iter_rows(values_only=True))
head = next(r for r in rows if r and "SUMAR" in r)
col = {name: i for i, name in enumerate(head) if name}
PARTIES = ["PSOE", "SUMAR", "PP", "VOX"]
votes = {}
for r in rows:
    if not isinstance(r[0], int) or not isinstance(r[2], int):
        continue
    code = f"{r[0]:02d}{r[2]:03d}"
    e = votes.setdefault(code, {"censo": 0, "emit": 0, "cand": 0, **{p: 0 for p in PARTIES}})
    cand = sum(x for x in r[col["FO"]:] if isinstance(x, (int, float)))
    e["censo"] += r[4] or 0; e["emit"] += r[6] or 0; e["cand"] += cand
    for p in PARTIES:
        e[p] += r[col[p]] or 0

out, geo = [], []
for i, g in enumerate(geoms):
    p = g["properties"]; c = p["COD_SECCIO"]
    rn, dm, vt = renta.get(c, {}), demo.get(c, {}), votes.get(c)
    v = {"renta": rn.get("renta"), "rhog": rn.get("rhog"), "edad": dm.get("edad"), "may65": dm.get("may65"), "men18": dm.get("men18"),
         "extr": round(100 - dm["esp"], 1) if "esp" in dm else None, "unip": dm.get("unip"), "thog": dm.get("thog"), "pob": dm.get("pob")}
    win = ""
    if vt and vt["emit"]:
        valid = max(1, vt["cand"])
        v["part"] = round(vt["emit"] / max(1, vt["censo"]) * 100, 1)
        for k in PARTIES:
            v["v_" + k] = round(vt[k] / valid * 100, 1)
        win = max(PARTIES, key=lambda k: vt[k])
    v = {k: x for k, x in v.items() if x is not None}
    polys = polygons(g)
    rings = []
    for poly in polys:
        a, last = [], None
        for x, y in poly[0][:-1]:
            q = (round((x - O[0]) * 1e5), round((y - O[1]) * 1e5))
            if q != last: a += q; last = q
        if len(a) >= 6: rings.append(a)
    out.append({"c": "28079" + c, "m": p["NOM_DIS"], "b": p["NOM_BAR"], "d": p["NOM_DIS"], "g": win, "v": v, "r": rings})
    geo.append({"type": "Feature", "properties": {"i": i}, "geometry": {"type": "MultiPolygon", "coordinates": polys}})

os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "src": {"renta": yr_r, "demo": yr_d}, "s": out},
          open(os.path.join(OUT, "data", "sections.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
json.dump({"type": "FeatureCollection", "features": geo}, open(os.path.join(OUT, "sections.geojson"), "w"))
print(len(out), "sections;", len(renta), "with income", yr_r, ";", len(demo), "with demography", yr_d, ";", len(votes), "with 2023 vote")
