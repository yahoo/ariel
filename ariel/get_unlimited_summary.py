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
    cache_file = '/tmp/cached-unlimited-summary.csv'
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
            + "SELECT line_item_usage_account_id AS accountid ,"
              "       product_region AS region, "
              "       lower(product_instance) AS instancetypefamily, "
              "       sum(line_item_usage_amount) AS unlimitedusageamount, "
              "       sum(line_item_unblended_cost) AS unlimitedusagecost "
                          + "  FROM " + database + ".cur "
            + " WHERE line_item_usage_type like '%CPUCredits:%' "
            + "   AND line_item_usage_start_date >= cast('{}' as timestamp) ".format(starttime.isoformat(' '))
            + "   AND line_item_usage_start_date < cast('{}' as timestamp) ".format(endtime.isoformat(' '))
            + " GROUP BY line_item_usage_account_id, product_region, lower(product_instance) "
            + " ORDER BY line_item_usage_account_id, product_region, lower(product_instance) "
            ).split())
        query_id = utils.execute_athena_query(athena, staging, query)
        session.client('s3').download_file(staging_bucket, '{0}{1}.csv'.format(staging_prefix, query_id), cache_file)

    result = pd.read_csv(cache_file)
    if len(result) == 0:
        result = pd.DataFrame(columns=['accountid', 'region', 'instancetypefamily', 'unlimitedusageamount', 'unlimitedusagecost'])

    result['accountid']            = result['accountid']           .map('{:012}'.format)
    result['unlimitedusageamount'] = result['unlimitedusageamount'].map('{:.2f}'.format)
    result['unlimitedusagecost']   = result['unlimitedusagecost']  .map('${:,.2f}'.format)
    LOGGER.info("Loaded {} unlimited rows".format(len(result)))
    return result


def cli():
    import argparse, yaml
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    unlimited = load(utils.load_config(args.config))
    unlimited.to_csv(sys.stdout)

if __name__ == '__main__':
    cli()
