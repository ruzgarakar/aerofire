"""AeroFire - MODIS ve VIIRS uyumlaştırma.

Girdi : data/processed/hatay_points.csv  (Akay'ın scripti)
Çıktı : web/data/points.json             (Ceyhun'un haritası)
Format: docs/VERI_FORMATI.md

Çalıştırma: python harmonize/harmonize.py
            python harmonize/harmonize.py --input baska.csv --km 1.5 --grid-km 1.0

Sadece Python standart kütüphanesi kullanılır.

Kurallar:
1. Ortak güven ölçeği (low / nominal / high)
   - MODIS 0-100 sayısı: 0-29 low, 30-79 nominal, 80-100 high
     (MODIS Collection 6 aktif yangın kullanıcı kılavuzundaki sınıflar)
   - VIIRS: l -> low, n -> nominal, h -> high
2. Aynı yangın: aynı gün (UTC) ve aralarında MATCH_KM km'den az mesafe olan
   noktalar zincir halinde birleşir ve aynı fire_id'yi alır.
   Bir grupta hem MODIS hem VIIRS varsa o yangın "iki sensörde de eşleşti" sayılır
   (match_id = fire_id).
3. Ortak ızgara: MODIS pikseli ~1 km, VIIRS pikseli ~375 m. Aynı yangın VIIRS'te
   daha çok noktayla görünür. Bu yüzden iki sensörü aynı ~1 km'lik karelere
   oturtup her gün için "bu kare yandı mı, hangi sensör gördü" diye sayıyoruz.
   Bir karede o gün en az bir bitki yangını noktası varsa kare o sensör için "yanan" sayılır.
"""

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT / "data" / "processed" / "hatay_points.csv"
OUTPUT_JSON = ROOT / "web" / "data" / "points.json"
MATCH_KM = 1.5
GRID_KM = 1.0

GRID_ORIGIN_LAT = 35.80
GRID_ORIGIN_LON = 35.75
GRID_REF_LAT = 36.40
KM_PER_DEG_LAT = 111.32

COLUMN_ALIASES = {
    "sensor": "sensor", "instrument": "sensor",
    "satellite": "satellite",
    "latitude": "latitude", "lat": "latitude",
    "longitude": "longitude", "lon": "longitude", "lng": "longitude",
    "acq_date": "acq_date", "date": "acq_date",
    "acq_time": "acq_time", "time": "acq_time",
    "confidence": "confidence",
    "brightness": "brightness", "brightness_k": "brightness", "bright_ti4": "brightness",
    "frp": "frp",
    "type": "type",
}

TYPE_NAMES = {"0": "vegetation", "1": "volcano", "2": "static", "3": "offshore"}


def guess_sensor(p):
    """Sensor sütunu boşsa uydu adından tahmin eder (Terra/Aqua = MODIS, diğerleri VIIRS)."""
    sensor = p.get("sensor", "").upper()
    if sensor:
        return sensor
    sat = p.get("satellite", "").strip().lower()
    if sat in ("terra", "aqua", "t", "a"):
        return "MODIS"
    if sat:
        return "VIIRS"
    return "UNKNOWN"


def load_points(path):
    """CSV'yi okur, sütun adlarını düzeltir, her satırı bir sözlük olarak döndürür."""
    points = []
    skipped = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            p = {}
            for key, value in row.items():
                if key is None:
                    continue
                name = COLUMN_ALIASES.get(key.strip().lower())
                if name:
                    p[name] = (value or "").strip()
            try:
                p["latitude"] = float(p["latitude"])
                p["longitude"] = float(p["longitude"])
                for num in ("brightness", "frp"):
                    p[num] = float(p[num]) if p.get(num) else None
            except (KeyError, ValueError):
                skipped += 1
                continue
            p["sensor"] = guess_sensor(p)
            p["acq_time"] = p.get("acq_time", "").zfill(4)
            raw_type = p.get("type", "0") or "0"
            raw_type = raw_type.split(".")[0]
            p["category"] = TYPE_NAMES.get(raw_type, "unknown")
            points.append(p)
    if skipped:
        print(f"Uyarı: {skipped} bozuk satır atlandı.")
    return points


