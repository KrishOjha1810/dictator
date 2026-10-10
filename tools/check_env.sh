#!/usr/bin/env bash
# Check that .env has the same variables, in the same order, as .env.example.
#
#   tools/check_env.sh
#
# .env.example is the standard: every name the scripts read, grouped and
# commented, with no values. .env is a copy of it with the values filled in.
# Prints names only, never values. Exits 1 when the two differ.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
names() { sed -n 's/^\([A-Za-z0-9_]*\)=.*/\1/p' "$1"; }

[ -f "$ROOT/.env" ] || { echo "no .env: cp .env.example .env, then fill it in" >&2; exit 1; }

ok=1
dups="$(names "$ROOT/.env" | sort | uniq -d)"
[ -z "$dups" ] || { echo "in .env more than once:" $dups; ok=0; }
missing="$(comm -23 <(names "$ROOT/.env.example" | sort -u) <(names "$ROOT/.env" | sort -u))"
[ -z "$missing" ] || { echo "missing from .env:" $missing; ok=0; }
extra="$(comm -13 <(names "$ROOT/.env.example" | sort -u) <(names "$ROOT/.env" | sort -u))"
[ -z "$extra" ] || { echo "in .env but not .env.example:" $extra; ok=0; }
if [ "$ok" = 1 ] && [ "$(names "$ROOT/.env")" != "$(names "$ROOT/.env.example")" ]; then
    echo "same names, different order"; ok=0
fi

empty="$(sed -n 's/^\([A-Za-z0-9_]*\)=$/\1/p' "$ROOT/.env")"
[ -z "$empty" ] || echo "not filled in yet:" $empty

[ "$ok" = 1 ] && echo ".env matches .env.example" || exit 1
