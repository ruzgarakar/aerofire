import csv
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


PROJECT_DIR = Path(__file__).resolve().parent
API_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
REGIONS = {
    "turkiye": {
        "name": "Türkiye",
        "slug": "turkiye",
        "bbox": (25.60, 35.80, 44.80, 42.10),
        "boundary": "turkiye_sinir.txt",
    },
    "hatay": {
        "name": "Hatay",
        "slug": "hatay",
        "bbox": (35.75, 35.80, 36.75, 37.00),
        "boundary": "hatay_sinir.txt",
    },
    "iskenderun": {
        "name": "İskenderun",
        "slug": "iskenderun",
        "bbox": (35.75, 36.25, 36.60, 36.75),
        "boundary": "hatay_sinir.txt",
    },
}
ARCHIVE_DAYS = {"10", "30", "90", "180", "365"}
POINT_HEADER = (
    "Sensor", "Latitude", "Longitude", "Brightness_K", "Acq_Date",
    "Acq_Time", "Satellite", "Confidence", "FRP", "Type",
)
SOURCES = (
    ("MODIS", "MODIS"),
    ("VIIRS_SNPP", "VIIRS"),
    ("VIIRS_NOAA20", "VIIRS"),
)


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError("Tarih YYYY-MM-DD biçiminde olmalı.") from None


def get_date_range(config):
    today = date.today()
    if config["kind"] == "nrt":
        return today - timedelta(days=1), today

    period = str(config.get("archiveDays", "10"))
    if period == "custom":
        start = parse_date(config.get("startDate"))
        end = parse_date(config.get("endDate"))
        if start > end:
            raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
        return start, end
    if period not in ARCHIVE_DAYS:
        raise ValueError("Geçerli bir Archive zaman aralığı seçin.")
    days = int(period)
    end = today - timedelta(days=2)
    return today - timedelta(days=days), end


def date_chunks(start, end):
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=4), end)
        yield current, (chunk_end - current).days + 1
        current = chunk_end + timedelta(days=1)


def parse_api_csv(body, sensor):
    text = body.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames or "latitude" not in {
        field.strip().lower() for field in reader.fieldnames if field
    }:
        raise RuntimeError(
            "NASA FIRMS beklenmeyen bir yanıt döndürdü; MAP_KEY ve sorgu ayarlarını kontrol edin."
        )

    points = []
    for source_row in reader:
        row = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in source_row.items()
        }
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
        except (KeyError, ValueError):
            continue
        brightness = row.get("bright_ti4") or row.get("brightness") or row.get("bright_ti5", "")
        points.append({
            "sensor": sensor,
            "latitude": str(latitude),
            "longitude": str(longitude),
            "brightness": brightness,
            "acq_date": row.get("acq_date", ""),
            "acq_time": row.get("acq_time", ""),
            "satellite": row.get("satellite", ""),
            "confidence": row.get("confidence", ""),
            "frp": row.get("frp", ""),
            "type": (row.get("type") or "0").split(".")[0],
        })
    return points


def fetch_source(map_key, source, sensor, bbox, start, end):
    chunks = list(date_chunks(start, end))
    points = []
    bbox_text = ",".join(str(value) for value in bbox)
    safe_key = quote(map_key, safe="")
    for index, (chunk_start, days) in enumerate(chunks, start=1):
        url = (
            f"{API_URL}/{safe_key}/{source}/{bbox_text}/{days}/"
            f"{chunk_start.isoformat()}"
        )
        try:
            with urlopen(url, timeout=120) as response:
                body = response.read()
        except HTTPError as error:
            raise RuntimeError(f"NASA FIRMS {source} isteği başarısız: HTTP {error.code}.") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError(f"NASA FIRMS {source} isteği ağ hatası nedeniyle başarısız.") from None
        chunk_points = parse_api_csv(body, sensor)
        points.extend(chunk_points)
        print(
            f"{source}: {index}/{len(chunks)} istek · {len(chunk_points)} satır",
            flush=True,
        )
    return points


