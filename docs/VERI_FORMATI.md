# AeroFire veri formatı

Akış: `scripts/` (Akay) → `data/processed/hatay_points.csv` → `harmonize/harmonize.py` → `web/data/points.json` → `web/app.js` (Ceyhun)

## 1. Girdi: `data/processed/hatay_points.csv`

| Sütun | Açıklama |
|---|---|
| `Sensor` | `MODIS` veya `VIIRS` (boşsa uydu adından tahmin edilir: Terra/Aqua = MODIS) |
| `Latitude`, `Longitude` | Derece (WGS84) |
| `Brightness_K` | Parlaklık sıcaklığı, Kelvin (MODIS kanal 21/22, VIIRS I4). İki sensörde farklı kanal, doğrudan karşılaştırılmaz |
| `Acq_Date` | `YYYY-MM-DD`, UTC |
| `Acq_Time` | `HHMM`, UTC (`750` gibi gelirse `0750` yapılır) |
| `Satellite` | MODIS: `Terra` / `Aqua`; VIIRS: `N` (Suomi NPP), `1` (NOAA-20) |
| `Confidence` | MODIS: 0–100 sayı; VIIRS: `l` / `n` / `h` |
| `FRP` | Yangın ışınım gücü, MW |
| `Type` | 0 bitki yangını, 1 volkan, 2 sabit ısı kaynağı, 3 deniz |

Sütun adları büyük/küçük harf duyarsızdır. `lat`, `lon`, `bright_ti4`, `instrument` gibi FIRMS adları da tanınır.

## 2. Çıktı: `web/data/points.json`

```json
{
  "meta":   { ... },
  "fires":  [ ... ],
  "grid":   [ ... ],
  "points": [ ... ]
}
```

### `meta`

| Alan | Açıklama |
|---|---|
| `region` | `"Hatay"` |
| `date_from`, `date_to` | İlk ve son tarih |
| `dates` | Verideki tüm tarihler, sıralı (haritadaki tarih düğmeleri) |
| `generated` | Çalıştırma zamanı (UTC). Slayttaki sayılar Cumartesi 16:00 çalıştırmasından gelmeli |
| `rules` | Kullanılan kurallar, metin olarak |
| `counts` | Aşağıdaki sayılar |

`meta.counts` (sadece bitki yangını noktaları, `category = "vegetation"`):

| Alan | Açıklama |
|---|---|
| `modis`, `viirs` | Ham nokta sayısı |
| `fires` | Yangın grubu sayısı |
| `matched` | Hem MODIS hem VIIRS içeren grup sayısı |
| `excluded_static`, `excluded_offshore` | Ayıklanan type 2 / type 3 nokta sayısı |
| `grid_modis` | MODIS'in yanan gördüğü kare-gün sayısı (`both` dahil) |
| `grid_viirs` | VIIRS'in yanan gördüğü kare-gün sayısı (`both` dahil) |
| `grid_both` | İki sensörün de aynı gün gördüğü kare sayısı |
| `raw_ratio` | `viirs / modis` (ham nokta oranı) |
| `grid_ratio` | `grid_viirs / grid_modis` (ızgara oranı) |

### `points[]`: her algılama bir satır

| Alan | Örnek | Açıklama |
|---|---|---|
| `id` | `"M-000001"` | Sensör harfi + sıra no |
| `sensor` | `"MODIS"` | |
| `satellite` | `"Terra"` | |
| `lat`, `lon` | `36.5326` | 5 basamak |
| `date`, `time` | `"2020-10-09"`, `"0750"` | UTC |
| `confidence_raw` | `"95"` / `"h"` | CSV'deki değer |
| `confidence_level` | `"high"` | Ortak ölçek: `low` / `nominal` / `high` / `unknown` |
| `brightness` | `349.7` | K |
| `frp` | `273.8` | MW |
| `category` | `"vegetation"` | `vegetation` / `static` / `offshore` / `volcano` / `unknown` |
| `fire_id` | `"F-0001"` | Yangın grubu. Bitki yangını değilse `null` |
| `match_id` | `"F-0001"` | Grup iki sensörde de görüldüyse `fire_id`, yoksa `null` |

Ortak güven ölçeği: MODIS 0–29 low, 30–79 nominal, 80–100 high (MODIS C6 kullanıcı kılavuzu). VIIRS l/n/h → low/nominal/high.

Aynı yangın kuralı: aynı UTC günü ve ≤ 1,5 km (`--km`), zincirleme (A–B yakın, B–C yakın ise A, B, C aynı grup).

### `grid[]`: ortak ızgara, her kare-gün bir satır

Sadece en az bir bitki yangını noktası olan kareler yazılır.

| Alan | Örnek | Açıklama |
|---|---|---|
| `date` | `"2020-10-09"` | UTC günü |
| `south`, `west`, `north`, `east` | `36.5129` | Kare köşeleri (derece) |
| `seen_by` | `"both"` | `MODIS` / `VIIRS` / `both` |
| `modis_points`, `viirs_points` | `3`, `12` | Karedeki ham nokta sayısı |
| `fire_ids` | `["F-0001"]` | Karedeki yangın grupları |

Izgara kuralı: kare kenarı `--grid-km` (varsayılan 1,0 km). Başlangıç noktası sabit, Hatay bbox'ının güney-batı köşesi (35.80N, 35.75E). Enlem adımı `km / 111,32`, boylam adımı `km / (111,32 × cos 36,40°)`. Kare, o gün içinde en az bir noktası varsa o sensör için "yanan" sayılır.

### `fires[]`: yangın grubu özeti

| Alan | Açıklama |
|---|---|
| `fire_id`, `date` | |
| `lat`, `lon` | Grup noktalarının ortalaması (merkez) |
| `modis`, `viirs` | Ham nokta sayısı |
| `matched` | İki sensörde de görüldü mü |
| `grid_modis`, `grid_viirs`, `grid_both` | Grubun ızgara kare sayıları |
| `frp_max` | Gruptaki en yüksek FRP (MW) |

## 3. Harita renkleri

| Katman | Renk |
|---|---|
| MODIS | `#F26B1D` (turuncu) |
| VIIRS | `#5B8DEF` (mavi) |
| İki sensörde eşleşen yangın | `#FFB020` (sarı halka; iç renk sensörü gösterir) |
| Sabit ısı kaynağı / deniz | gri `#8a8f98`, "yangın değil" |
| Izgara karesi | sadece MODIS turuncu, sadece VIIRS mavi, ikisi sarı |

## 4. Bilinen sınırlamalar

- "Aynı gün" UTC'ye göre. 9 Ekim 23:08 ile 10 Ekim 08:33 algılamaları aynı yangın olsa da iki ayrı grup olur (Belen: F-0001 ve F-0005).
- FIRMS, Belen içindeki 4 MODIS noktasını type 2 (sabit kaynak) olarak işaretlemiş. Kurala uyup bunları ayıkladık.
- Izgara sayıları karelerin başlangıç noktasına biraz bağlıdır. Kareler kaydırılırsa birkaç kare değişebilir.
- VIIRS parlaklığı yaklaşık 367 K'de doyuma ulaşır. Bu değerdeki noktaların gerçek sıcaklığı daha yüksektir.
