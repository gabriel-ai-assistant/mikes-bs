#!/bin/bash
cd /home/gabriel/mikes-bs
PROMPT=$(cat CODEX_CONTINUE.txt)
codex --yolo exec "$PROMPT"
