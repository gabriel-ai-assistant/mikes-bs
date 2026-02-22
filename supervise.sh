#!/bin/bash
LOG=/tmp/openclaw_progress.log
REPORT=/tmp/supervision_report.txt

echo "=== SUPERVISION CHECK $(date -Iseconds) ===" >> $REPORT

if ! tmux list-sessions 2>/dev/null | grep -q mikes-bs; then
  echo "SESSION_DEAD $(date -Iseconds)" >> $LOG
  echo "WARNING: mikes-bs tmux session DEAD" >> $REPORT
  exit 1
fi

tail -10 $LOG 2>/dev/null >> $REPORT
cd /home/gabriel/mikes-bs && git log --oneline -5 >> $REPORT 2>&1
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8470/candidates 2>/dev/null)
echo "App http: $HTTP" >> $REPORT
echo "=== END ===" >> $REPORT
