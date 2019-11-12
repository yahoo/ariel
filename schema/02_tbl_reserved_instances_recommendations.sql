-- Copyright 2019, Oath Inc.
-- Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
SET client_min_messages TO warning;

CREATE TABLE reserved_instances_recommendations
(
    "Account ID"          character(12)               NOT NULL,
    "Scope"               character varying(16)       NOT NULL, -- [Region, Availabilty Zone]
    "Region"              character varying(20)       NOT NULL, -- ap-northeast-3 + 6
    "Instance Type"       character varying(15)       NOT NULL, -- r5ad.24xlarge + 2
    "Operating System"    character varying(23)       NOT NULL, -- [Linux/UNIX (Amazon VPC), RHEL, SUSE, Windows]
    "Tenancy"             character varying(9)        NOT NULL, -- [Dedicated, Host, Shared]
    "Offering Class"      character varying(11)       NOT NULL, -- [classic, convertible]
    "Payment Type"        character varying(15)       NOT NULL, -- [All Upfront, Partial Upfront, No Upfront]
    "Term"                smallint                    NOT NULL, -- [12, 36]
    "Quantity"            smallint                    NOT NULL,
    accountid             character(19)               NOT NULL,
    accountname           character varying(64)       NOT NULL,
    family                character varying(5)        NOT NULL, -- r5ad + 1
    units                 double precision            NOT NULL,
    "ri upfront cost"     money                       NOT NULL,
    "ri total cost"       money                       NOT NULL,
    "ri savings"          money                       NOT NULL,
    "ondemand value"      money                       NOT NULL,
    algorithm             character varying(12)       NOT NULL  -- [CONSERVATIVE, DEFAULT, AGGRESSIVE]
    -- PRIMARY KEY is not necessarily possible
    -- Table should be small enough to not require indexes
) WITH ( OIDS=FALSE );
GRANT ALL ON TABLE reserved_instances_recommendations TO aurora_dbo;
GRANT SELECT, UPDATE, INSERT, DELETE, TRUNCATE ON TABLE reserved_instances_recommendations TO ariel_rw;
GRANT SELECT ON TABLE reserved_instances_recommendations TO ariel_ro;
