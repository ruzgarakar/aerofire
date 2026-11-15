# AeroFire — Active Fire Point Data Format

This document defines the canonical CSV input contract for active fire points and describes how the harmonization pipeline interprets each row.

The canonical input file is:

`data/processed/hatay_points.csv`

Pipeline:

`scripts/` → `data/processed/hatay_points.csv` → `harmonize/harmonize.py` → `web/data/points.json` → `web/app.js`

The CSV is the source of truth for the input point records. The harmonizer may accept legacy FIRMS column names as a convenience, but files produced for this pipeline should use the canonical header defined below.

---

## 1. Input file

### 1.1. File properties

| Property | Requirement |
|---|---|
| Filename | `hatay_points.csv` |
| Encoding | UTF-8 without a byte-order mark (BOM) |
| Line endings | LF (`\n`) |
| Delimiter | Comma (`,`) |
| Decimal separator | Period (`.`) |
| Header | Required; must be the first record |
| Locale | Generate with `LC_ALL=C` when using locale-sensitive tools |

The file follows standard CSV quoting rules. Fields containing commas, quotes, or line breaks must be quoted and embedded quotes must be escaped according to CSV conventions. Consumers must parse the file as CSV rather than splitting lines on commas.

### 1.2. Canonical header

The header must match this exact sequence, including spelling and capitalization:

```text
Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type
```

The canonical file must not include extra, missing, or reordered columns. Although the harmonizer may recognize alternate names or capitalization for legacy input, that behavior does not change this contract.

### 1.3. Column schema

| # | Column | Format | Required? | Description |
|---|---|---|---|---|
| 1 | `Sensor` | `MODIS` or `VIIRS` | Yes, except as described below | Instrument family. If empty, it is inferred from `Satellite`. |
| 2 | `Latitude` | Finite decimal number | Yes | WGS84 latitude in degrees; range `-90` to `90`. |
| 3 | `Longitude` | Finite decimal number | Yes | WGS84 longitude in degrees; range `-180` to `180`. |
| 4 | `Brightness_K` | Finite decimal number | Yes | Brightness temperature in Kelvin. MODIS and VIIRS use different channels, so values are not directly comparable. |
| 5 | `Acq_Date` | `YYYY-MM-DD` | Yes | Acquisition date in UTC; must be a real calendar date. |
| 6 | `Acq_Time` | `HHMM` | Yes | Acquisition time in UTC, 24-hour clock. Hours are `00`–`23`; minutes are `00`–`59`. |
| 7 | `Satellite` | See values below | Yes | Satellite/platform identifier. |
| 8 | `Confidence` | Sensor-specific; see below | Yes | Confidence value supplied by the source product. |
| 9 | `FRP` | Finite decimal number or empty | No | Fire Radiative Power in megawatts (MW). Empty means unavailable. |
| 10 | `Type` | `0`, `1`, `2`, `3`, or empty | No | FIRMS fire-pixel type. An empty value is treated as unknown. |

Coordinates should retain the precision provided by the source. Four to five decimal places are typical, but the contract does not require a fixed number of decimal places.

#### Sensor and satellite values

| `Sensor` | Allowed `Satellite` values | Inference when `Sensor` is empty |
|---|---|---|
| `MODIS` | `Terra`, `Aqua` | `Terra` or `Aqua` → `MODIS` |
| `VIIRS` | `N`, `1` | `N` or `1` → `VIIRS` |

`N` identifies Suomi NPP; `1` identifies NOAA-20. Sensor and satellite values are case-sensitive in the canonical file.

If `Sensor` is empty and `Satellite` is missing or unrecognized, the row is invalid because the sensor cannot be inferred.

#### Confidence values

- For `MODIS`, `Confidence` must be a whole number from `0` to `100`, inclusive.
- For `VIIRS`, `Confidence` must be one of `l`, `n`, or `h` (low, nominal, or high).
- Confidence values are interpreted according to the sensor and must not be compared across sensors as if they shared a scale.

### 1.4. Type-to-category mapping

The harmonizer maps `Type` to a category as follows:

| `Type` | Category | Harmonization behavior |
|---|---|---|
| `0` | `vegetation` | Included in vegetation fire counts, `grid[]`, and `fires[]`; included in `points[]`. |
| `1` | `volcano` | Excluded from vegetation analysis; retained in `points[]`. |
| `2` | `static` | Excluded from analysis and `points[]`; counted in `meta.counts.excluded_static`. |
| `3` | `offshore` | Excluded from analysis and `points[]`; counted in `meta.counts.excluded_offshore`. |
| Empty | `unknown` | Excluded from analysis and output. |

Only rows categorized as `vegetation` contribute to `meta.counts.modis`, `meta.counts.viirs`, `grid[]`, or `fires[]`. The `points[]` array contains vegetation and volcano records; static, offshore, and unknown records are not included.

### 1.5. Legacy FIRMS input names

The harmonizer may accept raw FIRMS files that use source column names instead of the canonical names. Examples include:

| Canonical name | Example source names |
|---|---|
| `Latitude` | `lat` |
| `Longitude` | `lon` |
| `Brightness_K` | `bright_ti4`, `bright_ti5`, or another source brightness field |
| `Sensor` | `instrument` |

This is a harmonizer compatibility feature. Before treating a file as canonical input, convert its header and values to the schema in Section 1.3. The exact aliases accepted by the harmonizer are implementation-specific.

### 1.6. Sample input

