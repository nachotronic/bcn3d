"""Snapshot Bicing availability (public GBFS feed) into data/bicing.json.

Usage: python3 bicing.py OUT_DIR
Output: {"t": unix_time, "o":[lon,lat], "s": [[x, y, bikes, ebikes, docks, capacity, "name"], ...]}
"""
import json, os, sys, urllib.request

OUT = sys.argv[1]
O = (2.12, 41.36)
BASE = "https://barcelona.publicbikesystem.net/customer/gbfs/v2/en/"
EBIKES = {"BOOST", "EFIT"}


def get(name):
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "bcn3d-map/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))


info = {s["station_id"]: s for s in get("station_information")["data"]["stations"]}
status = get("station_status")
out = []
for s in status["data"]["stations"]:
    i = info.get(s["station_id"])
    if not i or not s.get("is_installed") or s.get("status") != "IN_SERVICE":
        continue
    types = {v["vehicle_type_id"]: v["count"] for v in s.get("vehicle_types_available", [])}
    eb = sum(c for k, c in types.items() if k in EBIKES)
    out.append([round((i["lon"] - O[0]) * 1e5), round((i["lat"] - O[1]) * 1e5),
                s["num_bikes_available"], eb, s["num_docks_available"], i.get("capacity", 0), i["name"].strip().title()])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"t": status["last_updated"], "o": O, "s": out},
          open(os.path.join(OUT, "data", "bicing.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(out), "stations")
