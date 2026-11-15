#!/bin/bash
set -uo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GRID=0.1
TOP_N=10
BAR_LIMIT=30
JPG_WIDTH=1400
JPG_HEIGHT=900
DEFAULT_POLY="./turkiye_sinir.txt"
DEFAULT_HATAY_POLY="./hatay_sinir.txt"
DEFAULT_POINT_CSV="akay1"

for c in curl awk date sort head tail wc md5sum; do
    command -v "$c" >/dev/null 2>&1 || { echo "Eksik: $c"; exit 1; }
done

read -rp "MAP_KEY: " MAP_KEY
[ -z "$MAP_KEY" ] && { echo "✗"; exit 1; }

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

echo "1) Oto (NRT, akıllı polling) 2) Manuel"
read -rp "Mod [1/2]: " _mode
[ "$_mode" = "1" ] && MODE="auto" || MODE="manual"

count_rows () {
    awk -F',' 'NR>1 && NF>5 && $1 ~ /^-?[0-9]/ && $2 ~ /^-?[0-9]/ { c++ } END { print c+0 }' "$1"
}

filter_geojson () {
    local in_csv="$1" out_csv="$2" poly_file="$POLY_FILE"
    if [ ! -f "$poly_file" ] || [ "$(wc -l < "$poly_file")" -lt 10 ]; then cp "$in_csv" "$out_csv"; return; fi
    local in_lines=$(wc -l < "$in_csv" | tr -d ' ')
    if [ "$in_lines" -lt 2 ]; then cp "$in_csv" "$out_csv"; return; fi
    awk -F'[ ,]' -v OFS=',' '
    FNR==NR { poly_x[FNR]=$1+0; poly_y[FNR]=$2+0; n=FNR; next }
    FNR==1 { print; next }
    NF>5 && $1 ~ /^-?[0-9]/ && $2 ~ /^-?[0-9]/ {
        lat=$1+0; lon=$2+0; inside=0; j=n
        for (i=1; i<=n; i++) {
            xi=poly_x[i]; yi=poly_y[i]; xj=poly_x[j]; yj=poly_y[j]
            if ( ((yi>lat)!=(yj>lat)) && (lon < (xj-xi)*(lat-yi)/(yj-yi)+xi) ) inside=!inside
            j=i
        }
        if (inside) print
    }' "$poly_file" "$in_csv" > "$out_csv"
    local out_lines=$(wc -l < "$out_csv" | tr -d ' ')
    if [ "$out_lines" -lt 2 ]; then cp "$in_csv" "$out_csv"; return; fi
    echo "$((in_lines-1))→$((out_lines-1))"
}

grid_agg () {
    awk -F',' -v OFS=',' -v g="$GRID" '
    NR>1 && NF>5 && $1 ~ /^-?[0-9]/ && $2 ~ /^-?[0-9]/ {
        k=sprintf("%.1f_%.1f", int($1/g)*g, int($2/g)*g); c[k]++
    }
    END { for (k in c) print k, c[k] }' "$1"
}

build_merged () {
    awk -F',' -v OFS=',' '
    FNR==NR { m[$1]=$2; next } { v[$1]=$2 }
    END {
        for (k in m) ks[k]=1; for (k in v) ks[k]=1
        for (k in ks) print k, m[k]+0, v[k]+0
    }' "$WORKDIR/mg.csv" "$WORKDIR/vg.csv"
}

