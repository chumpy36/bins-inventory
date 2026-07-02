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

  # --timeout 5: don't wait 10+ minutes for a slow uvicorn shutdown.
  # SIGTERM is sent, 5s grace, then SIGKILL. Stateless web container, safe.
  sudo /usr/local/bin/docker compose down --timeout 5

  sudo /usr/local/bin/docker network prune -f
  sudo /usr/local/bin/docker compose up -d

  # Known Synology-docker bug: compose up sometimes leaves containers in
  # 'Created' state instead of starting them. Bounce any that are stuck.
  sleep 2
  for c in $IMAGE_NAME ${IMAGE_NAME}-tunnel; do
    STATE=\$(sudo /usr/local/bin/docker inspect -f '{{.State.Status}}' \"\$c\" 2>/dev/null || echo missing)
    if [ \"\$STATE\" = \"created\" ]; then
      echo \"Container \$c stuck in Created — starting manually\"
      sudo /usr/local/bin/docker start \"\$c\"
    fi
  done

  echo 'Deploy complete!'
  sudo /usr/local/bin/docker ps --filter \"name=$IMAGE_NAME\" --format '{{.Names}}\t{{.Status}}'
"

echo "=== Done ==="
