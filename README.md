# AeroFire: Harmonizing MODIS and VIIRS Active Fire Data
> NASA Space Apps Challenge 2026 · Challenge: **Harmonization of MODIS and VIIRS Hot Spots**
> Team AeroFire · İskenderun, Hatay, Türkiye

**Live Application:** https://ruzgarakar.github.io/aerofire/web/

## 1. The Problem: Apples and Oranges in Orbit
MODIS (~1 km resolution) and VIIRS (375 m resolution) are both incredible tools for detecting active fires from space, but they do not speak the same language. A single large fire event might register as one or two massive MODIS pixels, but the exact same fire will be picked up as dozens of smaller VIIRS pixels. 

If you look at raw detection counts, it looks like VIIRS is finding 4 or 5 times more fires than MODIS. But this is an optical illusion caused by spatial resolution. As MODIS approaches the end of its mission, we cannot simply stitch VIIRS data onto the historical MODIS record without a proper translation layer. That is exactly what AeroFire was built to solve.

## 2. What AeroFire Does
- **True Harmonization:** We don't just count raw pixels. We group detections into "fire clusters" (same day, within a 1.5 km radius) and map both sensors onto a shared daily 1 km grid. This allows us to compare MODIS and VIIRS on equal terms, shrinking the raw 4.55× detection gap down to a realistic 1.43×.
- **National-Scale Live Monitoring:** Our map doesn't just look at one city; it monitors all of Türkiye. Using NASA FIRMS Near-Real-Time (NRT) data, the dashboard updates hourly. Users can filter by time (Live, 10 days, 1 month, up to 1 year) and view a **Province Report** for any of the 81 provinces, detailing MODIS/VIIRS splits and fire group statistics.
- **Real-World Case Study:** To prove our methodology, we locked the Belen fire (Hatay, October 2020) as a fixed case study. This allows us to demonstrate exactly how the harmonization algorithm behaves under controlled conditions.
- **Settlement-Risk Prototype:** We went a step further to show how this data can be used in the real world. By combining live fire data with current 10m wind data (Open-Meteo), we created a rule-based screening tool that flags settlements downwind of active fires. *(Note: This is a heuristic screening prototype, not a full atmospheric smoke dispersion model.)*

## 3. How It Works: The Pipeline
We built a robust, zero-dependency backend to fetch and filter the data, feeding into a Python harmonization layer and a sleek Leaflet frontend.

```text
[ NASA FIRMS API (MODIS, VIIRS S-NPP, VIIRS NOAA-20) ]
       ↓ (Hourly Live Fetch / Daily Archive Fetch via GitHub Actions)
[ scripts/ ] (Bash & Awk Backend)
       ↓ (API rate-limit management, GeoJSON Point-in-Polygon boundary filtering)
[ data/processed/tr_archive.csv ]
       ↓ 
[ harmonize/harmonize.py ]
       ↓ (Fire clustering, 1 km Grid mapping, static heat source removal)
[ web/data/*.json ]
       ↓ 
[ web/index.html, web/belen.html, web/risk.html ] (Leaflet Interactive Map)
