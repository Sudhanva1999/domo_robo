#!/bin/bash
# push.sh — stage everything, commit with an auto-incremented serial message, push.

set -e

cd "$(dirname "$0")"

# Serial number = total commits so far + 1
N=$(( $(git rev-list --count HEAD 2>/dev/null || echo 0) + 1 ))
MSG="Update #${N}"

git add -A
git commit -m "$MSG"
git push

echo "Pushed: $MSG"
