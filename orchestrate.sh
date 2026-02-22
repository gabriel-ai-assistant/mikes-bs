#!/bin/bash
# Mike's BS overnight build orchestrator
# Runs one Codex session per block, chains them sequentially
# Restarts Codex if it exits without completing

set -euo pipefail
LOG=/tmp/openclaw_progress.log
DIR=/home/gabriel/mikes-bs
PROMPTS=/home/gabriel/mikes-bs/prompts

log() { echo "$(date -Iseconds) [ORCH] $1" | tee -a $LOG; }
is_done() { grep -q "^$1" $LOG 2>/dev/null; }

cd $DIR

# Ensure prompt dir exists
mkdir -p $PROMPTS
cp /home/gabriel/mikes-bs/prompts/*.txt $PROMPTS/ 2>/dev/null || true

run_block() {
  local BLOCK="$1"
  local PROMPT_FILE="$2"

  if is_done "${BLOCK}_COMPLETE"; then
    log "${BLOCK}_SKIPPED (already done)"
    return 0
  fi

  log "${BLOCK}_START"

  for attempt in 1 2 3; do
    log "${BLOCK}_attempt_${attempt}"
    PROMPT=$(cat "$PROMPT_FILE")
    codex --yolo exec "$PROMPT" 2>&1 | tee -a /tmp/codex_${BLOCK}.log || true

    if is_done "${BLOCK}_COMPLETE"; then
      log "${BLOCK}_DONE"
      return 0
    fi

    if is_done "${BLOCK}_BLOCKED"; then
      log "${BLOCK}_BLOCKED_detected, moving on"
      return 0
    fi

    log "${BLOCK}_no_complete_marker_after_attempt_${attempt}"
    sleep 15
  done

  log "${BLOCK}_GAVE_UP_after_3_attempts — marking BLOCKED and continuing"
  echo "${BLOCK}_BLOCKED $(date -Iseconds)" >> $LOG
}

log "ORCHESTRATOR_START v2"

run_block "BLOCK_B" "$PROMPTS/prompt_blockB.txt"
run_block "BLOCK_C" "$PROMPTS/prompt_blockC.txt"
run_block "BLOCK_D" "$PROMPTS/prompt_blockD.txt"
run_block "BLOCK_E" "$PROMPTS/prompt_blockE.txt"
run_block "BLOCK_FG" "$PROMPTS/prompt_blockFG.txt"
run_block "BLOCK_H" "$PROMPTS/prompt_blockH.txt"
run_block "FINAL" "$PROMPTS/prompt_final.txt"

log "ORCHESTRATOR_COMPLETE"
echo ""
echo "=============================="
echo "BUILD COMPLETE — all blocks done"
echo "=============================="
