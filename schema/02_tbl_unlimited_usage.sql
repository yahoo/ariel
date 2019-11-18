-- Copyright 2019, Oath Inc.
-- Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
SET client_min_messages TO warning;

CREATE TABLE unlimited_usage
(
    accountid            character(12)               NOT NULL,
    accountname          character varying(64)       NOT NULL,
    region               character varying(20)       NOT NULL, -- ap-northeast-3 + 6
    instancetypefamily   character varying(3)        NOT NULL, -- [t2, t3, t3a]
    unlimitedusageamount double precision            NOT NULL,
    unlimitedusagecost   money                       NOT NULL,
	PRIMARY KEY (accountid, region, instancetypefamily)
) WITH ( OIDS=FALSE );
GRANT ALL ON TABLE unlimited_usage TO aurora_dbo;
GRANT SELECT, UPDATE, INSERT, DELETE, TRUNCATE ON TABLE unlimited_usage TO ariel_rw;
GRANT SELECT ON TABLE unlimited_usage TO ariel_ro;