fetch_source () {
    local src=$1 out=$2 cur="$START_DATE"
    : > "$out"

    local total_days=$(( (EE - $(date -d "$START_DATE" +%s)) / 86400 + 1 ))
    local total_req=$(( (total_days + 4) / 5 ))    # 5 günlük parçalar
    [ "$total_req" -lt 1 ] && total_req=1

    local req_count=0
    local total_rows=0
    local bar_width=30
    local prefix="  [$src]"

    while [ "$(date -d "$cur" +%s)" -le "$EE" ]; do
        local left=$(( (EE - $(date -d "$cur" +%s))/86400 + 1 ))
        local dr=$left; [ "$dr" -gt 5 ] && dr=5    # API limiti 5 gün

        local url="https://firms.modaps.eosdis.nasa.gov/api/area/csv/${MAP_KEY}/${src}/${BBOX}/${dr}/${cur}"
        local tmp="$WORKDIR/tmp_req.csv"
        curl -sS --max-time 120 "$url" > "$tmp" 2>/dev/null || true

        local rows=$(awk -F',' 'NR>1 && NF>5 && $1 ~ /^-?[0-9]/ {c++} END{print c+0}' "$tmp")
        if head -n 1 "$tmp" 2>/dev/null | grep -qi "latitude"; then
            cat "$tmp" >> "$out"
            total_rows=$((total_rows + rows))
        fi
        rm -f "$tmp"

        req_count=$((req_count + 1))
        local pct=$(( req_count * 100 / total_req ))
        [ "$pct" -gt 100 ] && pct=100

        local filled=$(( pct * bar_width / 100 ))
        local empty=$(( bar_width - filled ))
        local bar=""
        local i=0
        while [ "$i" -lt "$filled" ]; do bar="${bar}█"; i=$((i+1)); done
        while [ "$i" -lt "$bar_width" ]; do bar="${bar}░"; i=$((i+1)); done

        printf "\r%s [%s] %3d%% · %d/%d istek · %d satır   " \
            "$prefix" "$bar" "$pct" "$req_count" "$total_req" "$total_rows"

        cur=$(date -d "$cur + $dr days" +%Y-%m-%d)
        sleep 0.2
    done
    printf "\r%s [%s] 100%% · %d satır — tamam          \n" \
        "$prefix" "██████████████████████████████" "$total_rows"
}

write_point_csv () {
    local out_csv="$1"
    echo "Sensor,Latitude,Longitude,Brightness_K,Acq_Date,Acq_Time,Satellite,Confidence,FRP,Type" > "$out_csv"
    awk -F',' 'NR>1 && NF>5 && $1 ~ /^-?[0-9]/ { t=($15=="")?"0":$15; print "MODIS," $1 "," $2 "," $3 "," $6 "," $7 "," $8 "," $10 "," $13 "," t }' "$WORKDIR/modis.csv" >> "$out_csv"
    awk -F',' 'NR>1 && NF>5 && $1 ~ /^-?[0-9]/ { t=($15=="")?"0":$15; print "VIIRS," $1 "," $2 "," $3 "," $6 "," $7 "," $8 "," $10 "," $13 "," t }' "$WORKDIR/viirs.csv" >> "$out_csv"
    echo "$out_csv: $(($(wc -l < "$out_csv")-1)) satır"
}

