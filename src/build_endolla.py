"""Endolla Barcelona public EV chargers (Open Data BCN, GELFS JSON) with a status snapshot.

Usage: python3 build_endolla.py OUT_DIR endolla_locations.json [endolla_status.json]  -> OUT_DIR/data/endolla.json
The portal refuses cloud servers, so download the files in a browser and pass them here;
the page then reads the live status file from each visitor's browser.
Output: {"o":[lon,lat], "s":[[x, y, "location id", "address", "notes", [[station, port, "connector", kW, status], ...]], ...]}
status: 0 unknown, 1 available, 2 in use, 3 reserved, 4 out of order / unavailable.
"""
import json, os, sys

OUT, LOCS = sys.argv[1], sys.argv[2]
O = (2.03, 41.30)
ST = {"AVAILABLE": 1, "IN_USE": 2, "RESERVED": 3, "OUT_OF_ORDER": 4, "UNAVAILABLE": 4}

status = {}
if len(sys.argv) > 3:
    for loc in json.load(open(sys.argv[3], encoding="utf-8"))["locations"]:
        for s in loc.get("stations", []):
            for p in s.get("ports", []):
                status[(s["id"], p["id"])] = ST.get(((p.get("port_status") or [{}])[0]).get("status"), 0)

out = []
for loc in json.load(open(LOCS, encoding="utf-8"))["locations"]:
    c = loc["coordinates"]
    ports = [[s["id"], p["id"], p.get("connector_type", ""), p.get("power_kw") or 0, status.get((s["id"], p["id"]), 0)]
             for s in loc.get("stations", []) for p in s.get("ports", [])]
    notes = next((s.get("notes", "") for s in loc.get("stations", []) if s.get("notes")), "")
    out.append([round((c["longitude"] - O[0]) * 1e5), round((c["latitude"] - O[1]) * 1e5), loc["id"],
                loc.get("address", {}).get("address_string", "").strip(), notes.strip(), ports])
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "s": out}, open(os.path.join(OUT, "data", "endolla.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "locations,", sum(len(r[5]) for r in out), "ports")
