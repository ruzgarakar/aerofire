# AeroFire — Data Format Contract for Active Fire Points

This document defines the structural contract for the raw point CSV file generated at the input layer of the fire analysis pipeline. All subsequent layers treat this file as the single source of truth.

Pipeline: `scripts/` → `data/processed/hatay_points.csv` → `harmonize/harmonize.py` → `web/data/points.json` → `web/app.js`

---

## 1. Input: `data/processed/hatay_points.csv`

### 1.1. File Properties

| Property | Value |
|---|---|
| Filename | `hatay_points.csv` |
| Character Encoding | UTF-8 (without BOM) |
| Line Endings | `\n` (LF) |
| Delimiter | `,` (comma) |
| Decimal Separator | `.` (dot) |
| Header Row | Mandatory — Line 1 must contain column names |
| Locale | Must be generated with `LC_ALL=C` (prevents decimal commas in Turkish locale) |

### 1.2. Column Schema

The header row must exactly match the following (case-sensitive, no spaces):
Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type

| # | Column | Type | Unit | Description |
|---|---|---|---|---|
| 1 | `Sensor` | string | — | `MODIS` or `VIIRS`. If empty, inferred from satellite name (Terra/Aqua = MODIS) |
| 2 | `Latitude` | float | degrees | WGS84. `-90 ≤ x ≤ 90`. 4-5 decimals |
| 3 | `Longitude` | float | degrees | WGS84. `-180 ≤ x ≤ 180`. 4-5 decimals |
| 4 | `Brightness_K` | float | Kelvin | MODIS: channel 21/22, VIIRS: I4. Different channels — cannot be directly compared |
| 5 | `Acq_Date` | string | — | `YYYY-MM-DD`, UTC |
| 6 | `Acq_Time` | string | — | `HHMM` (24h, UTC). Pad with zero if 3 digits (e.g., `750` → `0750`) |
| 7 | `Satellite` | string | — | MODIS: `Terra` / `Aqua`; VIIRS: `N` (Suomi NPP), `1` (NOAA-20) |
| 8 | `Confidence` | string | — | MODIS: `0-100` numeric; VIIRS: `l` / `n` / `h` |
| 9 | `FRP` | float | MW | Fire Radiative Power. Can be empty |
| 10 | `Type` | integer | — | `0` vegetation fire, `1` volcano, `2` static heat source, `3` offshore |

Column names are case-insensitive. Raw FIRMS names like `lat`, `lon`, `bright_ti4`, `instrument` are also recognized in the harmonization layer; however, this contract enforces canonical names.

### 1.3. Type → Category Mapping

The harmonization layer maps the `Type` column to the `category` field based on the following rule:

| `Type` | `category` | Pipeline Action |
|---|---|---|
| `0` | `vegetation` | Primary data — included in all counts |
| `1` | `volcano` | Excluded from analysis, written to `points[]` |
| `2` | `static` | Filtered out — incremented in `meta.counts.excluded_static` |
| `3` | `offshore` | Filtered out — incremented in `meta.counts.excluded_offshore` |
| empty / undefined | `unknown` | Excluded from analysis |

**Critical Rule:** Only rows with `category = "vegetation"` are included in `meta.counts.modis`, `meta.counts.viirs`, `grid[]`, and `fires[]` calculations. Other categories are visible in the `points[]` array (so the map can display them in gray), but are excluded from aggregations.

### 1.4. Data Integrity Verification Commands

After the script generates the output, verify integrity with the following commands:

```bash
# 1. Every row must have 10 columns
awk -F',' '{print NF}' hatay_points.csv | sort -u
# Expected single value: 10

# 2. Header row must match exactly
head -1 hatay_points.csv
# Expected: Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type

# 3. Sensor values must be MODIS or VIIRS only
awk -F',' 'NR>1 {print $1}' hatay_points.csv | sort -u
# Expected: MODIS, VIIRS

# 4. Type column must be 0, 1, 2, or 3
awk -F',' 'NR>1 {print $10}' hatay_points.csv | sort -u
# Expected: 0, 1, 2, 3 (based on usage)

# 5. Date format must be YYYY-MM-DD
awk -F',' 'NR>1 && $5 !~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/ {print NR": "$5}' hatay_points.csv
# Expected: no output

# 6. Time must be 4 characters
awk -F',' 'NR>1 && length($6)!=4 {print NR": "$6}' hatay_points.csv
# Expected: no output

# 7. Coordinates must be within the Turkey bounding box
awk -F',' 'NR>1 && ($2<35.7 || $2>42.2 || $3<25.5 || $3>44.9) {print NR}' hatay_points.csv
# Expected: no output

1.5:Samples
Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type
MODIS,36.5326,36.1739,321.1,2020-10-08,0750,Terra,59,12.3,0
MODIS,36.6094,36.1886,340.5,2020-10-08,0750,Aqua,75,45.2,2
MODIS,36.5912,36.1647,335.8,2020-10-09,1023,Terra,88,27.6,0
VIIRS,36.5326,36.1739,337.01,2020-10-08,1055,N,l,5.89,0
VIIRS,36.6153,36.1806,335.5,2020-10-08,1055,1,n,8.4,2
VIIRS,36.5901,36.1742,367.0,2020-10-09,1310,N,h,142.7,0

Output:{
  "meta":   { ... },
  "fires":  [ ... ],
  "grid":   [ ... ],
  "points": [ ... ]
}