write_csv_files () {
    local base="$1"
    {
        echo "grid,modis,viirs,total,viirs_per_modis"
        awk -F',' -v OFS=',' '{ r=($2>0)?$3/$2:0; printf "%s,%d,%d,%d,%.2f\n", $1, $2, $3, $2+$3, r }' "$WORKDIR/merged.csv" | sort -t',' -k4,4 -nr
    } > "${base}.csv"
    {
        echo "dataset,count"
        echo "MODIS,$MODIS_COUNT"; echo "VIIRS,$VIIRS_COUNT"
        echo "VIIRS_per_MODIS,$(awk -v m="$MODIS_COUNT" -v v="$VIIRS_COUNT" 'BEGIN{printf "%.2f",(m>0)?v/m:0}')"
        echo "grid_cells,$(awk -F',' 'END{print NR}' "$WORKDIR/merged.csv")"
        echo "start_date,$START_DATE"; echo "end_date,$END_DATE"
        echo "generated,$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "mode,${MODE_LABEL// /_}"; echo "scope,$SCOPE_NAME"
        echo "bbox,\"$BBOX\""; echo "geo_filter,$USE_FILTER"; echo "grid_deg,$GRID"
    } > "${base}_summary.csv"
    echo "${base}.csv"
    [ "$RUN_BAR_CHART" -eq 1 ] && _build_jpg "${base}.csv" "${base}.jpg"
}

_build_jpg () {
    local main="$1" jpg="$2"
    command -v gnuplot >/dev/null 2>&1 || return
    tail -n +2 "$main" | head -n "$BAR_LIMIT" > "$WORKDIR/plot.csv"
    [ -s "$WORKDIR/plot.csv" ] || return
    local n=$(wc -l < "$WORKDIR/plot.csv" | tr -d ' ')
    local xt="set xtics rotate by -45 font \",8\""
    [ "$n" -le 8 ] && xt="set xtics font \",9\""
    cat > "$WORKDIR/p.gp" <<EOF
set datafile separator ","
set terminal jpeg size ${JPG_WIDTH},${JPG_HEIGHT} enhanced
set output "${jpg}"
set title "${SCOPE_NAME}: MODIS vs VIIRS | ${START_DATE} - ${END_DATE} | M=${MODIS_COUNT} V=${VIIRS_COUNT}" font ",11"
set xlabel "grid"; set ylabel "nokta"
set style data histograms
set style histogram clustered gap 1
set style fill solid 1.0 border -1
set boxwidth 0.9
set key top right
set grid ytics lt 0 lw 1 lc rgb "#ccc"
${xt}
set border 3
plot "${WORKDIR}/plot.csv" using 2:xtic(1) title "MODIS" lc rgb "#d62728", \\
     "" using 3 title "VIIRS" lc rgb "#1f77b4"
EOF
    gnuplot "$WORKDIR/p.gp" 2>/dev/null && [ -s "$jpg" ] && echo "$jpg"
}

select_scope () {
    echo "1) Türkiye 2) Hatay 3) İskenderun 4) Custom"
    read -rp "[1-4]: " _scope_in
    case "$_scope_in" in
        1) SCOPE_NAME="Türkiye"; SCOPE_SHORT="turkiye"; WEST=25.60; SOUTH=35.80; EAST=44.80; NORTH=42.10; DEFAULT_FILTER="$DEFAULT_POLY" ;;
        2) SCOPE_NAME="Hatay"; SCOPE_SHORT="hatay"; WEST=35.75; SOUTH=35.80; EAST=36.75; NORTH=37.00; DEFAULT_FILTER="$DEFAULT_HATAY_POLY" ;;
        3) SCOPE_NAME="İskenderun"; SCOPE_SHORT="iskenderun"; WEST=35.75; SOUTH=36.25; EAST=36.60; NORTH=36.75; DEFAULT_FILTER="$DEFAULT_HATAY_POLY" ;;
        4) SCOPE_NAME="Custom"; SCOPE_SHORT="custom"
           while :; do
               read -rp "W,S,E,N: " _b
               [[ "$_b" =~ ^[-0-9.]+,[-0-9.]+,[-0-9.]+,[-0-9.]+$ ]] && { IFS=',' read -r WEST SOUTH EAST NORTH <<< "$_b"; DEFAULT_FILTER="$DEFAULT_HATAY_POLY"; break; }
           done ;;
        *) exit 1 ;;
    esac
    BBOX="${WEST},${SOUTH},${EAST},${NORTH}"
}

