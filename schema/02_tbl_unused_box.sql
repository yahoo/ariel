-- Copyright 2019, Oath Inc.
-- Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
SET client_min_messages TO warning;

CREATE TABLE unused_box
(
    accountid         character(12)               NOT NULL,
    accountname       character varying(64)       NOT NULL,
    region            character varying(20)       NOT NULL, -- ap-northeast-3 + 6
    instancetype      character varying(15)       NOT NULL, -- r5ad.24xlarge + 2
    unusedusageamount double precision            NOT NULL,
    unusedusagecost   money                       NOT NULL,
	PRIMARY KEY (accountid, region, instancetype)
) WITH ( OIDS=FALSE );
GRANT ALL ON TABLE unused_box TO aurora_dbo;
GRANT SELECT, UPDATE, INSERT, DELETE, TRUNCATE ON TABLE unused_box TO ariel_rw;
GRANT SELECT ON TABLE unused_box TO ariel_ro;
