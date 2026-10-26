#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
grep -E "Held-out|Findings|SHA-256" "$ROOT/results/SUMMARY.md" || true
head -5 "$ROOT/results/m2_size_comparison.csv" || true
