# AeroFire: Harmonization of MODIS and VIIRS Active Fire Data
> NASA Space Apps Challenge 2026 · Challenge: Harmonization of MODIS and VIIRS Hot Spots
> Team AeroFire · İskenderun, Hatay, Türkiye

## 1. Problem Statement
Multi-sensor satellite observations of active fires (MODIS and VIIRS) differ significantly in spatial resolution (1 km vs. 375 m), detection sensitivity, and overpass timing. This heterogeneity creates a data fusion challenge for disaster management and environmental monitoring. Furthermore, analyzing border regions (e.g., Hatay, Türkiye) requires eliminating false positives originating from neighboring countries (e.g., Syria) and distinguishing actual vegetation fires from permanent industrial heat sources (Type 2 anomalies). 

## 2. Core Capabilities
- **Multi-Sensor Harmonization:** Aggregates and harmonizes disparate MODIS and VIIRS data points into a unified 1 km spatial grid to enable direct, cross-sensor comparison and spatial matching.
- **Geospatial Filtering (Point-in-Polygon):** Implements a custom Ray-Casting algorithm in pure `awk` to clip raw satellite data strictly to regional boundaries using GADM GeoJSON polygons. This completely eliminates cross-border false positives and isolates `Type 0` (vegetation) fires.
- **Intelligent Polling (Auto-Mode):** Utilizes NASA FIRMS Near Real-Time (NRT) API with an `md5` checksum-based change detection system. The backend polls the API at configurable intervals, dynamically updating the web map only when new anomalies are detected, optimizing bandwidth and API quotas.

## 3. System Architecture & Data Pipeline
```text
[ NASA FIRMS API (MODIS & VIIRS) ]
       ↓ (Data fetching with API rate-limit management: 5-day chunks)
[ scripts/datapuller.sh ] (Backend: Bash + Awk)
       ↓ (Type 2 exclusion & GeoJSON Boundary Filtering)
[ data/processed/hatay_points.csv ] (10-column raw point data)
       ↓ 
[ harmonize/harmonize.py ]
       ↓ (1 km Grid Aggregation & MODIS/VIIRS Matching)
[ web/data/points.json ]
       ↓ 
[ web/index.html ] (Frontend: Leaflet Interactive Map)
