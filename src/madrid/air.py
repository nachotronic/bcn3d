"""Latest hourly air quality per Madrid monitoring station (Ayuntamiento de Madrid open data, no key).

Usage: python3 air.py OUT_DIR  -> OUT_DIR/data/air.json
Output: {"t": "YYYY-MM-DD HH:00", "o":[lon,lat], "s": [[x, y, "station", {"NO2": v, ...}, level, code], ...]}
level 0..3 = good / fair / moderate / poor (European AQI bands, worst pollutant), as in Barcelona.
The page also reads the same real-time CSV live (it answers browsers on nachotronic.github.io) and keeps this file
as the fallback and as the station list (names and positions).
"""
import csv, io, json, os, sys, urllib.request

OUT = sys.argv[1]
O = (-3.95, 40.28)
STATIONS = "https://datos.madrid.es/egob/catalogo/212629-1-estaciones-control-aire.csv"
LIVE = "https://ciudadesabiertas.madrid.es/dynamicAPI/API/query/calair_tiemporeal.csv?pageSize=5000"
MAG = {"8": "NO2", "10": "PM10", "9": "PM2.5", "14": "O3"}
BANDS = {"NO2": (40, 90, 120), "PM10": (20, 40, 50), "PM2.5": (10, 20, 25), "O3": (50, 100, 130)}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "madrid3d-map/1.0"})
    raw = urllib.request.urlopen(req, timeout=60).read()
    for enc in ("utf-8-sig", "latin-1"):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass


st = {}
for r in csv.DictReader(io.StringIO(get(STATIONS)), delimiter=";"):
    r = {k.strip().lstrip("﻿").lstrip("ï»¿"): v for k, v in r.items() if k}
    st[str(int(r["CODIGO_CORTO"]))] = {"n": r["ESTACION"].strip(), "x": float(r["LONGITUD"].replace(",", ".")),
                                      "y": float(r["LATITUD"].replace(",", ".")), "v": {}}
stamp = ""
for r in csv.DictReader(io.StringIO(get(LIVE)), delimiter=";"):
    s, m = st.get(str(int(r["ESTACION"]))), MAG.get(str(int(r["MAGNITUD"])))
    if not s or not m: continue
    hours = [h for h in range(1, 25) if r.get(f"V{h:02d}") == "V"]
    if not hours: continue
    h = hours[-1]
    s["v"][m] = round(float(r[f"H{h:02d}"]))
    stamp = max(stamp, f"{r['ANO']}-{int(r['MES']):02d}-{int(r['DIA']):02d} {h - 1:02d}:00")

out = []
for code, s in st.items():
    level = max((sum(v >= b for b in BANDS[k]) for k, v in s["v"].items()), default=0)
    out.append([round((s["x"] - O[0]) * 1e5), round((s["y"] - O[1]) * 1e5), s["n"], s["v"], level, code])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"t": stamp, "o": O, "s": out}, open(os.path.join(OUT, "data", "air.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "stations, latest", stamp)
