<p align="center">
  <img src="docs/banner.svg" alt="NIM Bench" width="700"/>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License"/></a>
  <img src="https://img.shields.io/badge/python-3-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3"/>
  <img src="https://img.shields.io/badge/NVIDIA-NIM_free_tier-76b900?style=flat-square&logo=nvidia&logoColor=white" alt="NVIDIA NIM"/>
  <img src="https://img.shields.io/badge/deps-zero-brightgreen?style=flat-square" alt="Zero dependencies"/>
</p>

Continuous benchmark for LLMs on the NVIDIA NIM free tier. Tracks availability, latency, and tool-calling quality hour-by-hour to find the best model for each time slot.

## What it does

1. **Collect** (cron, hourly) — queries the NIM API, auto-discovers models >100B, tests each with a minimal prompt (latency) + a tool-calling spec (quality), logs results to CSV.

2. **Analyze** (after each collect) — reads the CSV, generates a report with:
   - Hour-by-hour planning with top 5 fastest models
   - Global ranking (median, min, max, availability%, tool-calling score)
   - Per-model detail cards with colored timeline

3. **Auto-switch** (after each collect) — picks the best model for the current time slot using a composite score (latency x availability x tool-calling), and updates a YAML config file.

## Quick start

```bash
cd nim-bench

# Set your NVIDIA API key
export NVIDIA_API_KEY="nvapi-..."
# Or create a .env file:
echo 'NVIDIA_API_KEY=nvapi-...' > .env

# Run a manual collect
python3 collect.py

# Generate the report
python3 analyze.py

# View the report
cat data/rapport.txt
```

## Cron setup

```bash
# Edit crontab
crontab -e

# Add (runs every hour)
0 * * * * /path/to/nim-bench/cron-collect.sh
```

Logs go to `data/collect.log`.

## Data format

The CSV (`data/nim_bench.csv`) has one row per model per collect:

```
timestamp,jour,heure,model,taille_b,statut,temps_s,tool_score
2026-05-22T02:44:32,vendredi,02,mistralai/mistral-small-4-119b-2603,119,ok,0.33,3
```

Statuses: `ok`, `reasoning_only`, `timeout`, `degraded`, `http_404`, `http_502`, `http_503`

Tool score (0-3):
- 0 = no tool call / error
- 1 = tool call but wrong tool
- 2 = right tool but wrong arguments
- 3 = right tool + right arguments

## Report legend

- Green: < 1s (fast)
- Yellow: 1-5s (ok)
- Orange: 5-15s (slow)
- Red: > 15s (very slow)
- X: timeout or error

## Auto-switch

`switch.py` runs after each collect. Composite score:

```
score = (availability% / 100) x tool_avg / median_latency
```

Filters: min 3 samples, min 60% availability, min 2.0/3 tool-calling. Falls back to global stats if not enough data for the current slot.

By default, switch.py updates `config.yaml` in the nim-bench directory. Set `NIM_BENCH_TARGET_CONFIG` to point to a different file:

```bash
export NIM_BENCH_TARGET_CONFIG="/path/to/your/config.yaml"
```

The config must have a `model:` / `default:` YAML structure.

## Dependencies

Python 3 standard library only. No pip install needed.
