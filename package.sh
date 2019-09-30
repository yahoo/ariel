#!/bin/bash -e

# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.

if [ -z "$1" ]; then
  echo "Usage: $0 <s3-bucket>"
  echo "    s3-bucket must exist and will be used to package and upload CloudFormation template and source zip"
  exit 1
fi
BUCKET=$1

VERSION=$(cat ariel/__init__.py | grep "__version__" | cut -f 2 -d "'")
echo Building ariel-$VERSION.zip

(test -d build && (rm -rf build || sudo rm -rf build)) || true
mkdir build
test -f ariel-$VERSION.zip && rm ariel-$VERSION.zip

docker run -v $(pwd):/working --rm "lambci/lambda:build-python3.6" /bin/bash -c "pip install -r /working/$SOURCE/requirements.txt -t /working/build --prefix ''"
cp -R ariel build
(cd build; zip -r ../ariel-$VERSION.zip .)
rm -rf build || sudo rm -rf build || true

cat cloudformation/ariel.yaml | sed 's!CodeUri: ../ariel/!CodeUri: s3://'$BUCKET/lambda/ariel/$VERSION/ariel-$VERSION'.zip!' > ariel-$VERSION.yaml
cat cloudformation/ariel-vpc.yaml | sed 's!CodeUri: ../ariel/!CodeUri: s3://'$BUCKET/lambda/ariel/$VERSION/ariel-$VERSION'.zip!' > ariel-vpc-$VERSION.yaml

aws s3 cp ariel-$VERSION.zip s3://$BUCKET/lambda/ariel/$VERSION/ariel-$VERSION.zip
aws s3 cp ariel-$VERSION.yaml s3://$BUCKET/lambda/ariel/$VERSION/ariel-$VERSION.yaml
aws s3 cp ariel-vpc-$VERSION.yaml s3://$BUCKET/lambda/ariel/$VERSION/ariel-vpc-$VERSION.yaml
echo "Ariel can be installed from : https://s3.amazonaws.com/$BUCKET/lambda/ariel/$VERSION/ariel-$VERSION.yaml"
echo "                         or : https://s3.amazonaws.com/$BUCKET/lambda/ariel/$VERSION/ariel-vpc-$VERSION.yaml"
