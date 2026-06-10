#!/usr/bin/env python3
"""
NIM Bench — Collecteur
Récupère la liste des modèles NIM >100B, les teste et log les résultats.
Conçu pour tourner en cron toutes les heures.
"""

import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

DIR = Path(__file__).parent
DATA_FILE = DIR / "data" / "nim_bench.csv"
API_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.environ.get("NVIDIA_API_KEY", "")
TIMEOUT_SECONDS = 45

KNOWN_SIZES = {
    "deepseek-ai/deepseek-v4-pro": 1660,
    "deepseek-ai/deepseek-v4-flash": 284,
    "moonshotai/kimi-k2.6": 1000,
    "mistralai/mistral-nemotron": 130,
    "z-ai/glm-5.1": 130,
    "minimaxai/minimax-m2.7": 200,
    "meta/llama-4-maverick-17b-128e-instruct": 400,
    "mistralai/mixtral-8x22b-v0.1": 176,
    "mistralai/mixtral-8x7b-instruct-v0.1": 47,
}

SKIP_PATTERNS = [
    "embed", "rerank", "nvclip", "vila", "riva", "arctic-embed", "nv-embed",
    "cosmos", "fuyu", "neva", "deplot", "kosmos", "parse", "gliner",
    "safety", "guard", "content-safety", "topic-control", "reward",
    "calibration", "detector", "starcoder", "codegemma", "codellama",
]

KNOWN_DEAD = [
    "nvidia/nemotron-4-340b-instruct",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "mistralai/mixtral-8x22b-v0.1",
    "writer/palmyra-creative-122b",
]


