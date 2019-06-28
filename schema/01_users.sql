-- Copyright 2019, Oath Inc.
-- Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
SET client_min_messages TO warning;

CREATE USER ariel_rw WITH LOGIN;
GRANT rds_iam to ariel_rw;

CREATE USER ariel_ro WITH LOGIN;
GRANT rds_iam to ariel_ro;
