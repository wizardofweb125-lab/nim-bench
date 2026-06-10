# TECHNIQUE — nim-bench

Dev doc. For user-facing docs, see `README.md`.

## File structure

```
nim-bench/
├── collect.py        # collector (cron, hourly)
├── analyze.py        # analyzer (generates report)
├── switch.py         # auto-switch (picks best model, updates config)
├── cron-collect.sh   # cron wrapper (sources .env, runs all three)
├── .env              # NVIDIA_API_KEY (gitignored)
├── data/
│   ├── nim_bench.csv   # raw data (append-only)
│   ├── rapport.txt     # latest report from analyze.py
│   ├── collect.log     # cron stdout/stderr
│   └── switch.log      # switch decisions log
├── doc/
│   └── TECHNIQUE.md    # this file
└── README.md
```

## collect.py — Collector

### Flow

```
main()
 ├── get_api_key()          # reads NVIDIA_API_KEY env or .env
 ├── fetch_models(api_key)  # GET /v1/models → filter >100B
 │   ├── filter SKIP_PATTERNS (embed, safety, guard, etc.)
 │   ├── filter KNOWN_DEAD (models removed from NIM catalog)
 │   └── extract_size_billions(model_id)
 │       ├── lookup KNOWN_SIZES (table for models without size in name)
 │       └── regex on name (matches NNNb or N.NNt)
 ├── test_model(model_id)   # POST /v1/chat/completions, timeout 45s
 │   └── returns (status, seconds)
 ├── test_tool_calling()    # POST with tools spec, scores 0-3
 └── write_results()        # append CSV
```

### Tunable constants

| Constant | Value | Description |
|---|---|---|
| `TIMEOUT_SECONDS` | 45 | Timeout per model test |
| `KNOWN_SIZES` | dict | Known sizes for models without size in name |
| `KNOWN_DEAD` | list | Models removed from NIM catalog (skipped) |
| `SKIP_PATTERNS` | list | Keywords to filter non-chat models |

### Auto-discovery

The collector calls `GET /v1/models` on every run. If NVIDIA adds a new >100B model:
- If size is in the name (e.g. `foo/bar-200b-instruct`) → auto-detected
- Otherwise → add to `KNOWN_SIZES`

### CSV format

```
timestamp      : ISO 8601 (2026-05-22T02:44:32)
jour           : lundi, mardi, ..., dimanche
heure          : 00-23 (2 digits)
model          : full ID (e.g. mistralai/mistral-small-4-119b-2603)
taille_b       : size in billions (int)
statut         : ok | reasoning_only | timeout | degraded | http_NNN
temps_s        : seconds with 2 decimals
tool_score     : 0-3 (tool calling quality, empty if not tested)
```

Append-only. Never truncate while the benchmark is running.

## analyze.py — Analyzer

### Flow

```
main()
 ├── load_data()            # reads CSV
 └── build_report(rows)     # builds text report
     ├── Header (period, collect count, model count)
     ├── Planning by day
     │   └── For each hour 00h-23h
     │       └── Top 5 models (sorted by median, aggregated across weeks)
     ├── Global ranking
     │   └── All models sorted by median
     │       with min, max, ok count, fail count, availability%, tool score
     ├── Detail cards (focus models)
     │   └── Days x hours table with multi-week median and color icons
     └── Legend
```

### Focus models in detail cards

Defined in `focus_models` (~line 200). To add a model: add its full ID to the list.

### Short names

`short_name()` contains a dictionary of human-readable names. Auto-discovered models show the raw API name. For a clean name, add it to the `parts` dict in `short_name()`.

### Output

The report is printed to stdout and written to `data/rapport.txt` (overwritten each run).

## switch.py — Auto-switch

Runs after each collect via `cron-collect.sh`. Reads stats, picks the best model for the current time slot, and updates the target config file.

Target config is set via `NIM_BENCH_TARGET_CONFIG` env var (default: `config.yaml` in nim-bench dir). The config must have a YAML `model:` / `default:` structure.

### Scoring

```
score = (availability% / 100) x tool_avg / median_latency
```

Filters: min 3 samples, min 60% availability, min 2.0/3 tool calling average. Falls back to global stats if insufficient data for the current time slot.
