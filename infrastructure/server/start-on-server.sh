#!/usr/bin/env bash
# Called by deploy-from-pc.ps1 on the server: unpacks the uploaded release and starts the
# installation in the background (long SSH sessions to this server can drop). Progress goes
# to ~/attendance-setup/log; the last line is DEPLOY_EXIT=<code>.
#     bash start-on-server.sh deploy                 (update)
#     bash start-on-server.sh install DOMAIN         (first time: install + deploy)
set -euo pipefail
MODE="${1:-deploy}"
DOMAIN="${2:-}"
cd "$HOME"
rm -rf attendance-setup
mkdir attendance-setup
tar -xzf attendance-release.tar.gz -C attendance-setup server
sed -i 's/\r$//' attendance-setup/server/*.sh
STEPS="sudo bash $HOME/attendance-setup/server/deploy.sh $HOME/attendance-release.tar.gz"
if [ "$MODE" = install ]; then
  STEPS="sudo DOMAIN=$DOMAIN bash $HOME/attendance-setup/server/install.sh && $STEPS"
fi
nohup bash -c "($STEPS); echo DEPLOY_EXIT=\$?" > attendance-setup/log 2>&1 < /dev/null &
echo "started"
