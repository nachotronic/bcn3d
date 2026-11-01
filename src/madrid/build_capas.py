"""Madrid city layers from datos.madrid.es / geoportal.madrid.es, in the compact format the page reads.

Usage: python3 build_capas.py RAW_DIR OUT_DIR   (run after build_overture.py, which writes data/pois.json)
RAW_DIR holds (see README for the URLs):
  sercalles.csv  SER: parking spaces by street and number with their colour (218228 "Calles y número de plazas")
  equip8.csv     municipal facilities (300331, converted to UTF-8)
  fuentes.csv    drinking fountains (300051)
  bici/Infraestructura_Ciclista.shp  cycle network (205107)
Writes:
  data/zones.json  {"o", "s": [[x, y, kind, spaces, "street number", battery], ...]}  kind 0 blue, 1 green, 2 orange, 3 red, 4 grey
  data/equip.json  {"o", "s": [[x, y, group, "name", "address"], ...]}  groups as in Barcelona: health, education, culture, sport, markets, government
  data/bici.json   {"o", "s": [[kind, "type", x, y, x, y, ...], ...]}  kind 0 ring, 1 exclusive, 2 preferred, 3 shared lane
  data/pois.json   "water" replaced by the city's operating drinking fountains
"""
import csv, json, math, os, re, sys
import duckdb

RAW, OUT = sys.argv[1], sys.argv[2]
O = (-3.89, 40.31)
xy = lambda lon, lat: [round((lon - O[0]) * 1e5), round((lat - O[1]) * 1e5)]
num = lambda v: float(str(v).replace(",", "."))


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


def street(s):  # "AGUAS, CALLE, DE LAS" -> "Calle de las Aguas"
    parts = [p.strip() for p in s.split(",")]
    name = " ".join([parts[1], parts[2], parts[0]] if len(parts) == 3 else [parts[1], parts[0]] if len(parts) == 2 else parts)
    small = {"de", "del", "la", "las", "los", "el", "y"}
    return " ".join(w if i and w in small else w[:1].upper() + w[1:] for i, w in enumerate(name.lower().split()))


def dump(name, obj):
    json.dump(obj, open(os.path.join(OUT, "data", name), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


# SER spaces
KIND = {"Azul": 0, "Verde": 1, "Naranja": 2, "Rojo": 3, "Gris": 4}
zones = []
with open(os.path.join(RAW, "sercalles.csv"), encoding="latin-1") as f:
    for r in csv.DictReader(f, delimiter=";"):
        k = next((v for c, v in KIND.items() if c in r["Color"]), None)
        if k is None or not r["Gis_X"]: continue
        lon, lat = utm30(num(r["Gis_X"]), num(r["Gis_Y"]))
        zones.append(xy(lon, lat) + [k, int(r["Número de Plazas"] or 0), f"{street(r['Calle'])} {r['Nº Finca']}".strip(),
                                     1 if r["Batería/Línea"].startswith("Bat") else 0])
dump("zones.json", {"o": O, "s": zones})

# facilities
GROUP = [("CentrosAtencionMedica|Hospital|Salud", 0), ("CentrosEducacion|Universidades|Escuelas|Enseñanza", 1),
         ("Bibliotecas|Museos|CentrosCulturales|Teatros|Auditorios|SalasExposiciones|GaleriasArte|Archivos|SalasEstudio", 2),
         ("Deporte", 3), ("Mercados|Comercios", 4),
         ("AyuntamientoMadrid|AdministracionCentral|ComunidadMadrid|Justicia|Oficinas|Comisarias|Policia|Bomberos|Registros", 5)]
equip = []
with open(os.path.join(RAW, "equip8.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        g = next((v for pat, v in GROUP if re.search(pat, r["TIPO"])), None)
        if g is None or not r["LATITUD"]: continue
        addr = " ".join(x for x in [r["CLASE-VIAL"].capitalize(), r["NOMBRE-VIA"].title(), r["NUM"]] if x)
        equip.append(xy(num(r["LONGITUD"]), num(r["LATITUD"])) + [g, r["NOMBRE"].strip(), addr])
dump("equip.json", {"o": O, "s": equip})

# cycle network
c = duckdb.connect(); c.execute("LOAD spatial")
KB = {1: 0, 3: 1, 4: 2, 5: 3}
bici = []
for tip, label, g in c.sql(f"""select COD_TIPOLO, d_COD_TI_1, ST_AsGeoJSON(ST_Transform(geom, 'EPSG:25830', 'OGC:CRS84', always_xy := true))
                               from ST_Read('{os.path.join(RAW, "bici", "Infraestructura_Ciclista.shp")}') where COD_TIPOLO in (1, 3, 4, 5)""").fetchall():
    gj = json.loads(g)
    for ln in [gj["coordinates"]] if gj["type"] == "LineString" else gj["coordinates"]:
        a = []
        for pt in ln:
            q = xy(pt[0], pt[1])   # the shapefile carries a Z
            if not a or abs(q[0] - a[-2]) + abs(q[1] - a[-1]) >= 3: a += q
        if len(a) >= 4:
            bici.append([KB[tip], label.split(",")[-1].strip().capitalize()] + a)
dump("bici.json", {"o": O, "s": bici})

# drinking fountains from the city instead of OpenStreetMap
P = json.load(open(os.path.join(OUT, "data", "pois.json"), encoding="utf-8"))
water = []
with open(os.path.join(RAW, "fuentes.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if r["ESTADO"] == "OPERATIVO" and r["LATITUD"]:
            lon, lat = num(r["LONGITUD"]), num(r["LATITUD"])
            water.append([round((lon - P["o"][0]) * 1e5), round((lat - P["o"][1]) * 1e5)])
P["water"] = water
dump("pois.json", P)
print(len(zones), "SER entries,", len(equip), "facilities,", len(bici), "cycle pieces,", len(water), "fountains")