def get_api_key():
    if API_KEY:
        return API_KEY
    env_file = DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("NVIDIA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return ""


def extract_size_billions(model_id: str) -> int | None:
    if model_id in KNOWN_SIZES:
        return KNOWN_SIZES[model_id]
    patterns = [
        r'(\d+(?:\.\d+)?)t[- _]',   # 1.66T
        r'(\d+(?:\.\d+)?)t$',
        r'(\d+)b[- _]',              # 675b, 120b
        r'(\d+)b$',
        r'-(\d+)b-',
    ]
    name = model_id.split("/")[-1].lower()
    for pat in patterns:
        m = re.search(pat, name)
        if m:
            val = float(m.group(1))
            if 't' in pat:
                return int(val * 1000)
            return int(val)
    return None


def fetch_models(api_key: str) -> list[str]:
    req = Request(f"{API_URL}/models", headers={"Authorization": f"Bearer {api_key}"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    all_ids = sorted(set(m["id"] for m in data["data"]))
    chat_models = [
        m for m in all_ids
        if not any(s in m.lower() for s in SKIP_PATTERNS)
    ]
    big_models = []
    for mid in chat_models:
        size = extract_size_billions(mid)
        if size and size >= 100:
            big_models.append((mid, size))
    big_models = [(m, s) for m, s in big_models if m not in KNOWN_DEAD]
    big_models.sort(key=lambda x: -x[1])
    return big_models


TOOL_CALLING_SPEC = {
    "tools": [
        {"type": "function", "function": {
            "name": "navigate", "description": "Navigate to URL in a browser tab",
            "parameters": {"type": "object", "properties": {
                "tabId": {"type": "integer", "description": "Tab ID"},
                "url": {"type": "string", "description": "URL to navigate to"},
            }, "required": ["tabId", "url"]}}},
        {"type": "function", "function": {
            "name": "screenshot", "description": "Take a screenshot of a browser tab",
            "parameters": {"type": "object", "properties": {
                "tabId": {"type": "integer", "description": "Tab ID"},
            }, "required": ["tabId"]}}},
        {"type": "function", "function": {
            "name": "file_upload", "description": "Upload a file to a file input element",
            "parameters": {"type": "object", "properties": {
                "tabId": {"type": "integer", "description": "Tab ID"},
                "selector": {"type": "string", "description": "CSS selector"},
                "filePath": {"type": "string", "description": "Absolute file path"},
            }, "required": ["tabId", "selector", "filePath"]}}},
    ],
    "system": "Tu es un agent d'automatisation web. Utilise les outils pour accomplir les tâches.",
    "user": "Navigue vers https://example.com/dashboard dans l'onglet 77, puis uploade /tmp/img.png sur le selecteur #image.",
    "expect_tool": "navigate",
    "expect_args": {"tabId": 77, "url": "https://example.com/dashboard"},
}


def test_model(model_id: str, api_key: str) -> tuple[str, float]:
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": "Say hi in one word"}],
        "max_tokens": 5,
    }).encode()
    req = Request(
        f"{API_URL}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    start = time.monotonic()
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            elapsed = time.monotonic() - start
            body = json.loads(resp.read())
            content = body["choices"][0]["message"].get("content") or ""
            reasoning = body["choices"][0]["message"].get("reasoning_content") or ""
            if content:
                return "ok", round(elapsed, 2)
            elif reasoning:
                return "reasoning_only", round(elapsed, 2)
            else:
                return "empty", round(elapsed, 2)
    except HTTPError as e:
        elapsed = time.monotonic() - start
        try:
            detail = json.loads(e.read()).get("detail", "")
        except Exception:
            detail = ""
        if "DEGRADED" in str(detail):
            return "degraded", round(elapsed, 2)
        return f"http_{e.code}", round(elapsed, 2)
    except (URLError, TimeoutError, OSError):
        elapsed = time.monotonic() - start
        return "timeout", round(elapsed, 2)


def test_tool_calling(model_id: str, api_key: str) -> int:
    """Teste la capacité tool calling du modèle. Score 0-3.
    0 = pas de tool call / erreur
    1 = tool call mais mauvais outil
    2 = bon outil mais mauvais arguments
    3 = bon outil + bons arguments
    """
    spec = TOOL_CALLING_SPEC
    payload = json.dumps({
        "model": model_id,
        "messages": [
            {"role": "system", "content": spec["system"]},
            {"role": "user", "content": spec["user"]},
        ],
        "tools": spec["tools"],
        "max_tokens": 200,
    }).encode()
    req = Request(
        f"{API_URL}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read())
            msg = body["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return 0
            first = tool_calls[0]
            name = first.get("function", {}).get("name", "")
            if name != spec["expect_tool"]:
                return 1
            try:
                args = json.loads(first["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                return 2
            expected = spec["expect_args"]
            if args.get("tabId") == expected["tabId"] and expected["url"] in args.get("url", ""):
                return 3
            return 2
    except Exception:
        return 0


CSV_FIELDS = ["timestamp", "jour", "heure", "model", "taille_b", "statut", "temps_s", "tool_score"]


def _migrate_csv_header():
    """Ajoute tool_score au header si absent."""
    if not DATA_FILE.exists():
        return
    with open(DATA_FILE) as f:
        first = f.readline().strip()
    if "tool_score" not in first:
        content = DATA_FILE.read_text()
        content = content.replace(first, first + ",tool_score", 1)
        DATA_FILE.write_text(content)


def write_results(results: list[dict]):
    _migrate_csv_header()
    file_exists = DATA_FILE.exists() and DATA_FILE.stat().st_size > 0
    with open(DATA_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(results)


def main():
    api_key = get_api_key()
    if not api_key:
        print("ERREUR: NVIDIA_API_KEY non trouvée")
        return

    now = datetime.now()
    jours_fr = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    jour = jours_fr[now.weekday()]
    heure = now.strftime("%H")

    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] NIM Bench — collecte")

    try:
        models = fetch_models(api_key)
    except Exception as e:
        print(f"  ERREUR fetch models: {e}")
        return

    print(f"  {len(models)} modèles >100B détectés")

    results = []
    for model_id, size in models:
        statut, temps = test_model(model_id, api_key)
        tool_score = ""
        if statut in ("ok", "reasoning_only"):
            tool_score = test_tool_calling(model_id, api_key)
            print(f"  {model_id} ({size}B): {statut} {temps}s  tools={tool_score}/3")
        else:
            print(f"  {model_id} ({size}B): {statut} {temps}s")
        results.append({
            "timestamp": now.isoformat(timespec="seconds"),
            "jour": jour,
            "heure": heure,
            "model": model_id,
            "taille_b": size,
            "statut": statut,
            "temps_s": temps,
            "tool_score": tool_score,
        })

    write_results(results)
    print(f"  → {len(results)} résultats écrits dans {DATA_FILE}")


if __name__ == "__main__":
    main()
