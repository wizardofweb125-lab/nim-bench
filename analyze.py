#!/usr/bin/env python3
"""
NIM Bench — Analyseur
Lit les données collectées et génère un rapport heure par heure
avec le top 5 des modèles les plus rapides.
Sortie dans data/rapport.txt
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

DIR = Path(__file__).parent
DATA_FILE = DIR / "data" / "nim_bench.csv"
RAPPORT_FILE = DIR / "data" / "rapport.txt"

JOURS_ORDRE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def short_name(model_id: str) -> str:
    parts = {
        "deepseek-ai/deepseek-v4-pro": "DeepSeek V4 Pro (1.66T)",
        "deepseek-ai/deepseek-v4-flash": "DeepSeek V4 Flash (284B)",
        "moonshotai/kimi-k2.6": "Kimi K2.6 (1T)",
        "mistralai/mistral-large-3-675b-instruct-2512": "Mistral Large 3 (675B)",
        "mistralai/mistral-medium-3.5-128b": "Mistral Medium 3.5 (128B)",
        "mistralai/mistral-small-4-119b-2603": "Mistral Small 4 (119B)",
        "mistralai/mistral-nemotron": "Mistral Nemotron (130B)",
        "qwen/qwen3-coder-480b-a35b-instruct": "Qwen 3 Coder (480B)",
        "qwen/qwen3-next-80b-a3b-instruct": "Qwen 3 Next (80B)",
        "qwen/qwen3.5-397b-a17b": "Qwen 3.5 (397B)",
        "qwen/qwen3.5-122b-a10b": "Qwen 3.5 (122B)",
        "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super (120B)",
        "openai/gpt-oss-120b": "GPT-OSS (120B)",
        "openai/gpt-oss-20b": "GPT-OSS (20B)",
        "minimaxai/minimax-m2.7": "MiniMax M2.7 (200B)",
        "meta/llama-4-maverick-17b-128e-instruct": "Llama 4 Maverick (400B)",
        "z-ai/glm-5.1": "GLM 5.1 (130B)",
        "stockmark/stockmark-2-100b-instruct": "Stockmark 2 (100B)",
    }
    return parts.get(model_id, model_id.split("/")[-1])


def load_data() -> list[dict]:
    if not DATA_FILE.exists():
        print(f"Pas de données : {DATA_FILE}")
        sys.exit(1)
    with open(DATA_FILE) as f:
        return list(csv.DictReader(f))


def build_report(rows: list[dict]) -> str:
    # Grouper par jour + heure
    slots = defaultdict(lambda: defaultdict(list))
    all_statuts = defaultdict(lambda: defaultdict(lambda: {"ok": 0, "fail": 0}))

    for row in rows:
        jour = row["jour"]
        heure = int(row["heure"])
        model = row["model"]
        statut = row["statut"]
        temps = float(row["temps_s"])

        if statut in ("ok", "reasoning_only"):
            slots[(jour, heure)][model].append(temps)
            all_statuts[model][(jour, heure)]["ok"] += 1
        else:
            all_statuts[model][(jour, heure)]["fail"] += 1

    # Infos générales
    timestamps = sorted(set(row["timestamp"][:10] for row in rows))
    first = min(row["timestamp"] for row in rows)[:16].replace("T", " ")
    last = max(row["timestamp"] for row in rows)[:16].replace("T", " ")
    nb_collectes = len(set(row["timestamp"] for row in rows))
    models_vus = sorted(set(row["model"] for row in rows))

    lines = []
    sep = "═" * 95
    sep2 = "─" * 95

    lines.append(sep)
    lines.append("  NIM BENCH — RAPPORT DE DISPONIBILITÉ")
    lines.append(sep)
    lines.append(f"  Période      : {first} → {last}")
    lines.append(f"  Jours         : {', '.join(timestamps)}")
    lines.append(f"  Collectes     : {nb_collectes}")
    week_numbers = sorted(set(
        datetime.fromisoformat(row["timestamp"]).isocalendar()[1] for row in rows
    ))
    lines.append(f"  Modèles testés: {len(models_vus)}")
    lines.append(f"  Semaines      : {len(week_numbers)}")
    lines.append(sep)

    # Pour chaque jour
    for jour in JOURS_ORDRE:
        heures_du_jour = sorted(set(h for (j, h) in slots if j == jour))
        if not heures_du_jour:
            continue

        lines.append("")
        w = 24
        tw = 5 + 1 + (w + 3) * 5 + 1
        lines.append(f"  ┌{'─' * tw}┐")
        lines.append(f"  │  {jour.upper():^{tw-4}}  │")
        lines.append(f"  ├{'─' * tw}┤")
        lines.append(f"  │ {'Heure':^5} │ {'#1 (plus rapide)':<{w}} │ {'#2':<{w}} │ {'#3':<{w}} │ {'#4':<{w}} │ {'#5':<{w}} │")
        lines.append(f"  ├{'─' * tw}┤")

        for heure in range(24):
            key = (jour, heure)
            h_str = f"{heure:02d}h"

            if key not in slots or not slots[key]:
                lines.append(f"  │ {h_str:^5} │ {'—':<{w}} │ {'—':<{w}} │ {'—':<{w}} │ {'—':<{w}} │ {'—':<{w}} │")
                continue

            model_scores = []
            for model, times in slots[key].items():
                med = median(times)
                model_scores.append((model, round(med, 1), len(times)))
            model_scores.sort(key=lambda x: x[1])

            top5 = model_scores[:5]
            cols = []
            for model, med, n in top5:
                name = short_name(model)
                entry = f"{name} ({med}s)"
                if len(entry) > w:
                    name = name[:w - len(f" ({med}s)")]
                    entry = f"{name} ({med}s)"
                cols.append(entry)
            while len(cols) < 5:
                cols.append("—")

            lines.append(f"  │ {h_str:^5} │ {cols[0]:<{w}} │ {cols[1]:<{w}} │ {cols[2]:<{w}} │ {cols[3]:<{w}} │ {cols[4]:<{w}} │")

        lines.append(f"  └{'─' * tw}┘")

    # Classement global
    lines.append("")
    lines.append(sep)
    lines.append("  CLASSEMENT GLOBAL — Temps médian sur toutes les mesures")
    lines.append(sep)
    lines.append(f"  {'#':>3}  {'Modèle':<35} {'Médiane':>8} {'Min':>8} {'Max':>8} {'OK':>5} {'Fail':>5} {'Dispo%':>7} {'Tools':>6}")
    lines.append(f"  {sep2}")

    global_times = defaultdict(list)
    global_ok = defaultdict(int)
    global_fail = defaultdict(int)
    global_tool_scores = defaultdict(list)

    for row in rows:
        model = row["model"]
        if row["statut"] in ("ok", "reasoning_only"):
            global_times[model].append(float(row["temps_s"]))
            global_ok[model] += 1
            ts = row.get("tool_score", "")
            if ts != "":
                try:
                    global_tool_scores[model].append(int(ts))
                except (ValueError, TypeError):
                    pass
        else:
            global_fail[model] += 1

    ranking = []
    for model, times in global_times.items():
        total = global_ok[model] + global_fail[model]
        dispo = round(global_ok[model] / total * 100) if total > 0 else 0
        tscores = global_tool_scores.get(model, [])
        avg_tool = round(sum(tscores) / len(tscores), 1) if tscores else None
        ranking.append({
            "model": model,
            "median": round(median(times), 2),
            "min": round(min(times), 2),
            "max": round(max(times), 2),
            "ok": global_ok[model],
            "fail": global_fail[model],
            "dispo": dispo,
            "tool_avg": avg_tool,
        })
    ranking.sort(key=lambda x: x["median"])

    for i, r in enumerate(ranking, 1):
        name = short_name(r["model"])
        if len(name) > 33:
            name = name[:33]
        tool_str = f"{r['tool_avg']}/3" if r["tool_avg"] is not None else "—"
        lines.append(
            f"  {i:>3}. {name:<35} {r['median']:>7}s {r['min']:>7}s {r['max']:>7}s {r['ok']:>5} {r['fail']:>5} {r['dispo']:>6}% {tool_str:>6}"
        )

    # Modèles jamais dispo
    never_ok = [m for m in set(row["model"] for row in rows) if m not in global_times]
    if never_ok:
        lines.append("")
        lines.append(f"  JAMAIS DISPONIBLE : {', '.join(short_name(m) for m in sorted(never_ok))}")

    # Fiches détaillées par modèle
    focus_models = [
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-v4-flash",
        "z-ai/glm-5.1",
        "moonshotai/kimi-k2.6",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "mistralai/mistral-medium-3.5-128b",
        "mistralai/mistral-small-4-119b-2603",
        "mistralai/mistral-nemotron",
    ]

    lines.append("")
    lines.append(sep)
    lines.append("  FICHES DÉTAILLÉES PAR MODÈLE")
    lines.append(sep)

    for model_id in focus_models:
        name = short_name(model_id)
        model_rows = [r for r in rows if r["model"] == model_id]
        if not model_rows:
            continue

        ok_rows = [r for r in model_rows if r["statut"] in ("ok", "reasoning_only")]
        total = len(model_rows)
        nb_ok = len(ok_rows)
        dispo = round(nb_ok / total * 100) if total else 0

        jours_actifs = [j for j in JOURS_ORDRE if any(r["jour"] == j for r in model_rows)]
        if not jours_actifs:
            continue

        raw = defaultdict(lambda: {"ok_times": [], "total": 0})
        for r in model_rows:
            j = r["jour"]
            h = int(r["heure"])
            statut = r["statut"]
            temps = float(r["temps_s"])
            raw[(j, h)]["total"] += 1
            if statut in ("ok", "reasoning_only"):
                raw[(j, h)]["ok_times"].append(temps)

        cells = {}
        for key, data in raw.items():
            ok_times = data["ok_times"]
            n = data["total"]
            if ok_times:
                med = round(median(ok_times), 1)
                if med < 1:
                    icon = "🟢"
                elif med < 5:
                    icon = "🟡"
                elif med < 15:
                    icon = "🟠"
                else:
                    icon = "🔴"
                if len(ok_times) < n:
                    cells[key] = (icon, f"{med}s {len(ok_times)}/{n}")
                else:
                    cells[key] = (icon, f"{med}s")
            else:
                cells[key] = ("❌", f"0/{n}")

        lines.append("")
        stats = f"  {name}"
        if ok_rows:
            ts = [float(r["temps_s"]) for r in ok_rows]
            med = round(median(ts), 2)
            mn = round(min(ts), 2)
            mx = round(max(ts), 2)
            stats += f"  —  Méd: {med}s | Min: {mn}s | Max: {mx}s | Dispo: {dispo}% ({nb_ok}/{total})"
        else:
            stats += f"  —  Dispo: {dispo}% ({nb_ok}/{total})"
        lines.append(stats)

        cw = 14
        day_cols_top = "┬".join("─" * (cw + 2) for _ in jours_actifs)
        day_cols_mid = "┼".join("─" * (cw + 2) for _ in jours_actifs)
        day_cols_bot = "┴".join("─" * (cw + 2) for _ in jours_actifs)

        lines.append(f"  ┌{'─' * 7}┬{day_cols_top}┐")
        header = f"  │ {'Heure':^5} │"
        for j in jours_actifs:
            header += f" {j[:3].upper():^{cw}} │"
        lines.append(header)
        lines.append(f"  ├{'─' * 7}┼{day_cols_mid}┤")

        for h in range(24):
            if not any((j, h) in cells for j in jours_actifs):
                continue
            h_str = f"{h:02d}h"
            row = f"  │ {h_str:^5} │"
            for j in jours_actifs:
                if (j, h) in cells:
                    icon, val = cells[(j, h)]
                    cell = f"{icon} {val}"
                    row += f" {cell:<{cw - 1}} │"
                else:
                    row += f" {'—':<{cw}} │"
            lines.append(row)

        lines.append(f"  └{'─' * 7}┴{day_cols_bot}┘")

    # Légende
    lines.append("")
    lines.append("  Légende: 🟢 <1s  🟡 1-5s  🟠 5-15s  🔴 >15s  ❌ timeout/erreur")

    lines.append("")
    lines.append(sep)
    lines.append(f"  Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(sep)

    return "\n".join(lines)


def main():
    rows = load_data()
    if not rows:
        print("Fichier vide.")
        return

    rapport = build_report(rows)

    # Écrire le fichier
    RAPPORT_FILE.write_text(rapport)
    print(f"Rapport écrit dans {RAPPORT_FILE}")
    print()
    print(rapport)


if __name__ == "__main__":
    main()
