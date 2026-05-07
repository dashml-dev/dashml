#!/usr/bin/env bash
# Test plan dla warstwy 1 zarządzania poświadczeniami.
#
# Sekcja A: build-only (offline, weryfikuje WYJŚCIE kompilatora — zawsze uruchomić)
# Sekcja B: runtime SQL (wymaga lokalnej bazy postgres z tabelą public.orders_one_week)
# Sekcja C: runtime BigQuery (wymaga GCP project + dataset)
# Sekcja D: testy meta (brak env, dotenv, ADC)
#
# Uruchamiać z katalogu playground/:
#   bash test_secrets_layer1.sh A           # tylko build
#   bash test_secrets_layer1.sh A B         # build + SQL runtime
#   bash test_secrets_layer1.sh A B C D     # wszystko

set -u  # pusty unset = błąd
SECTIONS="${*:-A}"

# ───────────────────────────────────────────────────────────────────────────────
# Konfiguracja — uzupełnij przed uruchomieniem sekcji B / C
# ───────────────────────────────────────────────────────────────────────────────
SQL_DB_TYPE="${SQL_DB_TYPE:-postgresql}"
SQL_DB_HOST="${SQL_DB_HOST:-localhost}"
SQL_DB_PORT="${SQL_DB_PORT:-5432}"
SQL_DB_NAME="${SQL_DB_NAME:-dashml_test}"
SQL_DB_USER="${SQL_DB_USER:-postgres}"
SQL_DB_PASSWORD="${SQL_DB_PASSWORD:-}"   # ustaw przed uruchomieniem sekcji B

BQ_PROJECT="${BQ_PROJECT:-}"             # ustaw przed uruchomieniem sekcji C
BQ_CREDENTIALS="${BQ_CREDENTIALS:-}"     # opcjonalne, fallback na ADC

OUTDIR="${OUTDIR:-/tmp/dashml_secret_tests}"
SQL_SPEC="${SQL_SPEC:-simple_sql.dashml}"
BQ_SPEC="${BQ_SPEC:-dashml_new/bigquery_test.dashml}"

PY="${PY:-python3}"

# ───────────────────────────────────────────────────────────────────────────────
# Helpery
# ───────────────────────────────────────────────────────────────────────────────
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  ✓ $*"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ $*" >&2; }
section() { echo; echo "════ $* ════"; }
case_() { echo; echo "── $* ──"; }