def normalize_confidence(point):
    """MODIS 0-100 ve VIIRS l/n/h değerini ortak low/nominal/high ölçeğine çevirir."""
    raw = str(point.get("confidence", "")).strip().lower()
    if point["sensor"] == "VIIRS":
        return {"l": "low", "n": "nominal", "h": "high",
                "low": "low", "nominal": "nominal", "high": "high"}.get(raw, "unknown")
    try:
        value = float(raw)
    except ValueError:
        return "unknown"
    if value < 30:
        return "low"
    if value < 80:
        return "nominal"
    return "high"


def distance_km(a, b):
    """İki nokta arasındaki mesafe (haversine), km."""
    r = 6371.0
    lat1, lon1 = math.radians(a["latitude"]), math.radians(a["longitude"])
    lat2, lon2 = math.radians(b["latitude"]), math.radians(b["longitude"])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def match_fires(all_points, max_km=MATCH_KM):
    """Aynı gün ve max_km içindeki noktaları zincir halinde gruplar, fire_id verir.

    Sadece bitki örtüsü yangınları (type 0) eşleştirilir; sabit ısı kaynakları
    (fabrika vb., type 2) ve denizdeki kaynaklar (type 3) yangın sayılmaz.
    Dönen değer: (grup sayısı, iki sensörde de görülen grup sayısı)
    """
    for p in all_points:
        p["fire_id"] = None
        p["match_id"] = None
    points = [p for p in all_points if p["category"] == "vegetation"]
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    by_date = {}
    for i, p in enumerate(points):
        by_date.setdefault(p.get("acq_date", ""), []).append(i)

    for idxs in by_date.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if distance_km(points[i], points[j]) <= max_km:
                    union(i, j)

    groups = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)

    fire_no = 0
    both = 0
    for members in sorted(groups.values(), key=lambda m: min(m)):
        fire_no += 1
        fire_id = f"F-{fire_no:04d}"
        sensors = {points[i]["sensor"] for i in members}
        in_both = "MODIS" in sensors and "VIIRS" in sensors
        if in_both:
            both += 1
        for i in members:
            points[i]["fire_id"] = fire_id
            points[i]["match_id"] = fire_id if in_both else None
    return fire_no, both


def build_grid(points, grid_km=GRID_KM):
    """Bitki yangını noktalarını gün bazında ~grid_km'lik karelere yerleştirir.

    Her kare için: tarih, köşe koordinatları, hangi sensör(ler) görmüş,
    karede kaç MODIS / VIIRS noktası var ve hangi yangın grubuna ait.
    """
    lat_step = grid_km / KM_PER_DEG_LAT
    lon_step = grid_km / (KM_PER_DEG_LAT * math.cos(math.radians(GRID_REF_LAT)))

    cells = {}
    for p in points:
        if p["category"] != "vegetation":
            continue
        row = math.floor((p["latitude"] - GRID_ORIGIN_LAT) / lat_step)
        col = math.floor((p["longitude"] - GRID_ORIGIN_LON) / lon_step)
        key = (p.get("acq_date", ""), row, col)
        cell = cells.setdefault(key, {"count": Counter(), "fires": set()})
        cell["count"][p["sensor"]] += 1
        cell["fires"].add(p["fire_id"])

    grid = []
    for (date, row, col), cell in sorted(cells.items()):
        modis = cell["count"].get("MODIS", 0)
        viirs = cell["count"].get("VIIRS", 0)
        if modis and viirs:
            seen_by = "both"
        elif modis:
            seen_by = "MODIS"
        else:
            seen_by = "VIIRS"
        south = GRID_ORIGIN_LAT + row * lat_step
        west = GRID_ORIGIN_LON + col * lon_step
        grid.append({
            "date": date,
            "south": round(south, 5),
            "west": round(west, 5),
            "north": round(south + lat_step, 5),
            "east": round(west + lon_step, 5),
            "seen_by": seen_by,
            "modis_points": modis,
            "viirs_points": viirs,
            "fire_ids": sorted(f for f in cell["fires"] if f),
        })
    return grid


