"""Current traffic state per street section (Open Data BCN, updated every 5 minutes; needs a token).

Usage: OPENDATA_BCN_TOKEN=... python3 traffic.py OUT_DIR  -> OUT_DIR/data/traffic.json
Output: {"t": "YYYY-MM-DD HH:MM", "o":[lon,lat], "s": [[state, forecast, "description", x, y, x, y, ...], ...]}
state / forecast: 0 no data, 1 very fluid, 2 fluid, 3 dense, 4 very dense, 5 congested, 6 closed.
"""
import csv, io, json, os, sys, urllib.error, urllib.request

OUT = sys.argv[1]
TOKEN = os.environ.get("OPENDATA_BCN_TOKEN", "").strip().strip("'\"")
O = (2.03, 41.30)
GEOM = ("https://opendata-ajuntament.barcelona.cat/data/dataset/1090983a-1c40-4609-8620-14ad49aae3ab/resource/"
        "1d6c814c-70ef-4147-aa16-a49ddb952f72/download/transit_relacio_trams.csv")
STATE = ("https://opendata-ajuntament.barcelona.cat/data/dataset/8319c2b1-4c21-4962-9acd-6db4c5ff1148/resource/"
         "2d456eb5-4ea6-4f68-9794-2f3f1a58a933/download")

if not TOKEN:
    sys.exit("OPENDATA_BCN_TOKEN is not set")
print("token length", len(TOKEN))


def get(url):
    raw, err = None, None
    for auth in (TOKEN, "Bearer " + TOKEN, None):  # the portal documents the bare token; try the others before failing
        h = {"User-Agent": "bcn3d-map/1.0 (+https://github.com/nachotronic/bcn3d)", "Accept": "*/*"}
        if auth: h["Authorization"] = auth
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60).read(); break
        except urllib.error.HTTPError as e:
            err = e
            print(url.rsplit("/", 3)[-2], "auth" if auth else "no auth", e.code, " ".join(e.read(800).decode("utf-8", "replace").split()))
    if raw is None: raise err
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass


def col(row, *names):  # header names vary in accents and case between releases
    keys = {k.strip().lower(): k for k in row if k}
    for n in names:
        for k, orig in keys.items():
            if k.startswith(n):
                return row[orig]
    return ""


geom = {}
for r in csv.DictReader(io.StringIO(get(GEOM))):
    tid = col(r, "tram").strip()
    raw = ",".join([col(r, "coordenades", "coordenadas"), *(r.get(None) or [])])  # unquoted coordinates spill over
    nums = [float(v) for v in raw.replace(";", ",").split(",") if v.strip()]
    if not tid or len(nums) < 4: continue
    pts = []
    for x, y in zip(nums[::2], nums[1::2]):
        pts += [round((x - O[0]) * 1e5), round((y - O[1]) * 1e5)]
    geom.setdefault(tid, ["", []])
    geom[tid][0] = col(r, "descrip").strip()
    geom[tid][1].append(pts)

out, stamp = [], ""
for line in get(STATE).splitlines():
    f = line.strip().split("#")
    if len(f) < 4 or f[0] not in geom: continue
    stamp = max(stamp, f[1])
    name, parts = geom[f[0]]
    for pts in parts:
        out.append([int(f[2] or 0), int(f[3] or 0), name, *pts])

t = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}" if len(stamp) >= 12 else ""
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"t": t, "o": O, "s": out}, open(os.path.join(OUT, "data", "traffic.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "sections, data from", t)
