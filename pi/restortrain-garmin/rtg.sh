#!/bin/bash
# uruchamianie z venv projektu: ./rtg.sh parse|login|pobierz-wzorce|sync [--dry-run]|status
cd "$(dirname "$0")" && exec .venv/bin/python -m rtg.cli "$@"
