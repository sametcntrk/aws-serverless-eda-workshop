#!/usr/bin/env bash
# Deletes the Voltaj stacks with an hourly cost (workshop day is over). Keeps voltaj-global (certificate, WAF),
# voltaj-base (KMS key, secrets), voltaj-learning (trace table, on-demand) and the artifacts bucket.
# Bring everything back with: tools/deploy.sh all
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
read -r -p "Delete voltaj-3pl, -paysim, -edge, -app, -integration, -data, -network in $REGION (account $ACCOUNT)? Type yes: " ok
[ "$ok" = "yes" ] || { echo "Stopped."; exit 1; }
del() {
  echo "== delete $1"
  aws cloudformation delete-stack --region $REGION --stack-name "$1"
  aws cloudformation wait stack-delete-complete --region $REGION --stack-name "$1"
}
for b in voltaj-web voltaj-uploads voltaj-lake voltaj-osi-export; do
  aws s3 rm "s3://$b-$ACCOUNT" --recursive --region $REGION --quiet || true
done
del voltaj-3pl
del voltaj-paysim
del voltaj-edge
del voltaj-app
del voltaj-integration
del voltaj-data
del voltaj-network
echo "Done. Fixed-cost resources are gone. Run tools/deploy.sh all to bring the shop back (the seed runs again)."
