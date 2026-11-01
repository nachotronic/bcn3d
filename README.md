# Barcelona en 3D

Mapa 3D de Barcelona: edificios a su altura con su dirección, metro, FGC, tranvía, Rodalies, bus, Bicing en directo,
calidad del aire, árboles, semáforos, recarga eléctrica, aparcamientos y fuentes.
El selector "Datos por barrio" colorea cada sección censal por voto, renta, edad, origen, estudios, paro,
alquiler y pisos turísticos.

Página: https://nachotronic.github.io/bcn3d/

## Datos
- Edificios, calles, parques, árboles, semáforos, aparcamientos, fuentes, recarga, direcciones: Overture Maps (OpenStreetMap y otros), release 2026-10-21.
- Metro, bus, tranvía y FGC: GTFS de TMB, TRAM y FGC (espejo de Mobility Database). Rodalies: GTFS de Renfe Cercanías.
- Secciones censales: [mapaelectoral.es](https://github.com/nachotronic/abstencio-catalunya) (INE, SERPAVI 2024, viviendas turísticas INE, generales 2023).
- Bicing: feed público GBFS, leído en directo por el navegador cada minuto.
- Tráfico: estado por tramo del Ajuntament (Open Data BCN), leído en directo por el navegador cada 5 min (el portal rechaza servidores en la nube, así que no pasa por GitHub Actions). `src/traffic.py` hace una copia con token si algún día se necesita.
- Calidad del aire: Generalitat de Catalunya (XVPCA), actualizado cada hora por GitHub Actions.

## Reconstruir
```
pip install duckdb
python3 src/build_sections.py ABST_REPO . # data/sections.json, sections.geojson (antes que build_overture)
TMB_KEY='app_id=...&app_key=...' OVERTURE_STAGE=DIR python3 src/build_overture.py . # index.html, data/base.json, data/pois.json, data/t/*.json
python3 src/build_transit.py GTFS_DIR . # data/transit.json
python3 src/bicing.py . && python3 src/air.py .
```

# Madrid en 3D

Página: https://nachotronic.github.io/bcn3d/madrid/ (mismo motor; código específico en `src/madrid/`).

## Datos
- Edificios, calles, parques, agua, árboles, semáforos, aparcamientos, fuentes, recarga, direcciones: Overture Maps, release 2026-10-21.
- Metro, Metro Ligero, Cercanías y autobuses EMT: GTFS del Consorcio Regional de Transportes (datos.crtm.es).
- BiciMAD: feed público GBFS, leído en directo por el navegador cada minuto.
- Tráfico: puntos de medida de Informo (Ayuntamiento de Madrid), leídos en directo cada 5 min y pintados sobre el tramo de calle que miden.
- Calidad del aire: tiempo real del Ayuntamiento de Madrid, leído en directo; `madrid/data/air.json` como respaldo.
- Árboles: inventario municipal (datos.madrid.es 300761), ~800.000 árboles con especie, altura y perímetro.
- Datos por barrio: secciones censales del geoportal municipal; renta y demografía del INE (Atlas de distribución de renta de los hogares, 2024); voto en las generales de julio de 2023 por mesa (datos.madrid.es 210278).
- Zonas SER (plazas por calle y color), equipamientos municipales, fuentes de beber y red ciclista: datos.madrid.es / geoportal.madrid.es.
- Obras e incidencias: Informo, leídas en directo cada 5 min.

## Reconstruir
```
python3 src/madrid/build_sections.py RAW_DIR madrid   # antes que build_overture (edificio -> sección)
export BBOX="40.31,-3.89,40.645,-3.52" OVERTURE_STAGE=DIR TEMPLATE=src/madrid/template.html
export WATER="subtype in ('river','lake','pond','reservoir','water','canal') and class not in ('wastewater','swimming_pool','drain','ditch')"
python3 src/build_overture.py madrid && python3 src/build_calles.py madrid && python3 src/madrid/build_tramos.py madrid
python3 src/madrid/build_transit.py GTFS_DIR madrid   # GTFS_DIR/{metro,ml,cer,emt}
CITY=madrid python3 src/bicing.py madrid && python3 src/madrid/air.py madrid
python3 src/madrid/build_arboles.py madrid RAW_DIR/arb2026.csv RAW_DIR/esp2.xlsx RAW_DIR/esp4.xlsx
python3 src/madrid/build_capas.py RAW_DIR madrid      # después de build_overture (reescribe las fuentes de pois.json)
```