# Buduje artefakt; weryfikuje że został wygenerowany i nie zawiera password literałów
verify_build_artifact() {
    local target="$1"; local source_type="$2"; local outdir="$3"
    local main_file
    if [ "$target" = "streamlit" ]; then main_file="$outdir/app.py"
    else main_file="$outdir/app.py"; fi  # plotly/observable także generują app.py dla SQL/BQ

    [ -f "$main_file" ] || { fail "$target/$source_type: brak $main_file"; return 1; }
    [ -f "$outdir/.env.example" ] || { fail "$target/$source_type: brak .env.example"; return 1; }
    [ -f "$outdir/.gitignore" ] || { fail "$target/$source_type: brak .gitignore"; return 1; }
    [ -f "$outdir/SECRETS.md" ] || { fail "$target/$source_type: brak SECRETS.md"; return 1; }

    if [ "$source_type" = "sql" ]; then
        if grep -q "$SQL_DB_PASSWORD" "$main_file" 2>/dev/null && [ -n "$SQL_DB_PASSWORD" ]; then
            fail "$target/$source_type: HASŁO WYCIEKŁO do $main_file"
            return 1
        fi
        grep -q "DASHML_DB_PASSWORD" "$main_file" || { fail "$target/$source_type: brak odwołania do DASHML_DB_PASSWORD"; return 1; }
        grep -q "DATABASE_URL" "$main_file" || { fail "$target/$source_type: brak DATABASE_URL"; return 1; }
    elif [ "$source_type" = "bigquery" ]; then
        grep -q "DASHML_BQ_CREDENTIALS" "$main_file" || { fail "$target/$source_type: brak DASHML_BQ_CREDENTIALS"; return 1; }
        if [ -n "$BQ_CREDENTIALS" ]; then
            grep -F -q "$BQ_CREDENTIALS" "$main_file" && { fail "$target/$source_type: ścieżka do credentials WYCIEKŁA"; return 1; }
        fi
    fi

    grep -q "^DASHML_DB_PASSWORD=$" "$outdir/.env.example" 2>/dev/null || \
        grep -q "DASHML_BQ_PROJECT" "$outdir/.env.example" 2>/dev/null || true

    pass "$target/$source_type: app.py + .env.example + .gitignore + SECRETS.md, brak wycieku"
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
# SEKCJA A — build-only, offline (zawsze)
# ═══════════════════════════════════════════════════════════════════════════════
if [[ "$SECTIONS" == *A* ]]; then
section "A. Build-only (weryfikacja wyjścia kompilatora bez uruchamiania)"

rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"

# A.1 — sześć kombinacji Tier 1, build z pełnymi argumentami CLI
case_ "A.1: build z pełnymi argumentami CLI (defaulty trafiają do .env.example)"
for target in plotly observable streamlit; do
    out="$OUTDIR/${target}_sql_full"
    $PY -m dashml_new.cli build "$SQL_SPEC" -t "$target" -o "$out" \
        --db-type "$SQL_DB_TYPE" --db-host "$SQL_DB_HOST" --db-port "$SQL_DB_PORT" \
        --db-name "$SQL_DB_NAME" --db-user "$SQL_DB_USER" --db-password "$SQL_DB_PASSWORD" \
        > /dev/null 2>&1
    verify_build_artifact "$target" "sql" "$out"
done
for target in plotly observable streamlit; do
    out="$OUTDIR/${target}_bq_full"
    $PY -m dashml_new.cli build "$BQ_SPEC" -t "$target" -o "$out" \
        --bq-project "${BQ_PROJECT:-test-project-id}" \
        ${BQ_CREDENTIALS:+--bq-credentials "$BQ_CREDENTIALS"} \
        > /dev/null 2>&1
    verify_build_artifact "$target" "bigquery" "$out"
done

# A.2 — build BEZ argumentów CLI (powinien się powieść; .env.example z placeholderami)
case_ "A.2: build BEZ argumentów DB (sprawdzenie że są opcjonalne)"
for target in plotly observable streamlit; do
    out="$OUTDIR/${target}_sql_noargs"
    $PY -m dashml_new.cli build "$SQL_SPEC" -t "$target" -o "$out" > /dev/null 2>&1
    verify_build_artifact "$target" "sql" "$out"
    grep -q "your_database\|your_user" "$out/.env.example" \
        && pass "$target/sql noargs: .env.example zawiera placeholdery (your_database / your_user)" \
        || fail "$target/sql noargs: brak placeholderów w .env.example"
done

# A.3 — build BQ bez --bq-project powinien się NIE powieść (project jest wymagane)
case_ "A.3: build BQ bez --bq-project powinien zwrócić błąd"
out="$OUTDIR/plotly_bq_noproject"
if $PY -m dashml_new.cli build "$BQ_SPEC" -t plotly -o "$out" 2>&1 | grep -q "requires --bq-project"; then
    pass "BQ bez --bq-project zwraca poprawny błąd"
else
    fail "BQ bez --bq-project nie zwrócił oczekiwanego błędu"
fi

# A.4 — Tier 2 smoke test: CSV nie powinien generować plików sekretowych
case_ "A.4: smoke test CSV (NIE powinien generować .env.example / SECRETS.md)"
for target in plotly observable streamlit; do
    out="$OUTDIR/${target}_csv"
    $PY -m dashml_new.cli build dashml_example.dashml -t "$target" -o "$out" > /dev/null 2>&1
    if [ -f "$out/.env.example" ] || [ -f "$out/SECRETS.md" ]; then
        fail "$target/csv: nieoczekiwane pliki sekretowe w wyjściu CSV"
    else
        pass "$target/csv: brak plików sekretowych (zgodnie z oczekiwaniem)"
    fi
done

fi  # SEKCJA A

# ═══════════════════════════════════════════════════════════════════════════════
# SEKCJA B — runtime SQL (wymaga postgres)
# ═══════════════════════════════════════════════════════════════════════════════
if [[ "$SECTIONS" == *B* ]]; then
section "B. Runtime SQL (wymaga uruchomionej bazy postgres)"

if [ -z "$SQL_DB_PASSWORD" ]; then
    echo "  ⚠ SQL_DB_PASSWORD nie ustawione — pomijam sekcję B"
else
    # Eksportujemy env zgodnie z konwencją DASHML_DB_*
    export DASHML_DB_TYPE="$SQL_DB_TYPE"
    export DASHML_DB_HOST="$SQL_DB_HOST"
    export DASHML_DB_PORT="$SQL_DB_PORT"
    export DASHML_DB_NAME="$SQL_DB_NAME"
    export DASHML_DB_USER="$SQL_DB_USER"
    export DASHML_DB_PASSWORD="$SQL_DB_PASSWORD"

    # B.1 — Plotly SQL: Flask app powinien wystartować i odpowiedzieć na /api/schema
    case_ "B.1: Plotly SQL → Flask + curl /api/schema"
    out="$OUTDIR/plotly_sql_full"
    $PY "$out/app.py" > "$out/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 3
    if curl -sf http://localhost:5001/api/schema | head -c 200 | grep -q '{'; then
        pass "Plotly/SQL: serwer odpowiada na /api/schema"
    else
        fail "Plotly/SQL: brak odpowiedzi z /api/schema (zob. $out/server.log)"
    fi
    kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null

    # B.2 — Observable SQL
    case_ "B.2: Observable SQL → Flask + curl /api/schema"
    out="$OUTDIR/observable_sql_full"
    $PY "$out/app.py" > "$out/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 3
    if curl -sf http://localhost:5001/api/schema | head -c 200 | grep -q '{'; then
        pass "Observable/SQL: serwer odpowiada na /api/schema"
    else
        fail "Observable/SQL: brak odpowiedzi z /api/schema"
    fi
    kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null

    # B.3 — Streamlit SQL: nie ma curl-owalnego endpointu, ale streamlit musi wystartować bez błędu
    case_ "B.3: Streamlit SQL → uruchom przez 5s, sprawdź brak błędu modułu"
    out="$OUTDIR/streamlit_sql_full"
    streamlit run "$out/app.py" --server.headless true --server.port 8501 \
        > "$out/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 5
    if grep -q "RuntimeError\|Traceback\|ModuleNotFoundError" "$out/server.log"; then
        fail "Streamlit/SQL: błąd przy starcie (zob. $out/server.log)"
    else
        pass "Streamlit/SQL: wystartował bez błędu modułu"
    fi
    kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null
fi

fi  # SEKCJA B

# ═══════════════════════════════════════════════════════════════════════════════
# SEKCJA C — runtime BigQuery (wymaga GCP)
# ═══════════════════════════════════════════════════════════════════════════════
if [[ "$SECTIONS" == *C* ]]; then
section "C. Runtime BigQuery (wymaga GCP project + dataset)"

if [ -z "$BQ_PROJECT" ]; then
    echo "  ⚠ BQ_PROJECT nie ustawione — pomijam sekcję C"
else
    export DASHML_BQ_PROJECT="$BQ_PROJECT"
    [ -n "$BQ_CREDENTIALS" ] && export DASHML_BQ_CREDENTIALS="$BQ_CREDENTIALS"

    # C.1 — Plotly BQ
    case_ "C.1: Plotly BQ → Flask + curl /api/schema"
    out="$OUTDIR/plotly_bq_full"
    $PY "$out/app.py" > "$out/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 5
    if curl -sf http://localhost:5001/api/schema | head -c 200 | grep -q '{'; then
        pass "Plotly/BQ: serwer odpowiada na /api/schema"
    else
        fail "Plotly/BQ: brak odpowiedzi (zob. $out/server.log)"
    fi
    kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null

    # C.2 — Observable BQ
    case_ "C.2: Observable BQ → Flask + curl /api/schema"
    out="$OUTDIR/observable_bq_full"
    $PY "$out/app.py" > "$out/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 5
    if curl -sf http://localhost:5001/api/schema | head -c 200 | grep -q '{'; then
        pass "Observable/BQ: serwer odpowiada na /api/schema"
    else
        fail "Observable/BQ: brak odpowiedzi"
    fi
    kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null

    # C.3 — Streamlit BQ
    case_ "C.3: Streamlit BQ → uruchom przez 5s, sprawdź brak błędu"
    out="$OUTDIR/streamlit_bq_full"
    streamlit run "$out/app.py" --server.headless true --server.port 8502 \
        > "$out/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 5
    if grep -q "RuntimeError\|Traceback\|ModuleNotFoundError" "$out/server.log"; then
        fail "Streamlit/BQ: błąd przy starcie (zob. $out/server.log)"
    else
        pass "Streamlit/BQ: wystartował bez błędu"
    fi
    kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null
fi

fi  # SEKCJA C

# ═══════════════════════════════════════════════════════════════════════════════
# SEKCJA D — testy meta (niezależne od macierzy)
# ═══════════════════════════════════════════════════════════════════════════════
if [[ "$SECTIONS" == *D* ]]; then
section "D. Testy meta (mechanizm sam w sobie)"

# D.1 — brak wymaganych env → czytelny RuntimeError
case_ "D.1: brak DASHML_DB_PASSWORD → czytelny błąd"
out="$OUTDIR/plotly_sql_full"
unset DASHML_DB_PASSWORD
err_output=$(env -i PATH="$PATH" $PY -c "
import sys
sys.path.insert(0, '$out')
try:
    exec(open('$out/app.py').read())
except RuntimeError as e:
    print('RAISED:', e)
" 2>&1)
if echo "$err_output" | grep -q "Missing required environment variables"; then
    pass "Brak env zwraca czytelny RuntimeError"
else
    fail "Brak env nie zwrócił oczekiwanego błędu — output: $err_output"
fi

# D.2 — .env loadowany przez python-dotenv
case_ "D.2: python-dotenv ładuje .env (jeśli zainstalowany)"
if $PY -c "import dotenv" 2>/dev/null; then
    out="$OUTDIR/plotly_sql_full"
    cp "$out/.env.example" "$out/.env"
    echo "DASHML_DB_PASSWORD=test_from_dotenv" >> "$out/.env"
    cd "$out"
    test_output=$(env -i PATH="$PATH" $PY -c "
from dotenv import load_dotenv
load_dotenv()
import os
print('DB_PASSWORD len:', len(os.environ.get('DASHML_DB_PASSWORD', '')))
" 2>&1)
    cd - > /dev/null
    if echo "$test_output" | grep -q "DB_PASSWORD len: [1-9]"; then
        pass "python-dotenv załadował .env"
    else
        fail "python-dotenv NIE załadował .env: $test_output"
    fi
    rm -f "$out/.env"
else
    echo "  ⚠ python-dotenv nie zainstalowany — pomijam D.2"
fi

# D.3 — BigQuery × ADC (manualne, instrukcja)
case_ "D.3: BigQuery × ADC (Application Default Credentials)"
echo "  ℹ Test manualny. Wykonaj na maszynie z gcloud:"
echo "      gcloud auth application-default login"
echo "      unset DASHML_BQ_CREDENTIALS"
echo "      export DASHML_BQ_PROJECT=$BQ_PROJECT"
echo "      python3 $OUTDIR/plotly_bq_full/app.py"
echo "    Oczekiwany rezultat: serwer startuje, /api/schema odpowiada,"
echo "    NIE prosi o credentials (używa domyślnych z gcloud)."

fi  # SEKCJA D

# ───────────────────────────────────────────────────────────────────────────────
# Podsumowanie
# ───────────────────────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════════"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "═══════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
