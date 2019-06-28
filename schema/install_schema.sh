#!/bin/bash -e

# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.

if [ -z "$1" ]; then
  echo "Usage: $0 <auroradb-endpoint>"
  exit 1
fi

HOST=$1
export PGPASSWORD=$(aws secretsmanager get-secret-value --region us-east-1 --secret-id ariel-aurora-dbo \
        --query SecretString --output text | jq -r .password)

BASE=$(dirname $0)
for f in $BASE/*.sql; do
  echo Processing $f...
  psql -h $1 -U aurora_dbo -d ariel -f $f -q
done