if [ "$MODE" = "auto" ]; then
    echo ""
    echo "─── Oto mod: bölge seçimi ───"
    select_scope

    echo ""
    echo "Sorgu sıklığı:"
    echo "  1) 60s    (~4320 istek/gün, agresif)"
    echo "  2) 120s   (~2160 istek/gün, dengeli)"
    echo "  3) 300s   (~864  istek/gün, güvenli)"
    echo "  4) 30dk   (~144  istek/gün, sakin)"
    echo "  5) 1saat  (~72   istek/gün, minimal)"
    read -rp "Seçim [1-5, varsayılan 2]: " _poll
    case "$_poll" in
        1) POLL=60 ;;
        3) POLL=300 ;;
        4) POLL=1800 ;;
        5) POLL=3600 ;;
        *) POLL=120 ;;
    esac

    USE_ARCHIVE=0
    SRC_MODIS="MODIS_NRT"; SRC_VIIRS1="VIIRS_SNPP_NRT"; SRC_VIIRS2="VIIRS_NOAA20_NRT"; MODE_LABEL="NRT"

    USE_FILTER=1
    POLY_FILE="$DEFAULT_FILTER"
    if [ ! -f "$POLY_FILE" ]; then
        echo "⚠ $POLY_FILE yok → filtre kapalı"
        USE_FILTER=0
    fi

    RUN_COUNT_TABLE=1; RUN_MATCH_TABLE=0; RUN_BAR_CHART=1; RUN_TOP_FIRES=1

    trap 'echo ""; echo "Durduruldu."; exit 0' INT TERM

    echo ""
    echo "─── Oto mod aktif ───"
    echo "  Bölge : $SCOPE_NAME"
    echo "  Kaynak: NRT (area API)"
    echo "  Poll  : ${POLL}s"
    echo "  Kota  : ~$(( 86400 / POLL * 3 ))/gün (limit 5000)"
    echo "  Filtre: $([ "$USE_FILTER" -eq 1 ] && echo "AÇIK ($POLY_FILE)" || echo "kapalı")"
    echo "  Ctrl+C ile durdur"
    echo ""

    LIVE_POINTS_FILE="$SCRIPT_DIR/data/nrt_live_points.csv"
    mkdir -p "$SCRIPT_DIR/data"
    LAST_HASH=""
    TUR=0
    while true; do
        TUR=$((TUR + 1))
        ts=$(date +%Y%m%d_%H%M%S)
        saat=$(date +%H:%M:%S)

        START_DATE=$(date -d '1 day ago' +%Y-%m-%d)
        END_DATE=$(date +%Y-%m-%d)
        SE=$(date -d "$START_DATE" +%s)
        EE=$(date -d "$END_DATE" +%s)

        : > "$WORKDIR/modis.csv"
        : > "$WORKDIR/viirs1.csv"
        : > "$WORKDIR/viirs2.csv"
        fetch_source "$SRC_MODIS"  "$WORKDIR/modis.csv"  2>/dev/null
        fetch_source "$SRC_VIIRS1" "$WORKDIR/viirs1.csv" 2>/dev/null
        fetch_source "$SRC_VIIRS2" "$WORKDIR/viirs2.csv" 2>/dev/null
        cat "$WORKDIR/viirs1.csv" "$WORKDIR/viirs2.csv" > "$WORKDIR/viirs.csv"

        if [ "$USE_FILTER" -eq 1 ]; then
            filter_geojson "$WORKDIR/modis.csv" "$WORKDIR/m2.csv" 2>/dev/null && mv "$WORKDIR/m2.csv" "$WORKDIR/modis.csv"
            filter_geojson "$WORKDIR/viirs.csv" "$WORKDIR/v2.csv" 2>/dev/null && mv "$WORKDIR/v2.csv" "$WORKDIR/viirs.csv"
        fi

        CUR_HASH=$(cat "$WORKDIR/modis.csv" "$WORKDIR/viirs.csv" 2>/dev/null | md5sum | cut -d' ' -f1)

        if [ "$CUR_HASH" = "$LAST_HASH" ]; then
            echo "[$saat] #$TUR · $SCOPE_NAME · değişiklik yok"
        else
            MODIS_COUNT=$(count_rows "$WORKDIR/modis.csv")
            VIIRS_COUNT=$(count_rows "$WORKDIR/viirs.csv")

            if [ "$MODIS_COUNT" -eq 0 ] && [ "$VIIRS_COUNT" -eq 0 ]; then
                echo "[$saat] #$TUR · $SCOPE_NAME · veri boş"
                LAST_HASH="$CUR_HASH"
            else
                grid_agg "$WORKDIR/modis.csv" > "$WORKDIR/mg.csv"
                grid_agg "$WORKDIR/viirs.csv" > "$WORKDIR/vg.csv"
                build_merged > "$WORKDIR/merged.csv"

                base="${SCOPE_SHORT}_${ts}"
                write_csv_files "$base" >/dev/null
                write_point_csv "${base}_points.csv" >/dev/null

                echo "[$saat] #$TUR · $SCOPE_NAME · ✅ YENİ — M=$MODIS_COUNT V=$VIIRS_COUNT"
                echo "         ${base}.csv  ${base}.jpg  ${base}_points.csv"
                LAST_HASH="$CUR_HASH"
            fi
        fi

        live_tmp="${LIVE_POINTS_FILE}.tmp.$$"
        if ! write_point_csv "$live_tmp" >/dev/null || [ ! -s "$live_tmp" ]; then
            echo "NRT canlı CSV yazılamadı: $live_tmp" >&2
            rm -f "$live_tmp"
            exit 1
        fi
        if ! mv -f "$live_tmp" "$LIVE_POINTS_FILE"; then
            echo "NRT canlı CSV yayımlanamadı: $LIVE_POINTS_FILE" >&2
            rm -f "$live_tmp"
            exit 1
        fi
        sleep "$POLL"
    done