```csv
Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type
MODIS,36.5326,36.1739,321.1,2020-10-08,0750,Terra,59,12.3,0
MODIS,36.6094,36.1886,340.5,2020-10-08,0750,Aqua,75,45.2,2
MODIS,36.5912,36.1647,335.8,2020-10-09,1023,Terra,88,27.6,0
VIIRS,36.5326,36.1739,337.01,2020-10-08,1055,N,l,5.89,0
VIIRS,36.6153,36.1806,335.5,2020-10-08,1055,1,n,8.4,2
VIIRS,36.5901,36.1742,367.0,2020-10-09,1310,N,h,142.7,0
```

In this example, the rows with `Type=2` are counted as static heat sources and are not included in the analysis output.

---

## 2. Validation

Run validation from the repository root, passing the CSV path:

```bash
python3 - data/processed/hatay_points.csv <<'PY'
import csv
import io
import math
import re
import sys
from datetime import date
from pathlib import Path

EXPECTED_HEADER = [
    "Sensor",
    "Latitude",
    "Longitude",
    "Brightness_K",
    "Acq_Date",
    "Acq_Time",
    "Satellite",
    "Confidence",
    "FRP",
    "Type",
]

SATELLITE_SENSOR = {
    "Terra": "MODIS",
    "Aqua": "MODIS",
    "N": "VIIRS",
    "1": "VIIRS",
}

errors = []
path = Path(sys.argv[1])
raw = path.read_bytes()

if raw.startswith(b"\xef\xbb\xbf"):
    errors.append("file must not contain a UTF-8 BOM")

if b"\r" in raw:
    errors.append("file must use LF line endings, not CRLF or CR")

try:
    text = raw.decode("utf-8")
except UnicodeDecodeError as exc:
    print(f"Invalid UTF-8: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    header = next(reader, None)

    if header != EXPECTED_HEADER:
        errors.append(
            "header must exactly match: " + ",".join(EXPECTED_HEADER)
        )

    for row in reader:
        line = reader.line_num

        if len(row) != len(EXPECTED_HEADER):
            errors.append(
                f"line {line}: expected 10 columns, found {len(row)}"
            )
            continue

        (
            sensor,
            latitude,
            longitude,
            brightness,
            acq_date,
            acq_time,
            satellite,
            confidence,
            frp,
            fire_type,
        ) = row

        inferred_sensor = SATELLITE_SENSOR.get(satellite)
        if not sensor:
            sensor = inferred_sensor or ""
        elif sensor not in ("MODIS", "VIIRS"):
            errors.append(f"line {line}: Sensor must be MODIS or VIIRS")

        if not sensor:
            errors.append(
                f"line {line}: Sensor is empty and cannot be inferred "
                "from Satellite"
            )
        elif inferred_sensor and sensor != inferred_sensor:
            errors.append(
                f"line {line}: Sensor does not match Satellite"
            )

        for name, value, low, high in (
            ("Latitude", latitude, -90, 90),
            ("Longitude", longitude, -180, 180),
        ):
            try:
                number = float(value)
                if not math.isfinite(number) or not low <= number <= high:
                    raise ValueError
            except ValueError:
                errors.append(
                    f"line {line}: {name} must be a finite number "
                    f"between {low} and {high}"
                )

        try:
            brightness_number = float(brightness)
            if not math.isfinite(brightness_number):
                raise ValueError
        except ValueError:
            errors.append(
                f"line {line}: Brightness_K must be a finite number"
            )

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", acq_date):
            errors.append(f"line {line}: Acq_Date must use YYYY-MM-DD")
        else:
            try:
                date.fromisoformat(acq_date)
            except ValueError:
                errors.append(f"line {line}: Acq_Date is not a real date")

        if not re.fullmatch(r"\d{4}", acq_time):
            errors.append(f"line {line}: Acq_Time must use HHMM")
        else:
            hour = int(acq_time[:2])
            minute = int(acq_time[2:])
            if hour > 23 or minute > 59:
                errors.append(f"line {line}: Acq_Time is not a valid UTC time")

        if satellite not in SATELLITE_SENSOR:
            errors.append(
                f"line {line}: Satellite must be Terra, Aqua, N, or 1"
            )

        if sensor == "MODIS":
            if not re.fullmatch(r"\d+", confidence):
                errors.append(
                    f"line {line}: MODIS Confidence must be an integer "
                    "from 0 to 100"
                )
            elif not 0 <= int(confidence) <= 100:
                errors.append(
                    f"line {line}: MODIS Confidence must be from 0 to 100"
                )
        elif sensor == "VIIRS" and confidence not in ("l", "n", "h"):
            errors.append(
                f"line {line}: VIIRS Confidence must be l, n, or h"
            )

        if frp:
            try:
                frp_number = float(frp)
                if not math.isfinite(frp_number) or frp_number < 0:
                    raise ValueError
            except ValueError:
                errors.append(
                    f"line {line}: FRP must be empty or a finite "
                    "non-negative number"
                )

        if fire_type and fire_type not in ("0", "1", "2", "3"):
            errors.append(
                f"line {line}: Type must be 0, 1, 2, 3, or empty"
            )

except csv.Error as exc:
    errors.append(f"invalid CSV: {exc}")
except StopIteration:
    errors.append("file is empty; a header row is required")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)

print(f"Valid CSV: {path}")
PY
```

This validator checks the CSV structure and field formats. If the dataset is expected to contain only Hatay observations, apply a separate, documented geographic sanity check; do not treat a regional bounding box as a substitute for the WGS84 coordinate limits in the schema.

---

## 3. Harmonizer output

The harmonizer writes JSON to `web/data/points.json`. The top-level structure is:

```json
{
  "meta": {},
  "fires": [],
  "grid": [],
  "points": []
}
```

The exact fields within `meta`, `fires`, `grid`, and `points` are defined by the harmonizer implementation. Keep this document’s category rules in sync with that implementation and its tests.
