#!/usr/bin/env bash
export TELEGRAM_BOT_TOKEN="<TG_BOT_TOKEN>"
export TELEGRAM_CHAT_ID="<TG_CHAT_ID>"
cd ~/llm-digest
./venv/bin/python digest.py >> digest.log 2>&1
