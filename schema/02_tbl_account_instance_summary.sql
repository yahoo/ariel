-- Copyright 2019, Oath Inc.
-- Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
SET client_min_messages TO warning;

CREATE TABLE account_instance_summary
(
    usagestartdate    timestamp without time zone NOT NULL,
    usageaccountid    character(12)               NOT NULL,
    region            character varying(20)       NOT NULL, -- ap-northeast-3 + 6
    availabilityzone  character varying(21)       NOT NULL, -- region + 1
    instancefamily    character varying(5)        NOT NULL, -- r5ad + 1
    instancetype      character varying(15)       NOT NULL, -- r5ad.24xlarge + 2
    tenancy           character varying(9)        NOT NULL, -- [Dedicated, Host, Shared]
    operatingsystem   character varying(7)        NOT NULL, -- [Linux, RHEL, SUSE, Windows]
    instances         double precision            NOT NULL,
    reserved          double precision            NOT NULL,
    instance_units    double precision            NOT NULL,
    reserved_units    double precision            NOT NULL,
	PRIMARY KEY (usagestartdate, usageaccountid, availabilityzone, instancetype)
) WITH ( OIDS=FALSE );
GRANT ALL ON TABLE account_instance_summary TO aurora_dbo;
GRANT SELECT, UPDATE, INSERT, DELETE ON TABLE account_instance_summary TO ariel_rw;
GRANT SELECT ON TABLE account_instance_summary TO ariel_ro;
