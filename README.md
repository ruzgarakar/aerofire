# AeroFire — One Fire, One Story

> NASA Space Apps Challenge 2026 · Challenge: **Harmonization of MODIS and VIIRS Hot Spots**
> Team AeroFire · İskenderun, Hatay, Türkiye

**Live map:** [LINK]  ·  **Demo slides:** [LINK]

## The problem
<!-- PAZAR doldurulacak (Rüzgar + Ahmet): 3-4 cümle. İki sensör aynı yangını farklı görüyor... -->

## What AeroFire does
<!-- PAZAR: 3 madde. Uyumlaştırma / kesintisiz kayıt / otomatik güncellenen harita -->

## How it works
```
NASA FIRMS (MODIS + VIIRS)  →  scripts/  →  data/processed/hatay_points.csv
                            →  harmonize/harmonize.py  →  web/data/points.json
                            →  web/index.html (Leaflet map)
```

## Results (Hatay, 8–12 October 2020)
<!-- Cumartesi 16:00'daki tek çalıştırmanın sayıları -->
| | MODIS | VIIRS |
| --- | --- | --- |
| Hot spots | [SAYI] | [SAYI] |
| Matched fires | [SAYI] | |

## Run it yourself
```bash
# 1. Get a free FIRMS MAP_KEY: https://firms.modaps.eosdis.nasa.gov/api/map_key/
export MAP_KEY=your_key_here        # never commit your key
# 2. Download + filter data
bash scripts/<AKAY_SCRIPT>.sh
# 3. Harmonize
python harmonize/harmonize.py
# 4. Open the map with VS Code Live Server: web/index.html
```

## Data sources
- NASA FIRMS active fire data: MODIS (MODIS_SP), VIIRS S-NPP (VIIRS_SNPP_SP), VIIRS NOAA-20 (VIIRS_NOAA20_SP) — https://firms.modaps.eosdis.nasa.gov
- Province boundary: GADM 4.1 (https://gadm.org) — downloaded at runtime, not redistributed

## Team
- Ahmet — Team lead, harmonization
- Akay — Data & backend
- Ceyhun — Design & frontend
- Rüzgar — Research & impact

## Notes on preparation and AI use
- Before the event we prepared only the folder structure, empty templates and a data-download helper script. All harmonization logic, the map and the results were built during the hackathon (14–15 November 2026).
- AI tools were used; see `docs/AI_LOG.md`.

## License
MIT
