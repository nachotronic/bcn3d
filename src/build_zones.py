"""Regulated on-street parking (area blava, area verda, DUM loading bays, bus) from Open Data BCN.

Usage: python3 build_zones.py OUT_DIR TRAMS.csv TARIFES.csv HORARIS.csv  -> OUT_DIR/data/zones.json
The portal refuses cloud servers, so download the CSVs in a browser and pass them here.
Output: {"o":[lon,lat], "k":["AZL","VM","VR","DUM","BUS"], "t":[[eur_per_unit, max_stay, "min"|"h"|"d", "short"], ...], "h":["short schedule", ...],
         "s":[[x1, y1, x2, y2, kind, places, tariff, schedule, resident_tariff, resident_schedule, "address"], ...]}
tariff / schedule index "t" / "h"; -1 when the section has none.
"""
import csv, json, os, re, sys

OUT, TRAMS, TARIFES, HORARIS = sys.argv[1:5]
O = (2.03, 41.30)
KINDS = ["AZL", "VM", "VR", "DUM", "BUS"]


def rows(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


tar, ti = [], {}
for r in rows(TARIFES):
    ti[r["ID_TARIFA"].strip()] = len(tar)
    unit = {"0": "min", "1": "h", "2": "d"}.get(r["TIPUS_FRACCIO"].strip(), "h")  # fraction the price and the maximum stay are counted in
    tar.append([float(r["IMPORT_FRACCIO"] or 0), int(r["TEMPS_MAXIM"] or 0), unit, r["DESC_CURTA"].strip()])
hor, hi = [], {}
for r in rows(HORARIS):
    hi[r["ID_HORARI"].strip()] = len(hor)
    hor.append(" ".join(r["DESC_CURTA"].split()))

out = []
for r in rows(TRAMS):
    k = r["TIPUS_TRAM"].strip()
    if k not in KINDS: continue
    try:
        a = [float(r[c]) for c in ("LONGITUD_I", "LATITUD_I", "LONGITUD_F", "LATITUD_F")]
    except ValueError:
        continue
    q = [round((a[0] - O[0]) * 1e5), round((a[1] - O[1]) * 1e5), round((a[2] - O[0]) * 1e5), round((a[3] - O[1]) * 1e5)]
    out.append(q + [KINDS.index(k), int(r["PLACES"] or 0), ti.get(r["ID_TARIFA"].strip(), -1), hi.get(r["ID_HORARIO"].strip(), -1),
                    ti.get(r["ID_TARIFA1"].strip(), -1), hi.get(r["ID_HORARIO1"].strip(), -1), re.sub(r"^\d+\.-\s*", "", " ".join(r["ADREÇA"].split()))])  # some carry an internal "1019.- " prefix
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "k": KINDS, "t": tar, "h": hor, "s": out}, open(os.path.join(OUT, "data", "zones.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print(len(out), "sections,", sum(r[5] for r in out), "places")
