#!/bin/bash
# pull.sh — pull latest changes and restart the service if running.

set -e

cd "$(dirname "$0")"

git pull

echo "Up to date."
