# AeroFire — Nokta Verisi Format Sözleşmesi

Bu belge, yangın analiz pipeline'ının giriş katmanında üretilen ham nokta CSV dosyasının yapısını tanımlar. Sonraki tüm katmanlar bu dosyayı tek doğruluk kaynağı olarak kullanır.

Akış: `scripts/` → `data/processed/hatay_points.csv` → `harmonize/harmonize.py` → `web/data/points.json` → `web/app.js`

---

## 1. Girdi: `data/processed/hatay_points.csv`

### 1.1. Dosya Özellikleri

| Özellik | Değer |
|---|---|
| Ad | `hatay_points.csv` |
| Karakter kodlaması | UTF-8 (BOM'suz) |
| Satır sonu | `\n` (LF) |
| Alan ayırıcı | `,` (virgül) |
| Ondalık ayırıcı | `.` (nokta) |
| Başlık satırı | Zorunlu — 1. satır her zaman sütun adlarıdır |
| Locale | `LC_ALL=C` ile üretilmelidir (Türkçe locale'de ondalık virgüle dönüşmez) |

### 1.2. Sütun Şeması

Başlık satırı birebir şu olmalıdır (büyük/küçük harf duyarlı, boşluk yok):

```
Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type
```

| # | Sütun | Tip | Birim | Açıklama |
|---|---|---|---|---|
| 1 | `Sensor` | string | — | `MODIS` veya `VIIRS`. Boşsa uydu adından tahmin edilir (Terra/Aqua = MODIS) |
| 2 | `Latitude` | float | derece | WGS84. `-90 ≤ x ≤ 90`. 4-5 ondalık |
| 3 | `Longitude` | float | derece | WGS84. `-180 ≤ x ≤ 180`. 4-5 ondalık |
| 4 | `Brightness_K` | float | Kelvin | MODIS: kanal 21/22, VIIRS: I4. İki sensörde farklı kanal — doğrudan karşılaştırılamaz |
| 5 | `Acq_Date` | string | — | `YYYY-MM-DD`, UTC |
| 6 | `Acq_Time` | string | — | `HHMM` (24sa, UTC). `750` gibi gelirse `0750`'ye sıfırla doldur |
| 7 | `Satellite` | string | — | MODIS: `Terra` / `Aqua`; VIIRS: `N` (Suomi NPP), `1` (NOAA-20) |
| 8 | `Confidence` | string | — | MODIS: `0-100` sayı; VIIRS: `l` / `n` / `h` |
| 9 | `FRP` | float | MW | Yangın ışınım gücü. Boş olabilir |
| 10 | `Type` | integer | — | `0` bitki yangını, `1` volkan, `2` sabit ısı kaynağı, `3` deniz |

Sütun adları büyük/küçük harf duyarsızdır. `lat`, `lon`, `bright_ti4`, `instrument` gibi FIRMS ham adları da harmonize katmanında tanınır; ancak bu sözleşme kanonik adları zorunlu kılar.

### 1.3. Tip → Kategori Eşlemesi

Harmonize katmanı, `Type` sütununu aşağıdaki kurala göre `category` alanına çevirir:

| `Type` | `category` | Pipeline'da işlem |
|---|---|---|
| `0` | `vegetation` | Ana veri — tüm sayımlar bu kategoriye girer |
| `1` | `volcano` | Analiz dışı, `points[]`'a yazılır |
| `2` | `static` | Ayıklanır — `meta.counts.excluded_static` sayacına eklenir |
| `3` | `offshore` | Ayıklanır — `meta.counts.excluded_offshore` sayacına eklenir |
| boş / tanımsız | `unknown` | Analiz dışı |

Kritik kural: Sadece `category = "vegetation"` satırlar `meta.counts.modis`, `meta.counts.viirs`, `grid[]` ve `fires[]` sayımlarına dahil edilir. Diğer kategoriler `points[]` dizisinde görünür (harita gri gösterebilsin diye), ancak sayımlara girmez.

### 1.4. Veri Bütünlüğü Doğrulama Komutları

Script çıktıyı yazdıktan sonra aşağıdaki komutlarla doğrulanabilir:

```bash
# 1. Her satırda 10 sütun olmalı
awk -F',' '{print NF}' hatay_points.csv | sort -u
# Beklenen tek değer: 10

# 2. Başlık satırı birebir doğru mu?
head -1 hatay_points.csv
# Beklenen: Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type

# 3. Sensör değerleri sadece MODIS/VIIRS mi?
awk -F',' 'NR>1 {print $1}' hatay_points.csv | sort -u
# Beklenen: MODIS, VIIRS

# 4. Type sütunu sadece 0/1/2/3 mü?
awk -F',' 'NR>1 {print $10}' hatay_points.csv | sort -u
# Beklenen: 0, 1, 2, 3 (kullanılanlar)

# 5. Tarih formatı YYYY-MM-DD mi?
awk -F',' 'NR>1 && $5 !~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/ {print NR": "$5}' hatay_points.csv
# Beklenen: hiçbir satır dönmemeli

# 6. Saat 4 karakter mi?
awk -F',' 'NR>1 && length($6)!=4 {print NR": "$6}' hatay_points.csv
# Beklenen: hiçbir satır dönmemeli

# 7. Koordinatlar Türkiye bbox'ı içinde mi?
awk -F',' 'NR>1 && ($2<35.7 || $2>42.2 || $3<25.5 || $3>44.9) {print NR}' hatay_points.csv
# Beklenen: hiçbir satır dönmemeli
```

### 1.5. Örnek Satırlar

```csv
Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type
MODIS,36.5326,36.1739,321.1,2020-10-08,0750,Terra,59,12.3,0
MODIS,36.6094,36.1886,340.5,2020-10-08,0750,Aqua,75,45.2,2
MODIS,36.5912,36.1647,335.8,2020-10-09,1023,Terra,88,27.6,0
VIIRS,36.5326,36.1739,337.01,2020-10-08,1055,N,l,5.89,0
VIIRS,36.6153,36.1806,335.5,2020-10-08,1055,1,n,8.4,2
VIIRS,36.5901,36.1742,367.0,2020-10-09,1310,N,h,142.7,0
```

---

## 2. Çıktı: `web/data/points.json`

```json
{
  "meta":   { ... },
  "fires":  [ ... ],
  "grid":   [ ... ],
  "points": [ ... ]
}
```

### 2.1. `meta`

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

### 2.2. `points[]` — Her Algılama Bir Satır

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

Ortak güven ölçeği:

- MODIS 0–29 `low`, 30–79 `nominal`, 80–100 `high` (MODIS C6 kullanıcı kılavuzu)
- VIIRS `l` / `n` / `h` → `low` / `nominal` / `high`

Aynı yangın kuralı:

- Aynı UTC günü ve ≤ 1,5 km (`--km`) ve zincirleme (A–B yakın, B–C yakın ise A, B, C aynı grup)
- Sadece `category = "vegetation"` noktalar gruplanır
- Grup iki sensörde de görüldüyse `match_id = fire_id`, aksi halde `null`

### 2.3. `grid[]` — Ortak Izgara

Sadece en az bir bitki yangını noktası olan kareler yazılır. Her kare-gün bir satırdır.

| Alan | Örnek | Açıklama |
|---|---|---|
| `date` | `"2020-10-09"` | UTC günü |
| `south`, `west`, `north`, `east` | `36.5129` | Kare köşeleri (derece) |
| `seen_by` | `"both"` | `MODIS` / `VIIRS` / `both` |
| `modis_points`, `viirs_points` | `3`, `12` | Karedeki ham nokta sayısı |
| `fire_ids` | `["F-0001"]` | Karedeki yangın grupları |

Izgara kuralı:

- Kare kenarı: `--grid-km` (varsayılan 1,0 km)
- Başlangıç noktası (sabit): Hatay bbox'ının GB köşesi 35.80N, 35.75E
- Enlem adımı: `km / 111.32`
- Boylam adımı: `km / (111.32 × cos 36.40°)`
- Kare, o gün içinde en az bir noktası varsa o sensör için "yanan" sayılır

### 2.4. `fires[]` — Yangın Grubu Özeti

| Alan | Açıklama |
|---|---|
| `fire_id`, `date` | |
| `lat`, `lon` | Grup noktalarının ortalaması (merkez) |
| `modis`, `viirs` | Ham nokta sayısı |
| `matched` | İki sensörde de görüldü mü |
| `grid_modis`, `grid_viirs`, `grid_both` | Grubun ızgara kare sayıları |
| `frp_max` | Gruptaki en yüksek FRP (MW) |

---

## 3. Harita Renkleri

| Katman | Renk |
|---|---|
| MODIS | `#F26B1D` (turuncu) |
| VIIRS | `#5B8DEF` (mavi) |
| İki sensörde eşleşen yangın | `#FFB020` (sarı halka; iç renk sensörü gösterir) |
| Sabit ısı kaynağı / deniz | gri `#8a8f98`, "yangın değil" |
| Izgara karesi | sadece MODIS turuncu, sadece VIIRS mavi, ikisi sarı |

---

## 4. Bilinen Sınırlamalar

| # | Sınırlama | Etki |
|---|---|---|
| 1 | "Aynı gün" UTC'ye göre. 9 Ekim 23:08 ile 10 Ekim 08:33 algılamaları aynı fiziksel yangın olsa da iki ayrı grup olur | Belen: F-0001 ve F-0005 ayrı görünür |
| 2 | FIRMS, Belen içindeki 4 MODIS noktasını `type=2` (sabit kaynak) olarak işaretlemiş | Kurala uyup bunları ayıkladık; ancak bunlar aslında bitki yangını olabilir |
| 3 | Izgara sayıları karelerin başlangıç noktasına biraz bağlıdır | Kareler kaydırılırsa birkaç kare değişebilir; `grid_ratio` ±%5 oynayabilir |
| 4 | VIIRS parlaklığı yaklaşık 367 K'de doyuma ulaşır | Bu değerdeki noktaların gerçek sıcaklığı daha yüksektir |
| 5 | MODIS ve VIIRS farklı kanal kullanır (21/22 vs I4) | `brightness` doğrudan karşılaştırılmaz; yalnızca "iki sensör de aynı yeri yandı gördü" göstergesi olarak kullanılır |

---

## 5. Üretim Sorumlusu

Bu format, `firms_hatay.sh` script'inin `write_point_csv` fonksiyonu tarafından üretilir. Script:

- Zorunlu sütunları (FIRMS SP `area/csv` başlığına göre `$1`–`$15`) doğru eşler
- `Type` boşsa `0` yazar (bitki yangını varsayılanı)
- Ana CSV ile isim çakışması durumunda otomatik `_points` soneki ekler
- Dosya zaten varsa numaralandırır (`akay1.csv` → `akay1_2.csv` → `akay1_3.csv`)

Sonraki katman (`harmonize.py`) bu dosyayı tek doğruluk kaynağı kabul eder. Başka hiçbir ara dosya bu sözleşmenin yerini tutmaz.

---

## 6. Sözleşme Özeti

> `hatay_points.csv`, FIRMS SP `area/csv` yanıtından türetilmiş, `Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type` sütunlarını içeren, UTF-8, LF, virgül ayırıcı, ondalık noktalı, `Type ∈ {0,1,2,3}` garantili, hatasız bir CSV'dir. Bütün sonraki katmanlar bu sözleşmeye göre çalışır.
