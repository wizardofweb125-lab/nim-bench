#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.env" 2>/dev/null
python3 "$SCRIPT_DIR/collect.py" >> "$SCRIPT_DIR/data/collect.log" 2>&1
python3 "$SCRIPT_DIR/analyze.py" > /dev/null 2>&1
python3 "$SCRIPT_DIR/switch.py" >> "$SCRIPT_DIR/data/collect.log" 2>&1
