#!/usr/bin/env bash
# Quick code update of one or more functions (code only; layers and config need tools/deploy.sh app). Usage: tools/hotfix.sh order cart
set -euo pipefail
cd "$(dirname "$0")/.."
for f in "$@"; do
  rm -f /tmp/voltaj-$f.zip
  (cd app/functions/$f && zip -qr /tmp/voltaj-$f.zip .)
  aws lambda update-function-code --region eu-central-1 --function-name voltaj-$f --zip-file fileb:///tmp/voltaj-$f.zip --query LastUpdateStatus --output text
  aws lambda wait function-updated --region eu-central-1 --function-name voltaj-$f
done