def load_boundary(region):
    path = PROJECT_DIR / REGIONS[region]["boundary"]
    if not path.is_file():
        print(f"Uyarı: {path.name} bulunamadı; bölge sınırı filtresi uygulanmayacak.", flush=True)
        return None
    vertices = []
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            parts = line.replace(",", " ").split()
            if len(parts) < 2:
                continue
            vertices.append((float(parts[0]), float(parts[1])))
    except (OSError, ValueError):
        raise RuntimeError(f"{path.name} sınır dosyası okunamadı.") from None
    if len(vertices) < 10:
        print(f"Uyarı: {path.name} geçerli bir sınır içermiyor; bölge sınırı filtresi uygulanmayacak.", flush=True)
        return None
    return vertices


def point_in_polygon(latitude, longitude, vertices):
    inside = False
    previous = vertices[-1]
    for current in vertices:
        lat_a, lon_a = previous
        lat_b, lon_b = current
        if (lon_a > longitude) != (lon_b > longitude):
            crossing_lat = (
                (lat_b - lat_a) * (longitude - lon_a) / (lon_b - lon_a) + lat_a
            )
            if latitude < crossing_lat:
                inside = not inside
        previous = current
    return inside


def filter_points(points, region):
    vertices = load_boundary(region)
    if vertices is None:
        return points, False
    filtered = [
        point for point in points
        if point_in_polygon(float(point["latitude"]), float(point["longitude"]), vertices)
    ]
    if not filtered and points:
        return points, False
    if len(filtered) != len(points):
        print(f"Bölge sınırı filtresi: {len(points)} → {len(filtered)} nokta", flush=True)
    return filtered, True


def csv_row(point):
    return (
        point["sensor"], point["latitude"], point["longitude"], point["brightness"],
        point["acq_date"], point["acq_time"], point["satellite"],
        point["confidence"], point["frp"], point["type"],
    )


def atomic_write_points(path, points):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            writer = csv.writer(temporary)
            writer.writerow(POINT_HEADER)
            writer.writerows(csv_row(point) for point in points)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def aggregate_grid(points):
    cells = {}
    for point in points:
        latitude = float(point["latitude"])
        longitude = float(point["longitude"])
        grid_lat = math.floor(latitude * 10) / 10
        grid_lon = math.floor(longitude * 10) / 10
        key = f"{grid_lat:.1f}_{grid_lon:.1f}"
        counts = cells.setdefault(key, Counter())
        counts[point["sensor"].lower()] += 1
    return cells


