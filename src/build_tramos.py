"""Street sections used by the live traffic feed, from Open Data BCN transit_relacio_trams.csv.

Usage: python3 build_tramos.py transit_relacio_trams.csv OUT_DIR  -> OUT_DIR/data/tramos.json
The portal refuses cloud servers, so download the CSV in a browser and pass it here; it rarely changes.
Output: {"o":[lon,lat], "t": {"id": ["description", [x, y, x, y, ...]]}}
"""
import csv, json, os, sys

SRC, OUT = sys.argv[1], sys.argv[2]
O = (2.03, 41.30)


def fix(s):  # some descriptions are UTF-8 encoded twice
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


out = {}
with open(SRC, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        k = {c.lower()[:5]: c for c in r if c}
        nums = [float(v) for v in r[k["coord"]].split(",") if v.strip()]
        if len(nums) < 4: continue
        pts = []
        for x, y in zip(nums[::2], nums[1::2]):
            pts += [round((x - O[0]) * 1e5), round((y - O[1]) * 1e5)]
        out[r[k["tram"]].strip()] = [fix(r[k["descr"]].strip()), pts]
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "t": out}, open(os.path.join(OUT, "data", "tramos.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(out), "street sections")
