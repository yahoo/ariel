-- Copyright 2019, Oath Inc.
-- Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
SET client_min_messages TO warning;

CREATE TABLE unused_az_ris
(
    availabilityzone  character varying(21)       NOT NULL, -- region + 1
    instancetype      character varying(15)       NOT NULL, -- r5ad.24xlarge + 2
    tenancy           character varying(9)        NOT NULL, -- [Dedicated, Host, Shared]
    operatingsystem   character varying(7)        NOT NULL, -- [Linux, RHEL, SUSE, Windows]
    min_unused_qty    double precision            NOT NULL,
    avg_unused_qty    double precision            NOT NULL,
    max_unused_qty    double precision            NOT NULL,
	PRIMARY KEY (availabilityzone, instancetype, tenancy, operatingsystem)
) WITH ( OIDS=FALSE );
GRANT ALL ON TABLE unused_az_ris TO aurora_dbo;
GRANT SELECT, UPDATE, INSERT, DELETE, TRUNCATE ON TABLE unused_az_ris TO ariel_rw;
GRANT SELECT ON TABLE unused_az_ris TO ariel_ro;
