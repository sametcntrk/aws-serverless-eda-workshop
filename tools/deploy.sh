#!/usr/bin/env bash
# Deploys the Voltaj stacks in order. Usage: tools/deploy.sh [all|global|base|network|data|integration|learning|app|edge|paysim|3pl|web|setup]
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ARTIFACTS=voltaj-artifacts-$ACCOUNT
TAGS="Project=voltaj"
out() { aws cloudformation describe-stacks --region "${3:-$REGION}" --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text; }
deploy() {  # name template [extra args...]
  local name=$1 tpl=$2; shift 2
  echo "== deploy $name"
  aws cloudformation deploy --region "${DEPLOY_REGION:-$REGION}" --stack-name "$name" --template-file "$tpl" --tags $TAGS \
    --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset "$@"
}
build_layers() {
  if [ ! -d build/deps/python/pg8000 ]; then
    mkdir -p build/deps/python build/pillow/python
    uv pip install -q --target build/deps/python --python-platform x86_64-manylinux2014 --python-version 3.13 --only-binary :all: \
      pg8000 pika kafka-python aws-msk-iam-sasl-signer-python python-dateutil six
    uv pip install -q --target build/pillow/python --python-platform x86_64-manylinux2014 --python-version 3.13 --only-binary :all: pillow
  fi
}
step=${1:-all}
case $step in
  global) DEPLOY_REGION=us-east-1 deploy voltaj-global cloudformation/global.yaml ;;
  base) deploy voltaj-base cloudformation/base.yaml ;;
  network) python3 cloudformation/src/gen_network.py cloudformation/network.yaml; deploy voltaj-network cloudformation/network.yaml ;;
  data) deploy voltaj-data cloudformation/data.yaml ;;
  integration) deploy voltaj-integration cloudformation/integration.yaml ;;
  learning) deploy voltaj-learning cloudformation/learning.yaml ;;
  app)
    build_layers
    python3 app/statemachine/gen_checkout.py app/statemachine/checkout.asl.json
    python3 cloudformation/src/gen_app.py cloudformation/app.json
    aws cloudformation package --region $REGION --template-file cloudformation/app.json --s3-bucket "$ARTIFACTS" --s3-prefix app \
      --output-template-file build/app.packaged.json --use-json >/dev/null
    MSK=$(out voltaj-integration MskArn)
    BOOT=$(aws kafka get-bootstrap-brokers --region $REGION --cluster-arn "$MSK" --query BootstrapBrokerStringSaslIam --output text)
    PARAMS=(MskBootstrap="$BOOT" EnableMskConsumers="${MSK_CONSUMERS:-true}" EnablePipe="${PIPE:-true}")
    [ -f build/personas.json ] && PARAMS+=(Personas="$(cat build/personas.json)")
    SMS_ORIGIN=${SMS_ORIGIN:-$(aws pinpoint-sms-voice-v2 describe-phone-numbers --region $REGION \
      --query "PhoneNumbers[?NumberType=='SIMULATOR'].PhoneNumber | [0]" --output text 2>/dev/null || true)}
    [ -n "$SMS_ORIGIN" ] && [ "$SMS_ORIGIN" != "None" ] && PARAMS+=(SmsOrigin="$SMS_ORIGIN")
    S3_BUCKET=$ARTIFACTS deploy voltaj-app build/app.packaged.json --s3-bucket "$ARTIFACTS" --s3-prefix app --parameter-overrides "${PARAMS[@]}" ;;
  edge) deploy voltaj-edge cloudformation/edge.yaml --parameter-overrides CertArn="$(out voltaj-global CertArn us-east-1)" \
          WebAclArn="$(out voltaj-global WebAclArn us-east-1)" ;;
  paysim)
    aws cloudformation package --region $REGION --template-file cloudformation/paysim.yaml --s3-bucket "$ARTIFACTS" --s3-prefix paysim \
      --output-template-file build/paysim.packaged.yaml >/dev/null
    deploy voltaj-paysim build/paysim.packaged.yaml --parameter-overrides CertArn="$(out voltaj-global CertArn us-east-1)" ;;
  3pl) aws s3 cp app/threepl/ "s3://$ARTIFACTS/threepl/" --recursive --region $REGION --quiet
       deploy voltaj-3pl cloudformation/threepl.yaml --parameter-overrides CodeBucket="$ARTIFACTS" ;;
  web) python3 tools/build_web.py && aws s3 sync web/ "s3://$(out voltaj-data WebBucket)/" --region $REGION --delete \
         --exclude "images/*" --cache-control "public, max-age=60" && \
       aws cloudfront create-invalidation --distribution-id "$(out voltaj-edge DistributionId)" --paths "/*" --query Invalidation.Id --output text ;;
  setup)
    for f in fulfillment producer; do
      echo "== setup $f"; aws lambda invoke --region $REGION --function-name voltaj-$f --cli-binary-format raw-in-base64-out \
        --payload '{"action":"setup"}' /dev/stdout; echo
    done ;;
  all) for s in global base network data integration learning; do "$0" $s; done
       MSK_CONSUMERS=false PIPE=false "$0" app; "$0" setup; "$0" app; "$0" edge; "$0" paysim; "$0" 3pl; uv run -q --with boto3 --with pillow python tools/seed.py; "$0" app; "$0" web ;;
  *) echo "unknown step $step"; exit 1 ;;
esac
