"""Shared helpers: FIRMS area API (same call that works in the local tool) + Türkiye boundary filter."""
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BBOX = "25.60,35.80,44.80,42.10"
_poly = None


def api_fetch(source, days, start=None, timeout=60, tries=2):
    key = os.environ.get("MAP_KEY", "").strip()
    if not key:
        raise SystemExit("MAP_KEY is missing")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{BBOX}/{days}"
    if start:
        url += f"/{start}"
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                text = r.read().decode("utf-8")
            if text.lstrip().lower().startswith("latitude"):
                return text
            print(f"{source} {start or ''}: unexpected answer {text[:120]!r}", flush=True)
            return ""
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:150]
            except Exception:
                pass
            print(f"{source} {start or ''}: HTTP {e.code} {body!r}", flush=True)
        except Exception as e:
            print(f"{source} {start or ''}: attempt {attempt + 1} failed: {type(e).__name__} {e}", flush=True)
        time.sleep(3)
    return None


def _load():
    """Boundary file = 'lon lat' per line; several closed rings (mainland + islands), each ends where it started."""
    global _poly
    if _poly is None:
        _poly = []
        p = ROOT / "data" / "turkiye_sinir.txt"
        pts = []
        if p.exists():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                a = line.replace(",", " ").split()
                if len(a) >= 2:
                    pts.append((float(a[1]), float(a[0])))  # (lat, lon)
        ring = []
        for q in pts:
            ring.append(q)
            if len(ring) > 3 and q == ring[0]:
                _poly.append(ring)
                ring = []
        if len(ring) > 3:
            _poly.append(ring)
        _poly = [(min(x[0] for x in r), max(x[0] for x in r), min(x[1] for x in r), max(x[1] for x in r), r) for r in _poly]
    return _poly


def in_turkey(lat, lon):
    rings = _load()
    if not rings:
        return True
    for la0, la1, lo0, lo1, v in rings:
        if lat < la0 or lat > la1 or lon < lo0 or lon > lo1:
            continue
        inside, prev = False, v[-1]
        for cur in v:
            la, oa = prev
            lb, ob = cur
            if (oa > lon) != (ob > lon) and lat < (lb - la) * (lon - oa) / (ob - oa) + la:
                inside = not inside
            prev = cur
        if inside:
            return True
    return False
