#!/bin/bash
# Visible commands only. Explanations stay in the edited captions.
set -euo pipefail
cd "${DEVSENTRY_PROJECT}"

hold_mark() {
  MARK_NAME="$1" python3 - <<'PY'
import os
import time
with open(os.environ["STORY_MARKS"], "a", encoding="utf-8") as handle:
    handle.write(f"{os.environ['MARK_NAME']} {time.time():.3f}\n")
time.sleep(float(os.environ.get("STORY_HOLD", "8")))
PY
}

prompt() {
  printf '\033[38;5;74m$\033[0m'
  local part
  for part in "$@"; do
    if [[ "$part" == *[[:space:]]* || "$part" == *[\(\)]* ]]; then
      printf " '%s'" "$part"
    else
      printf ' %s' "$part"
    fi
  done
  printf '\n'
}

clear
prompt python3 -B run_sample.py
python3 -B run_sample.py > /tmp/ds-story/stdout.txt 2> /tmp/ds-story/traceback.txt || true
cat /tmp/ds-story/traceback.txt
grep -q ZeroDivisionError /tmp/ds-story/traceback.txt
hold_mark crash

export DEVSENTRY_TRACE=/tmp/ds-story/traceback.txt
DEVSENTRY_PHASE=inspect python3 /tmp/ds-story/launch.py
DEVSENTRY_PHASE=diagnose python3 /tmp/ds-story/launch.py

clear
prompt sed -i 's/ratio(1, 0)/ratio(1, 2)/' src/app.py
sed -i 's/ratio(1, 0)/ratio(1, 2)/' src/app.py
printf '\n'
prompt git --no-pager diff --unified=0 -- src/app.py
git --no-pager diff --unified=0 -- src/app.py
printf '\n'
prompt python3 -B run_sample.py
python3 -B run_sample.py
hold_mark fixed

DEVSENTRY_PHASE=review python3 /tmp/ds-story/launch.py
hold_mark done
