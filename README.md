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
- Tráfico: estado por tramo del Ajuntament (Open Data BCN), cada 10 min por GitHub Actions. Necesita el secreto `OPEN_DATA_TOKEN`.
- Calidad del aire: Generalitat de Catalunya (XVPCA), actualizado cada hora por GitHub Actions.

## Reconstruir
```
pip install duckdb
python3 src/build_sections.py ABST_REPO . # data/sections.json, sections.geojson (antes que build_overture)
OVERTURE_STAGE=DIR python3 src/build_overture.py . # index.html, data/base.json, data/pois.json, data/t/*.json
python3 src/build_transit.py GTFS_DIR . # data/transit.json
python3 src/bicing.py . && python3 src/air.py .
```