def ratio(a, b):
    """a / b, iki basamak. b sıfırsa None (JSON'da null)."""
    return round(a / b, 2) if b else None


def grid_counts(grid):
    """Izgaradan sayıları çıkarır. 'both' kareler hem MODIS'e hem VIIRS'e sayılır."""
    modis = sum(1 for c in grid if c["seen_by"] in ("MODIS", "both"))
    viirs = sum(1 for c in grid if c["seen_by"] in ("VIIRS", "both"))
    both = sum(1 for c in grid if c["seen_by"] == "both")
    return modis, viirs, both


def summarize_fires(points, grid):
    """Her yangın grubu için kısa özet: tarih, merkez, ham nokta ve ızgara sayıları."""
    fires = {}
    for p in points:
        if not p["fire_id"]:
            continue
        f = fires.setdefault(p["fire_id"], {"date": p.get("acq_date", ""), "lats": [], "lons": [],
                                            "count": Counter(), "frp_max": None})
        f["lats"].append(p["latitude"])
        f["lons"].append(p["longitude"])
        f["count"][p["sensor"]] += 1
        if p.get("frp") is not None and (f["frp_max"] is None or p["frp"] > f["frp_max"]):
            f["frp_max"] = p["frp"]

    out = []
    for fire_id in sorted(fires):
        f = fires[fire_id]
        cells = [c for c in grid if fire_id in c["fire_ids"]]
        g_modis, g_viirs, g_both = grid_counts(cells)
        modis = f["count"].get("MODIS", 0)
        viirs = f["count"].get("VIIRS", 0)
        out.append({
            "fire_id": fire_id,
            "date": f["date"],
            "lat": round(sum(f["lats"]) / len(f["lats"]), 5),
            "lon": round(sum(f["lons"]) / len(f["lons"]), 5),
            "modis": modis,
            "viirs": viirs,
            "matched": modis > 0 and viirs > 0,
            "grid_modis": g_modis,
            "grid_viirs": g_viirs,
            "grid_both": g_both,
            "frp_max": f["frp_max"],
        })
    return out


def build_output(points, grid, fires, meta_extra):
    """docs/VERI_FORMATI.md'deki points.json yapısını oluşturur."""
    counts = Counter(p["sensor"] for p in points if p["category"] == "vegetation")
    excluded = Counter(p["category"] for p in points if p["category"] != "vegetation")
    dates = sorted(p["acq_date"] for p in points if p.get("acq_date"))
    g_modis, g_viirs, g_both = grid_counts(grid)
    out_points = []
    for n, p in enumerate(points, start=1):
        prefix = p["sensor"][:1] if p["sensor"] != "UNKNOWN" else "X"
        out_points.append({
            "id": f"{prefix}-{n:06d}",
            "sensor": p["sensor"],
            "satellite": p.get("satellite", ""),
            "lat": round(p["latitude"], 5),
            "lon": round(p["longitude"], 5),
            "date": p.get("acq_date", ""),
            "time": p.get("acq_time", ""),
            "confidence_raw": p.get("confidence", ""),
            "confidence_level": p["confidence_level"],
            "brightness": p.get("brightness"),
            "frp": p.get("frp"),
            "category": p["category"],
            "fire_id": p["fire_id"],
            "match_id": p["match_id"],
        })
    return {
        "meta": {
            "region": "Hatay",
            "date_from": dates[0] if dates else None,
            "date_to": dates[-1] if dates else None,
            "dates": sorted(set(dates)),
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rules": {
                "modis_confidence": "0-29 low, 30-79 nominal, 80-100 high",
                "viirs_confidence": "l low, n nominal, h high",
                "same_fire": f"same UTC date and within {meta_extra['km']} km (chained)",
                "excluded": "FIRMS type 2 (static land source) and 3 (offshore) are not counted as wildfires",
                "grid": (f"{meta_extra['grid_km']} km squares per UTC date, origin "
                         f"{GRID_ORIGIN_LAT}N {GRID_ORIGIN_LON}E; a square counts for a sensor "
                         "if it has at least one vegetation fire point"),
            },
            "counts": {
                "modis": counts.get("MODIS", 0),
                "viirs": counts.get("VIIRS", 0),
                "fires": meta_extra["fires"],
                "matched": meta_extra["matched"],
                "excluded_static": excluded.get("static", 0),
                "excluded_offshore": excluded.get("offshore", 0),
                "grid_modis": g_modis,
                "grid_viirs": g_viirs,
                "grid_both": g_both,
                "raw_ratio": ratio(counts.get("VIIRS", 0), counts.get("MODIS", 0)),
                "grid_ratio": ratio(g_viirs, g_modis),
            },
        },
        "fires": fires,
        "grid": grid,
        "points": out_points,
    }


