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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from firms_common import api_fetch, in_turkey  # noqa: E402

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
    return api_fetch(source, days, start, timeout=45, tries=2)


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
        print(f"chunk {cur} +{days}d", flush=True)
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
                if cell(lat, lon) in static or not in_turkey(lat, lon):
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
