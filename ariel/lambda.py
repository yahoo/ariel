# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from ariel import *

import boto3
import gzip
import io
import os
import pandas as pd
import pg8000
import ssl
import sys

def lambda_main(config):

    # TODO Check to see if we've been run recently (DB Not Ready thing)
    # TODO Check to see if our most recent summary is more recent than the database

    # TODO Regional Summary to Aurora
    # TODO UnusedBox Summary to Aurora
    # TODO Should Aurora be the storage platform?
    LOGGER.info("Loading Account Names...")
    account_names = get_account_names.load(config)
    LOGGER.info("Loaded {} accounts".format(len(account_names)))

    LOGGER.info("Loading Locations...")
    locations = get_locations.load(config)
    LOGGER.info("Loaded {} locations".format(len(locations)))

    LOGGER.info("Loading Reserved Instances...")
    ris = get_reserved_instances.load(config)
    LOGGER.info("Loaded {} RI Subcriptions".format(len(ris)))

    LOGGER.info("Loading EC2 Pricing Data...")
    pricing = get_ec2_pricing.load(config, locations = locations)
    for region in sorted(pricing):
        LOGGER.info("Loaded prices for {} instance types in {}".format(len(pricing[region]), region))

    LOGGER.info("Querying CUR data from Athena...")
    instances = get_account_instance_summary.load(config)

    LOGGER.info("Generating Reports...")
    reports = generate_reports.generate(config, instances, ris, pricing)

    LOGGER.info("Generating Unused Box report")
    if utils.get_config_value(config, 'CSV_REPORTS', 'UNUSED_BOX', '') != '':
        reports['UNUSED_BOX'] = get_unused_box_summary.load(config)

    LOGGER.info("Generating Unlimited report")
    if utils.get_config_value(config, 'CSV_REPORTS', 'UNLIMITED', '') != '':
        reports['UNLIMITED'] = get_unlimited_summary.load(config)

    LOGGER.info("Publishing Reports...")
    pgdb = utils.get_config_value(config, 'PG_REPORTS', 'DB_HOST', '')
    if pgdb != '':
        ca_cache = '/tmp/cached-rds-ca.pem'
        boto3.resource('s3').Bucket('rds-downloads').download_file('rds-ca-2019-root.pem', ca_cache)
        ssl_context = ssl.SSLContext()
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(ca_cache)
        connect_host = utils.get_config_value(config, 'PG_REPORTS', 'CONNECT_HOST', pgdb)
        token = boto3.client('rds').generate_db_auth_token(pgdb, 5432, 'ariel_rw')
        conn = pg8000.connect(host=connect_host, port=5432, ssl_context=ssl_context, database='ariel', user='ariel_rw', password=token)

    for key, report in reports.items():
        store_index = type(report.index) != pd.RangeIndex and len(report) > 0
        filename = utils.get_config_value(config, 'CSV_REPORTS', key, '')
        if filename != '':
            LOGGER.info("Writing Report {} to {}...".format(key, filename))

            # Decorate report
            if 'accountid' in report.columns and 'accountname' not in report.columns:
                accountname_column = report.columns.get_loc('accountid') + 1
                input_column = 'Account ID' if 'Account ID' in report.columns else 'accountid'
                accountname_value = report[input_column].apply(lambda x: account_names[x] if x in account_names else x)
                report.insert(accountname_column, 'accountname', accountname_value)

            # Write report
            with utils.get_temp_write_handle(filename) as output:
                report.to_csv(output, index=store_index)

        if pgdb != '':
            tablename = utils.get_config_value(config, 'PG_REPORTS', key, '')
            if tablename != '':
                LOGGER.info("Writing Report {} to {}.{}...".format(key, pgdb, tablename))
                with conn.cursor() as cursor:
                    if key == 'ACCOUNT_INSTANCE_SUMMARY':
                        start = report.reset_index()['usagestartdate'].min()
                        cursor.execute('DELETE FROM {} WHERE usagestartdate >= %s'.format(tablename), [start])
                    else:
                        cursor.execute('TRUNCATE TABLE {}'.format(tablename))

                    report_cache = '/tmp/cached-report.csv.gz'
                    with gzip.open(report_cache, 'wb') as writer:
                        report.to_csv(io.TextIOWrapper(writer, write_through=True), index=store_index)
                    with gzip.open(report_cache, 'rb') as reader:
                        cursor.execute("COPY {} FROM STDIN WITH CSV HEADER".format(tablename), stream=reader)
                    os.remove(report_cache)
                    conn.commit()
    LOGGER.info("Reports Complete")


def handler(event, context):
    # Allow for multiple configs to be processed sequentially
    # NOTE: Data caching highly recommended when using multiple configs
    configs = event['config'].split(',')
    for config in configs:
        lambda_main(utils.load_config(config))

def cli():
    import argparse
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    lambda_main(utils.load_config(args.config))

if __name__ == '__main__':
    cli()