def main():
    parser = argparse.ArgumentParser(description="AeroFire MODIS-VIIRS uyumlaştırma")
    parser.add_argument("--input", default=str(INPUT_CSV))
    parser.add_argument("--output", default=str(OUTPUT_JSON))
    parser.add_argument("--km", type=float, default=MATCH_KM,
                        help="aynı yangın sayılacak en büyük mesafe (km)")
    parser.add_argument("--grid-km", type=float, default=GRID_KM,
                        help="ortak ızgara karesinin kenarı (km)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    points = load_points(args.input)
    if not points:
        raise SystemExit(f"Hiç nokta okunamadı: {args.input}")
    for p in points:
        p["confidence_level"] = normalize_confidence(p)
    fires, matched = match_fires(points, args.km)
    grid = build_grid(points, args.grid_km)
    fire_summary = summarize_fires(points, grid)
    output = build_output(points, grid, fire_summary, {
        "km": args.km, "grid_km": args.grid_km, "fires": fires, "matched": matched})

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    c = output["meta"]["counts"]
    levels = Counter((p["sensor"], p["confidence_level"]) for p in points if p["category"] == "vegetation")
    print(f"Orman/bitki yangını noktası -> MODIS: {c['modis']} | VIIRS: {c['viirs']}")
    print(f"Ayıklanan: sabit ısı kaynağı {c['excluded_static']}, deniz {c['excluded_offshore']}")
    print(f"Yangın grubu: {c['fires']} | İki sensörde de görülen: {c['matched']}")
    for sensor in ("MODIS", "VIIRS"):
        print(f"  {sensor} güven: " + ", ".join(
            f"{lvl}={levels.get((sensor, lvl), 0)}" for lvl in ("low", "nominal", "high", "unknown")))
    print(f"Ortak {args.grid_km} km ızgara (gün bazında yanan kare) -> "
          f"MODIS: {c['grid_modis']} | VIIRS: {c['grid_viirs']} | ikisi de: {c['grid_both']}")
    print(f"Oran (VIIRS/MODIS) -> ham nokta: {c['raw_ratio']}x | ızgara: {c['grid_ratio']}x")
    if fire_summary:
        big = max(fire_summary, key=lambda f: f["modis"] + f["viirs"])
        print(f"En büyük grup {big['fire_id']} ({big['date']}): ham MODIS {big['modis']}, "
              f"VIIRS {big['viirs']} | ızgara MODIS {big['grid_modis']}, VIIRS {big['grid_viirs']}")
    print(f"Yazıldı: {out}")


if __name__ == "__main__":
    main()
