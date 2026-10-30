"""Street and house-number index for the search box, from Overture addresses.

Usage: OVERTURE_STAGE=dir python3 build_calles.py OUT_DIR  -> OUT_DIR/data/calles.json
Output: {"o":[lon,lat], "s":[["Carrer de Balmes", x, y, "1", dx, dy, "3", dx, dy, ...], ...]}
x, y is the street's middle address; each number is stored as an offset from it (1e-5 degrees).
"""
import json, os, re, sys
import duckdb

OUT, STAGE = sys.argv[1], os.environ["OVERTURE_STAGE"]
O = (2.03, 41.30)
SMALL = {"de", "del", "dels", "la", "les", "el", "els", "i", "d", "l", "y", "s", "n"}


def nice(s):  # "CARRER DE L'ARC DE SANT MARTI" -> "Carrer de l'Arc de Sant Marti"
    words = re.split(r"(\s+|')", s.lower())
    return "".join(w if (i and w in SMALL) else w[:1].upper() + w[1:] for i, w in enumerate(words)).strip()


def numkey(n):
    m = re.match(r"(\d+)", n or "")
    return (int(m.group(1)) if m else 10 ** 6, n or "")


c = duckdb.connect(); c.execute("LOAD spatial")
rows = c.sql(f"""select street, number, avg(ST_X(geometry)) x, avg(ST_Y(geometry)) y from '{STAGE}/address.parquet'
  where street is not null and number is not null group by street, number""").fetchall()
streets = {}
for st, n, x, y in rows:
    streets.setdefault(st.strip(), []).append((numkey(n.strip()), n.strip(), round((x - O[0]) * 1e5), round((y - O[1]) * 1e5)))
out = []
for st, nums in sorted(streets.items()):
    nums.sort()
    _, _, x0, y0 = nums[len(nums) // 2]
    row = [nice(st), x0, y0]
    for _, n, x, y in nums:
        row += [n, x - x0, y - y0]
    out.append(row)
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
json.dump({"o": O, "s": out}, open(os.path.join(OUT, "data", "calles.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(out), "streets,", len(rows), "numbers")
