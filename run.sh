#!/usr/bin/env bash
export TELEGRAM_BOT_TOKEN="8986103466:AAHwihetX8mpnlpwlO1xyDeUZ-1gyILL3Rg"
export TELEGRAM_CHAT_ID="431887834"
cd ~/llm-digest
./venv/bin/python digest.py >> digest.log 2>&1