fi

echo "1) Türkiye 2) Hatay 3) İskenderun 4) Custom"
read -rp "[1-4]: " _scope_in
case "$_scope_in" in
    1) SCOPE_NAME="Türkiye"; WEST=25.60; SOUTH=35.80; EAST=44.80; NORTH=42.10; DEFAULT_FILTER="$DEFAULT_POLY" ;;
    2) SCOPE_NAME="Hatay"; WEST=35.75; SOUTH=35.80; EAST=36.75; NORTH=37.00; DEFAULT_FILTER="$DEFAULT_HATAY_POLY" ;;
    3) SCOPE_NAME="İskenderun"; WEST=35.75; SOUTH=36.25; EAST=36.60; NORTH=36.75; DEFAULT_FILTER="$DEFAULT_HATAY_POLY" ;;
    4) SCOPE_NAME="Custom"
       while :; do
           read -rp "W,S,E,N: " _b
           [[ "$_b" =~ ^[-0-9.]+,[-0-9.]+,[-0-9.]+,[-0-9.]+$ ]] && { IFS=',' read -r WEST SOUTH EAST NORTH <<< "$_b"; DEFAULT_FILTER="$DEFAULT_HATAY_POLY"; break; }
       done ;;
    *) exit 1 ;;
esac
BBOX="${WEST},${SOUTH},${EAST},${NORTH}"

echo "1) Archive(SP) 2) NRT (güncel)"
read -rp "Kaynak [1/2]: " _src
[ "$_src" = "2" ] && USE_ARCHIVE=0 || USE_ARCHIVE=1

echo "1) 10g 2) 1ay 3) 3ay 4) 6ay 5) 1yıl 6) Custom"
read -rp "Zaman [1-6]: " _time_in
case "$_time_in" in
    1) DAYS=10 ;; 2) DAYS=30 ;; 3) DAYS=90 ;; 4) DAYS=180 ;; 5) DAYS=365 ;; 6) DAYS=0 ;; *) DAYS=10 ;;
esac
if [ "$DAYS" -gt 0 ]; then
    END_DATE=$(date -d '2 days ago' +%Y-%m-%d)
    START_DATE=$(date -d "$DAYS days ago" +%Y-%m-%d)
    echo "  $START_DATE → $END_DATE"
else
    while :; do read -rp "Başlangıç: " START_DATE; date -d "$START_DATE" +%s >/dev/null 2>&1 && break; done
    while :; do read -rp "Bitiş: " END_DATE; [ "$(date -d "$END_DATE" +%s 2>/dev/null)" -ge "$(date -d "$START_DATE" +%s)" ] 2>/dev/null && break; done
fi
SE=$(date -d "$START_DATE" +%s); EE=$(date -d "$END_DATE" +%s)