def write_aggregate_files(base, points, start, end, region, mode, filtered):
    cells = aggregate_grid(points)
    modis_count = sum(counts.get("modis", 0) for counts in cells.values())
    viirs_count = sum(counts.get("viirs", 0) for counts in cells.values())
    grid_path = PROJECT_DIR / f"{base}.csv"
    with grid_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("grid", "modis", "viirs", "total", "viirs_per_modis"))
        for key, counts in sorted(
            cells.items(),
            key=lambda item: (-(item[1].get("modis", 0) + item[1].get("viirs", 0)), item[0]),
        ):
            modis = counts.get("modis", 0)
            viirs = counts.get("viirs", 0)
            writer.writerow((key, modis, viirs, modis + viirs, f"{viirs / modis if modis else 0:.2f}"))

    summary_path = PROJECT_DIR / f"{base}_summary.csv"
    summary = (
        ("dataset", "count"),
        ("MODIS", modis_count),
        ("VIIRS", viirs_count),
        ("VIIRS_per_MODIS", f"{viirs_count / modis_count if modis_count else 0:.2f}"),
        ("grid_cells", len(cells)),
        ("start_date", start.isoformat()),
        ("end_date", end.isoformat()),
        ("generated", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("mode", "NRT" if mode == "nrt" else "SP"),
        ("scope", REGIONS[region]["name"]),
        ("bbox", ",".join(str(value) for value in REGIONS[region]["bbox"])),
        ("geo_filter", int(filtered)),
        ("grid_deg", "0.1"),
    )
    with summary_path.open("w", encoding="utf-8", newline="") as output:
        csv.writer(output).writerows(summary)
    return modis_count, viirs_count


def make_operation_files(base, points, start, end, region, mode, filtered):
    grid_base = f"{base}_grid" if mode == "archive" else base
    point_path = PROJECT_DIR / f"{base}_points.csv"
    atomic_write_points(point_path, points)
    counts = write_aggregate_files(
        grid_base, points, start, end, region, mode, filtered
    )
    return point_path, counts


def make_output_base(config, region):
    if config["kind"] == "archive":
        return f"webarchive_{config['operationId'][:8]}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{REGIONS[region]['slug']}_{timestamp}"


def collect_once(config, region, start, end):
    points = []
    suffix = "NRT" if config["kind"] == "nrt" else "SP"
    for source_prefix, sensor in SOURCES:
        source = f"{source_prefix}_{suffix}"
        points.extend(fetch_source(
            config["mapKey"], source, sensor, REGIONS[region]["bbox"], start, end
        ))
    points, filtered = filter_points(points, region)
    return points, filtered


def run_archive(config, region, start, end):
    points, filtered = collect_once(config, region, start, end)
    if not points:
        print("Sorgu tamamlandı; bölgede eşleşen veri bulunamadı.", flush=True)
        return
    base = make_output_base(config, region)
    point_path, (modis_count, viirs_count) = make_operation_files(
        base, points, start, end, region, "archive", filtered
    )
    print(f"M={modis_count} V={viirs_count}", flush=True)
    print(f"{base}_grid.csv  {base}_grid.jpg  {point_path.name}", flush=True)


def digest_points(points):
    digest = hashlib.sha256()
    for point in points:
        digest.update(json.dumps(point, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def run_nrt(config, region, start, end):
    live_file = PROJECT_DIR / "data" / "nrt_live_points.csv"
    last_digest = None
    turn = 0
    poll_seconds = int(config.get("pollSeconds", 120))
    while True:
        turn += 1
        started = datetime.now()
        current_start = date.today() - timedelta(days=1)
        current_end = date.today()
        points, filtered = collect_once(config, region, current_start, current_end)
        current_digest = digest_points(points)
        atomic_write_points(live_file, points)

        if current_digest == last_digest:
            print(
                f"[{started:%H:%M:%S}] #{turn} · {REGIONS[region]['name']} · değişiklik yok",
                flush=True,
            )
        elif not points:
            print(f"[{started:%H:%M:%S}] #{turn} · {REGIONS[region]['name']} · veri boş", flush=True)
        else:
            base = make_output_base(config, region)
            point_path, (modis_count, viirs_count) = make_operation_files(
                base, points, current_start, current_end, region, "nrt", filtered
            )
            print(
                f"[{started:%H:%M:%S}] #{turn} · {REGIONS[region]['name']} · "
                f"YENİ — M={modis_count} V={viirs_count}",
                flush=True,
            )
            print(f"{base}.csv  {base}.jpg  {point_path.name}", flush=True)
        last_digest = current_digest
        time.sleep(poll_seconds)


def read_config():
    line = sys.stdin.readline()
    if not line:
        raise ValueError("Sorgu ayarları alınamadı.")
    try:
        config = json.loads(line)
    except json.JSONDecodeError:
        raise ValueError("Sorgu ayarları geçerli JSON olmalı.") from None
    if not isinstance(config, dict):
        raise ValueError("Sorgu ayarları JSON nesnesi olmalı.")
    if config.get("kind") not in ("nrt", "archive"):
        raise ValueError("Sorgu türü NRT veya Archive olmalı.")
    if config.get("region") not in REGIONS:
        raise ValueError("Türkiye, Hatay veya İskenderun bölgesi seçin.")
    map_key = config.get("mapKey")
    if not isinstance(map_key, str) or not 8 <= len(map_key.strip()) <= 256:
        raise ValueError("Geçerli bir NASA FIRMS MAP_KEY girin.")
    if any(ord(char) < 32 or ord(char) == 127 for char in map_key):
        raise ValueError("MAP_KEY tek satır olmalı.")
    config["mapKey"] = map_key.strip()
    if config["kind"] == "nrt":
        try:
            poll = int(config.get("pollSeconds", 120))
        except (TypeError, ValueError):
            raise ValueError("Geçerli bir NRT sorgu aralığı seçin.") from None
        if poll not in (60, 120, 300, 1800, 3600):
            raise ValueError("Geçerli bir NRT sorgu aralığı seçin.")
        config["pollSeconds"] = poll
    elif not config.get("operationId"):
        raise ValueError("Archive sorgusu için işlem kimliği gerekli.")
    return config


def main():
    try:
        config = read_config()
        region = config["region"]
        start, end = get_date_range(config)
        if config["kind"] == "nrt":
            run_nrt(config, region, start, end)
        else:
            run_archive(config, region, start, end)
    except KeyboardInterrupt:
        print("\nSorgu durduruldu.", flush=True)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Hata: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
