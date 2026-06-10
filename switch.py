#!/usr/bin/env python3
"""
NIM Bench — Auto-switch
Lit les stats collectées, choisit le meilleur modèle pour le créneau actuel
(latence + dispo + tool calling), et met à jour un fichier config YAML.
Le fichier cible est configurable via TARGET_CONFIG (env var ou .env).
"""

import csv
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

DIR = Path(__file__).parent
DATA_FILE = DIR / "data" / "nim_bench.csv"
TARGET_CONFIG = Path(os.environ.get("NIM_BENCH_TARGET_CONFIG", DIR / "config.yaml"))
SWITCH_LOG = DIR / "data" / "switch.log"

MIN_SAMPLES = 3
MIN_DISPO_PCT = 60
MIN_TOOL_AVG = 2.0
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def load_stats() -> dict:
    """Charge le CSV et agrège par (modèle, jour, heure)."""
    if not DATA_FILE.exists():
        return {}
    stats = defaultdict(lambda: {"times": [], "ok": 0, "fail": 0, "tool_scores": []})
    with open(DATA_FILE) as f:
        for row in csv.DictReader(f):
            model = row["model"]
            jour = row["jour"]
            heure = int(row["heure"])
            key = (model, jour, heure)
            if row["statut"] in ("ok", "reasoning_only"):
                stats[key]["times"].append(float(row["temps_s"]))
                stats[key]["ok"] += 1
                ts = row.get("tool_score", "")
                if ts != "":
                    try:
                        stats[key]["tool_scores"].append(int(ts))
                    except (ValueError, TypeError):
                        pass
            else:
                stats[key]["fail"] += 1
    return stats


def pick_best(stats: dict, jour: str, heure: int) -> str | None:
    """Choisit le meilleur modèle pour ce créneau.

    Score composite = dispo% * tool_avg / median_latency
    Filtres: MIN_SAMPLES, MIN_DISPO_PCT, MIN_TOOL_AVG
    """
    candidates = []
    for (model, j, h), s in stats.items():
        if j != jour or h != heure:
            continue
        total = s["ok"] + s["fail"]
        if total < MIN_SAMPLES:
            continue
        dispo = s["ok"] / total * 100
        if dispo < MIN_DISPO_PCT:
            continue
        med = median(s["times"]) if s["times"] else 99
        tool_scores = s["tool_scores"]
        tool_avg = sum(tool_scores) / len(tool_scores) if tool_scores else None
        if tool_avg is not None and tool_avg < MIN_TOOL_AVG:
            continue
        tool_factor = tool_avg if tool_avg is not None else 2.0
        score = (dispo / 100) * tool_factor / max(med, 0.1)
        candidates.append((model, score, med, dispo, tool_avg))

    if not candidates:
        return pick_best_global(stats)

    candidates.sort(key=lambda x: -x[1])
    best = candidates[0]
    log(f"  Créneau {jour} {heure}h: {best[0]} (score={best[1]:.2f} med={best[2]:.2f}s dispo={best[3]:.0f}% tools={best[4]})")
    return best[0]


def pick_best_global(stats: dict) -> str | None:
    """Fallback: meilleur modèle tous créneaux confondus."""
    by_model = defaultdict(lambda: {"times": [], "ok": 0, "fail": 0, "tool_scores": []})
    for (model, _, _), s in stats.items():
        by_model[model]["times"].extend(s["times"])
        by_model[model]["ok"] += s["ok"]
        by_model[model]["fail"] += s["fail"]
        by_model[model]["tool_scores"].extend(s["tool_scores"])

    candidates = []
    for model, s in by_model.items():
        total = s["ok"] + s["fail"]
        if total < MIN_SAMPLES:
            continue
        dispo = s["ok"] / total * 100
        if dispo < MIN_DISPO_PCT:
            continue
        med = median(s["times"]) if s["times"] else 99
        tool_scores = s["tool_scores"]
        tool_avg = sum(tool_scores) / len(tool_scores) if tool_scores else None
        if tool_avg is not None and tool_avg < MIN_TOOL_AVG:
            continue
        tool_factor = tool_avg if tool_avg is not None else 2.0
        score = (dispo / 100) * tool_factor / max(med, 0.1)
        candidates.append((model, score, med, dispo, tool_avg))

    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[1])
    best = candidates[0]
    log(f"  Fallback global: {best[0]} (score={best[1]:.2f} med={best[2]:.2f}s dispo={best[3]:.0f}% tools={best[4]})")
    return best[0]


def update_config(model_id: str) -> bool:
    """Met à jour model.default dans le fichier config YAML cible."""
    if not TARGET_CONFIG.exists():
        log(f"  ERREUR: {TARGET_CONFIG} introuvable")
        return False

    content = TARGET_CONFIG.read_text()
    pattern = r"^(model:\s*\n\s*default:\s*)(.+)$"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        log("  ERREUR: pattern 'model.default' non trouvé dans config.yaml")
        return False

    current = match.group(2).strip()
    if current == model_id:
        log(f"  Déjà configuré: {model_id}")
        return False

    new_content = content[:match.start(2)] + model_id + content[match.end(2):]
    TARGET_CONFIG.write_text(new_content)
    log(f"  Switch: {current} → {model_id}")
    return True


def log(msg: str):
    print(msg)
    with open(SWITCH_LOG, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {msg}\n")


def main():
    now = datetime.now()
    jour = JOURS_FR[now.weekday()]
    heure = now.hour

    log(f"NIM Switch — {jour} {heure}h")

    stats = load_stats()
    if not stats:
        log("  Pas de données, abandon")
        return

    best = pick_best(stats, jour, heure)
    if not best:
        log("  Aucun modèle éligible, on garde le courant")
        return

    update_config(best)


if __name__ == "__main__":
    main()