read -rp "Sınır filtresi? [1/0]: " _f
if [ "$_f" = "1" ]; then
    USE_FILTER=1
    [ -n "$DEFAULT_FILTER" ] && [ -f "$DEFAULT_FILTER" ] && echo "1) Varsayılan ($DEFAULT_FILTER) 2) Kendi" || echo "1) Hatay 2) Kendi"
    read -rp "[1/2]: " _fi
    if [ "$_fi" = "2" ]; then
        read -rp "Dosya: " CUSTOM_POLY
        if [[ "$CUSTOM_POLY" == *.geojson ]] || [[ "$CUSTOM_POLY" == *.json ]]; then
            if command -v jq >/dev/null 2>&1; then
                jq -r '.features[]? | .geometry.coordinates | .. | arrays | select(length == 2 and (.[0] | type) == "number") | "\(.[0]) \(.[1])"' "$CUSTOM_POLY" > "$WORKDIR/p.txt"
                [ ! -s "$WORKDIR/p.txt" ] && jq -r '.coordinates | .. | arrays | select(length == 2 and (.[0] | type) == "number") | "\(.[0]) \(.[1])"' "$CUSTOM_POLY" > "$WORKDIR/p.txt"
                POLY_FILE="$WORKDIR/p.txt"
            else USE_FILTER=0; fi
        elif [ -f "$CUSTOM_POLY" ]; then POLY_FILE="$CUSTOM_POLY"
        else USE_FILTER=0; fi
    else
        POLY_FILE="$DEFAULT_FILTER"
        [ ! -f "$POLY_FILE" ] && { echo "  yok → kapalı"; USE_FILTER=0; }
    fi
else
    USE_FILTER=0; POLY_FILE=""
fi

read -rp "İşlem [1-4, boş=tüm]: " _ops
_ops=$(echo "$_ops" | tr -d ' '); [ -z "$_ops" ] && _ops="1,2,3,4"
RUN_COUNT_TABLE=0; RUN_MATCH_TABLE=0; RUN_BAR_CHART=0; RUN_TOP_FIRES=0
IFS=',' read -ra _arr <<< "$_ops"
for o in "${_arr[@]}"; do
    case "$o" in 1) RUN_COUNT_TABLE=1 ;; 2) RUN_MATCH_TABLE=1 ;; 3) RUN_BAR_CHART=1 ;; 4) RUN_TOP_FIRES=1 ;; esac
done
[ $((RUN_COUNT_TABLE+RUN_MATCH_TABLE+RUN_BAR_CHART+RUN_TOP_FIRES)) -eq 0 ] && { RUN_COUNT_TABLE=1; RUN_MATCH_TABLE=1; RUN_BAR_CHART=1; RUN_TOP_FIRES=1; }

read -rp "Grid adı [boş=atla]: " CSV_NAME
CSV_NAME="${CSV_NAME%.csv}"; CSV_NAME="${CSV_NAME// /_}"
read -rp "Nokta adı [$DEFAULT_POINT_CSV]: " _pi
POINT_CSV_NAME="${_pi:-$DEFAULT_POINT_CSV}"
POINT_CSV_NAME="${POINT_CSV_NAME%.csv}"; POINT_CSV_NAME="${POINT_CSV_NAME// /_}"

if [ "$USE_ARCHIVE" -eq 1 ]; then
    SRC_MODIS="MODIS_SP"; SRC_VIIRS1="VIIRS_SNPP_SP"; SRC_VIIRS2="VIIRS_NOAA20_SP"; MODE_LABEL="SP"
else
    SRC_MODIS="MODIS_NRT"; SRC_VIIRS1="VIIRS_SNPP_NRT"; SRC_VIIRS2="VIIRS_NOAA20_NRT"; MODE_LABEL="NRT"
fi

[ "$RUN_BAR_CHART" -eq 1 ] && [ -z "$CSV_NAME" ] && RUN_BAR_CHART=0

DAYS_DIFF=$(( (EE-SE)/86400 + 1 ))
if [ "$DAYS_DIFF" -gt 60 ]; then
    REQS=$(( (DAYS_DIFF + 4) / 5 * 3 ))    # 5 günlük parçalar için tahmini istek sayısı
    echo "$DAYS_DIFF gün → ~$REQS istek"
    read -rp "Devam? [e/H]: " _a; [[ "$_a" =~ ^[Ee]$ ]] || exit 1
fi

HCODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "https://firms.modaps.eosdis.nasa.gov/" 2>/dev/null || echo "000")
[ "$HCODE" != "200" ] && { echo "Sunucu: $HCODE"; read -rp "Devam? [e/H]: " _a; [[ "$_a" =~ ^[Ee]$ ]] || exit 1; }

TEST_URL="https://firms.modaps.eosdis.nasa.gov/api/area/csv/${MAP_KEY}/${SRC_MODIS}/${BBOX}/1/${START_DATE}"
TB=$(curl -sS --max-time 30 "$TEST_URL" 2>/dev/null)
echo "$TB" | head -n 1 | grep -qiE "latitude|country_id" || { echo "API hata: $TB"; exit 1; }

echo ""
echo "MODIS..."
fetch_source "$SRC_MODIS"  "$WORKDIR/modis.csv"
echo "VIIRS..."
fetch_source "$SRC_VIIRS1" "$WORKDIR/viirs1.csv"
fetch_source "$SRC_VIIRS2" "$WORKDIR/viirs2.csv"
cat "$WORKDIR/viirs1.csv" "$WORKDIR/viirs2.csv" > "$WORKDIR/viirs.csv"

if [ "$USE_FILTER" -eq 1 ]; then
    echo ""
    echo "filtre MODIS..."
    filter_geojson "$WORKDIR/modis.csv" "$WORKDIR/m2.csv" && mv "$WORKDIR/m2.csv" "$WORKDIR/modis.csv"
    echo "filtre VIIRS..."
    filter_geojson "$WORKDIR/viirs.csv" "$WORKDIR/v2.csv" && mv "$WORKDIR/v2.csv" "$WORKDIR/viirs.csv"
fi

MODIS_COUNT=$(count_rows "$WORKDIR/modis.csv")
VIIRS_COUNT=$(count_rows "$WORKDIR/viirs.csv")
echo ""
echo "M=$MODIS_COUNT V=$VIIRS_COUNT"

if [ "$MODIS_COUNT" -eq 0 ] && [ "$VIIRS_COUNT" -eq 0 ]; then exit 0; fi

grid_agg "$WORKDIR/modis.csv" > "$WORKDIR/mg.csv"
grid_agg "$WORKDIR/viirs.csv" > "$WORKDIR/vg.csv"
build_merged > "$WORKDIR/merged.csv"

[ "$RUN_COUNT_TABLE" -eq 1 ] && { echo "──────────────"; printf "MODIS  %6d\nVIIRS  %6d\n" "$MODIS_COUNT" "$VIIRS_COUNT"; echo "──────────────"; }

[ "$RUN_MATCH_TABLE" -eq 1 ] && { echo "─── eşleşme ───"; printf "%-14s %6s %6s %5s\n" "grid" "M" "V" "V/M"; awk -F',' '{ r=($2>0)?$3/$2:0; printf "%-14s %6d %6d %5.1f\n", $1, $2, $3, r }' "$WORKDIR/merged.csv" | sort -t',' -k3,3 -nr | head -30; }

[ "$RUN_TOP_FIRES" -eq 1 ] && { echo "─── top $TOP_N ───"; awk -F',' -v OFS=',' '{ print $1, $2+$3, $2, $3 }' "$WORKDIR/merged.csv" | sort -t',' -k2,2 -nr | head -n "$TOP_N" | awk -F',' 'BEGIN{ printf "%-3s %-14s %5s %5s %5s\n","#","grid","M","V","tot" }{ printf "%-3d %-14s %5d %5d %5d\n", NR, $1, $3, $4, $2 }'; }

echo "─── özet ───"
printf "M=%d V=%d mod=%d v/m=%.1f\n" "$MODIS_COUNT" "$VIIRS_COUNT" \
    "$(awk -F',' 'END{print NR}' "$WORKDIR/merged.csv")" \
    "$(awk -v m="$MODIS_COUNT" -v v="$VIIRS_COUNT" 'BEGIN{print (m>0)?v/m:0}')"

echo "─── dosya ───"
[ -n "$CSV_NAME" ] && write_csv_files "$CSV_NAME"
write_point_csv "${POINT_CSV_NAME}.csv"