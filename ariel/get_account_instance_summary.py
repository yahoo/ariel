# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from ariel import utils, LOGGER

import boto3
import datetime
import os
import pandas as pd
import sys
import time

def load(config):

    # If local files exists and is less than a day old, just use it.
    cache_file = '/tmp/cached-account-instance-summary.csv'
    caching = utils.get_config_value(config, 'DEFAULTS', 'CACHING', False)
    mtime = 0
    if caching:
        try:
            mtime = os.stat(cache_file).st_mtime
        except FileNotFoundError:
            mtime = 0

    if mtime > time.time() - 86400:
        LOGGER.info("Using existing cache file: " + cache_file)
    else:
        account, role = utils.get_master(config)
        region   = utils.get_config_value(config, 'ATHENA', 'AWS_REGION',
                   utils.get_config_value(config, 'DEFAULTS', 'AWS_REGION',
                                          os.environ.get('AWS_DEFAULT_REGION')))
        database = utils.get_config_value(config, 'ATHENA', 'CUR_DATABASE')
        table_name = utils.get_config_value(config, 'ATHENA', 'CUR_TABLE_NAME', 'cur')
        staging  = utils.get_config_value(config, 'ATHENA', 'STAGING',
                                          's3://aws-athena-query-results-{0}-{1}/ariel-cur-output/'.format(account, region))
        days     = utils.get_config_value(config, 'ATHENA', 'DAYS', 28)
        offset   = utils.get_config_value(config, 'ATHENA', 'OFFSET', 1)

        session = boto3.Session()
        proto, empty, staging_bucket, staging_prefix = staging.split('/', 3)

        # Assume role if needed
        if role is not None:
            session = utils.assume_role(session, role)

        # Connect to Athena
        athena = session.client('athena', region_name=region)

        # Validate database is usable
        status_id = utils.execute_athena_query(athena, staging, 'SELECT status FROM ' + database + '.cost_and_usage_data_status')

        # Row 0 is header
        status = athena.get_query_results(QueryExecutionId=status_id)['ResultSet']['Rows'][1]['Data'][0]['VarCharValue']
        if status != 'READY':
            raise Exception('Athena database not in READY status')

        # Identify start to end range query
        today = datetime.datetime.combine(datetime.datetime.today(), datetime.time.min)
        endtime = today - datetime.timedelta(days=offset)
        starttime = endtime - datetime.timedelta(days=days)

        # Download Instance and RI usage
        query = ' '.join((""
            + "  WITH preprocess AS ( "
            + "       SELECT line_item_usage_start_date AS usagestartdate, "
            + "              line_item_usage_account_id AS usageaccountid, "
            + "              line_item_availability_zone AS availabilityzone, "
            + "              CASE WHEN line_item_usage_type LIKE '%:%' THEN SPLIT(line_item_usage_type, ':')[2] "
            + "                   WHEN line_item_line_item_description LIKE '%m1.small%' THEN 'm1.small' "
            + "                   WHEN line_item_line_item_description LIKE '%m1.medium%' THEN 'm1.medium' "
            + "                   WHEN line_item_line_item_description LIKE '%m1.large%' THEN 'm1.large' "
            + "                   WHEN line_item_line_item_description LIKE '%m1.xlarge%' THEN 'm1.xlarge' "
            + "                   ELSE 'm1.error' "
            + "              END AS instancetype, "
            + "              product_tenancy AS tenancy, "
            + "              product_operating_system AS operatingsystem, "
            + "              CAST(line_item_usage_amount AS double) as usageamount, "
            + "              CASE WHEN line_item_line_item_type = 'DiscountedUsage' THEN CAST(line_item_usage_amount AS DOUBLE) ELSE 0 END as reservedamount "
            + "         FROM " + database + "." + table_name
            + "        WHERE product_operation = 'RunInstances' "
            + "          AND line_item_availability_zone != '' "
            + "          AND product_tenancy = 'Shared' "
            + " ) "
            + "SELECT usagestartdate, usageaccountid, availabilityzone, instancetype, tenancy, operatingsystem, SUM(usageamount) as instances, SUM(reservedamount) as reserved "
            + "  FROM preprocess "
            + " WHERE usagestartdate >= cast('{}' as timestamp) ".format(starttime.isoformat(' '))
            + "   AND usagestartdate < cast('{}' as timestamp) ".format(endtime.isoformat(' '))
            + " GROUP BY usagestartdate, usageaccountid, availabilityzone, instancetype, tenancy, operatingsystem "
            + " ORDER BY usagestartdate, usageaccountid, availabilityzone, instancetype, tenancy, operatingsystem "
            ).split())
        query_id = utils.execute_athena_query(athena, staging, query)
        session.client('s3').download_file(staging_bucket, '{0}{1}.csv'.format(staging_prefix, query_id), cache_file)

    result = pd.read_csv(cache_file, parse_dates=['usagestartdate'])

    LOGGER.info("Loaded {} instance summary rows".format(len(result)))
    return result


def cli():
    import argparse, yaml
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    load(utils.load_config(args.config))

if __name__ == '__main__':
    cli()
