"""Daily job: extend the Türkiye archive with the newest NASA FIRMS data and rebuild web/data/tr_year.json.

Seed: data/processed/tr_archive.csv (FIRMS archive, Nov 2025 - Aug 2026, static sources already flagged as type 2).
New days come from the near-real-time (NRT) sources, which carry no `type` column, so known static
heat sources (data/static_cells.json) are removed instead.
Needs MAP_KEY. Test without internet: AEROFIRE_SAMPLE_DIR=<folder with MODIS_NRT.csv, VIIRS_SNPP_NRT.csv, VIIRS_NOAA20_NRT.csv>.
"""
import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "data" / "processed" / "tr_archive.csv"
STATIC = ROOT / "data" / "static_cells.json"
OUT_JSON = ROOT / "web" / "data" / "tr_year.json"
SOURCES = {"MODIS_NRT": "MODIS", "VIIRS_SNPP_NRT": "VIIRS", "VIIRS_NOAA20_NRT": "VIIRS"}
HEADER = ["Sensor", "Latitude", "Longitude", "Brightness_K", "Acq_Date", "Acq_Time", "Satellite", "Confidence", "FRP", "Type"]
CHUNK = 5
KEEP_DAYS = 366


def fetch(source, start, days):
    sample = os.environ.get("AEROFIRE_SAMPLE_DIR")
    if sample:
        p = Path(sample, source + ".csv")
        return p.read_text(encoding="utf-8") if p.exists() else ""
    key = os.environ.get("MAP_KEY", "").strip()
    if not key:
        sys.exit("MAP_KEY is missing")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{key}/{source}/TUR/{days}/{start}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                text = r.read().decode("utf-8")
            if text.lstrip().lower().startswith("latitude"):
                return text
            print(f"{source} {start}: unexpected answer {text[:60]!r}")
            return ""
        except Exception as e:
            print(f"{source} {start}: attempt {attempt + 1} failed: {type(e).__name__}")
            time.sleep(5 * (attempt + 1))
    return None


def cell(lat, lon):
    return f"{round(lat, 2):.2f},{round(lon, 2):.2f}"


def main():
    static = set(json.loads(STATIC.read_text(encoding="utf-8"))["cells"])
    rows, seen = [], set()
    with open(ARCHIVE, newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            if len(r) < 10 or r[0] == "Sensor":
                continue
            rows.append(r)
            seen.add((r[0], r[1], r[2], r[4], r[5].zfill(4)))
    last = max(r[4] for r in rows)
    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(last) - timedelta(days=1)
    added, failed, empty = 0, [], []
    cur = start
    while cur <= today:
        days = min(CHUNK, (today - cur).days + 1)
        got = 0
        for source, sensor in SOURCES.items():
            text = fetch(source, cur.isoformat(), days)
            if text is None:
                failed.append(f"{source} {cur}")
                continue
            for r in csv.DictReader(io.StringIO(text)):
                try:
                    lat, lon = float(r["latitude"]), float(r["longitude"])
                except (KeyError, ValueError):
                    continue
                if cell(lat, lon) in static:
                    continue
                bright = r.get("brightness") or r.get("bright_ti4") or ""
                new = [sensor, str(lat), str(lon), bright, r["acq_date"], r["acq_time"].zfill(4),
                       r.get("satellite", ""), r["confidence"], r.get("frp", ""), "0"]
                key = (sensor, new[1], new[2], new[4], new[5])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(new)
                added += 1
                got += 1
        if got == 0:
            empty.append(f"{cur}..{cur + timedelta(days=days - 1)}")
        cur += timedelta(days=days)
    if failed:
        print("WARNING, could not fetch:", ", ".join(failed))
    if empty:
        print("No data returned for:", ", ".join(empty))
    keep_from = (today - timedelta(days=KEEP_DAYS)).isoformat()
    rows = [r for r in rows if r[4] >= keep_from]
    rows.sort(key=lambda x: (x[4], x[5], x[1], x[2]))
    with open(ARCHIVE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"{added} new detections, archive now {len(rows)} rows, latest date {max(r[4] for r in rows)}")
    subprocess.run([sys.executable, str(ROOT / "harmonize" / "harmonize.py"),
                    "--input", str(ARCHIVE), "--output", str(OUT_JSON)], check=True, stdout=subprocess.DEVNULL)
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    data["meta"]["region"] = "Türkiye"
    data["meta"]["latest_date"] = max(r[4] for r in rows)
    data["meta"]["gaps"] = empty
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("tr_year.json written:", OUT_JSON.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
