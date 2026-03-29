#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
NAS_USER="jholland"
NAS_HOST="nas"
NAS_DEPLOY_DIR="/volume1/docker/bins-inventory"
IMAGE_NAME="bins-inventory"

echo "=== Bins Inventory Deploy ==="

# Check for uncommitted changes
cd "$REPO_DIR"
if [ -n "$(git status --porcelain)" ]; then
  echo "Committing local changes..."
  git add -A
  git commit -m "deploy: $(date '+%Y-%m-%d %H:%M')"
fi

echo "Pushing to GitHub..."
git push

echo "Building Docker image on NAS..."
ssh "$NAS_HOST" "
  set -e
  cd $NAS_DEPLOY_DIR
  git pull
  sudo /usr/local/bin/docker build -t $IMAGE_NAME .
  sudo /usr/local/bin/docker compose down
  sudo /usr/local/bin/docker network prune -f
  sudo /usr/local/bin/docker compose up -d
  echo 'Deploy complete!'
"

echo "=== Done ==="
