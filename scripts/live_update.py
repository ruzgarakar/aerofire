import csv
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from firms_common import api_fetch, in_turkey  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {"MODIS_NRT": "MODIS", "VIIRS_SNPP_NRT": "VIIRS", "VIIRS_NOAA20_NRT": "VIIRS"}
DAYS = 2          # how many days are asked from NASA every hour
KEEP_DAYS = 7     # how many days of detections are kept and shown
HEADER = ["Sensor", "Latitude", "Longitude", "Brightness_K", "Acq_Date", "Acq_Time", "Satellite", "Confidence", "FRP", "Type"]
OUT_CSV = ROOT / "data" / "processed" / "live_points.csv"
OUT_JSON = ROOT / "web" / "data" / "live.json"
STATIC = ROOT / "data" / "static_cells.json"


def fetch(source):
    sample = os.environ.get("AEROFIRE_SAMPLE_DIR")
    if sample:
        return Path(sample, source + ".csv").read_text(encoding="utf-8")
    return api_fetch(source, DAYS)


def cell(lat, lon):
    return f"{round(lat, 2):.2f},{round(lon, 2):.2f}"


def main():
    static = set(json.loads(STATIC.read_text(encoding="utf-8"))["cells"])
    rows, dropped, failed = [], 0, []
    for source, sensor in SOURCES.items():
        text = fetch(source)
        if text is None:
            failed.append(source)
            continue
        for r in csv.DictReader(io.StringIO(text)):
            try:
                lat, lon = float(r["latitude"]), float(r["longitude"])
            except (KeyError, ValueError):
                continue
            if cell(lat, lon) in static or not in_turkey(lat, lon):
                dropped += 1
                continue
            bright = r.get("brightness") or r.get("bright_ti4") or ""
            rows.append([sensor, lat, lon, bright, r["acq_date"], r["acq_time"],
                         r.get("satellite", ""), r["confidence"], r.get("frp", ""), "0"])
    if failed:
        sys.exit("Could not fetch: " + ", ".join(failed) + " (live.json left unchanged)")
    # keep earlier detections too, so a fire that appeared hours ago stays on the map
    keep_from = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    seen = {(r[0], str(r[1]), str(r[2]), r[4], str(r[5]).zfill(4)) for r in rows}
    if OUT_CSV.exists():
        with open(OUT_CSV, newline="", encoding="utf-8") as f:
            for o in csv.reader(f):
                if len(o) < 10 or o[0] == "Sensor":
                    continue
                key = (o[0], o[1], o[2], o[4], o[5].zfill(4))
                if key not in seen and o[4] >= keep_from:
                    seen.add(key)
                    rows.append(o)
    rows = [r for r in rows if str(r[4]) >= keep_from]
    rows.sort(key=lambda x: (str(x[4]), str(x[5]).zfill(4), str(x[1]), str(x[2])))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"{len(rows)} detections kept, {dropped} known static sources removed")
    subprocess.run([sys.executable, str(ROOT / "harmonize" / "harmonize.py"),
                    "--input", str(OUT_CSV), "--output", str(OUT_JSON)], check=True)
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    data["meta"]["region"] = "Türkiye"
    data["meta"]["live"] = {"source": "FIRMS NRT", "days": KEEP_DAYS, "static_removed": dropped,
                            "note": "NASA updates NRT data about every 3 hours"}
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
