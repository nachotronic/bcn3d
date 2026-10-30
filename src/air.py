"""Latest hourly air quality per monitoring station (Generalitat XVPCA open data, no key).

Usage: python3 air.py OUT_DIR  -> OUT_DIR/data/air.json
Output: {"t": "YYYY-MM-DD HH:00", "o":[lon,lat], "s": [[x, y, "station", {"NO2": v, "PM10": v, ...}, level], ...]}
level 0..3 = good / fair / moderate / poor (European AQI bands, worst pollutant).
"""
import json, os, sys, urllib.parse, urllib.request

OUT = sys.argv[1]
O = (2.03, 41.30)
W, S, E, N = 2.03, 41.30, 2.30, 41.48
API = "https://analisi.transparenciacatalunya.cat/resource/tasf-thgu.json"
BANDS = {"NO2": (40, 90, 120), "PM10": (20, 40, 50), "PM2.5": (10, 20, 25), "O3": (50, 100, 130)}

q = {"$where": f"latitud > {S} and latitud < {N} and longitud > {W} and longitud < {E} "
               f"and contaminant in ('NO2','PM10','PM2.5','O3')",
     "$order": "data DESC", "$limit": "400"}
req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "bcn3d-map/1.0"})
rows = json.load(urllib.request.urlopen(req, timeout=60))

stations, stamp = {}, ""
for r in rows:  # newest day first; keep each station's newest day and its last filled hour
    hours = [(h, r.get(f"h{h:02d}")) for h in range(1, 25)]
    hours = [(h, float(v)) for h, v in hours if v not in (None, "")]
    if not hours: continue
    key = r["codi_eoi"]
    st = stations.setdefault(key, {"n": r["nom_estacio"], "x": float(r["longitud"]), "y": float(r["latitud"]),
                                   "day": r["data"][:10], "v": {}})
    if r["data"][:10] != st["day"] or r["contaminant"] in st["v"]: continue
    h, v = hours[-1]
    st["v"][r["contaminant"]] = round(v)
    stamp = max(stamp, f"{st['day']} {h - 1:02d}:00")

out = []
for st in stations.values():
    level = max((sum(v >= b for b in BANDS[k]) for k, v in st["v"].items()), default=0)
    out.append([round((st["x"] - O[0]) * 1e5), round((st["y"] - O[1]) * 1e5), st["n"], st["v"], level])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"t": stamp, "o": O, "s": out}, open(os.path.join(OUT, "data", "air.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "stations, latest", stamp)
