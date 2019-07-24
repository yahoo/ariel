# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from ariel import utils, LOGGER

import boto3
import datetime
import os
import sys
import time
import yaml

def load(config):

    # If local files exists and is less than a day old, just use it.
    cache_file = '/tmp/cached-locations.yaml'
    caching = utils.get_config_value(config, 'DEFAULTS', 'CACHING', False)
    mtime = 0
    if caching:
        try:
            mtime = os.stat(cache_file).st_mtime
        except FileNotFoundError:
            pass

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

        # Retrieve location to region mapping for use with ec2 pricing data
        query = ' '.join((""
            + "SELECT DISTINCT product_location, product_region "
            + "  FROM " + database + "." + table_name
            + " WHERE line_item_usage_start_date >= cast('{}' as timestamp) ".format(starttime.isoformat(' '))
            + "   AND line_item_usage_start_date < cast('{}' as timestamp) ".format(endtime.isoformat(' '))
            + "   AND product_operation = 'RunInstances' "
            ).split())
        map_id = utils.execute_athena_query(athena, staging, query)
        map_result = athena.get_query_results(QueryExecutionId=map_id)['ResultSet']['Rows']
        locations = {}
        for i in range(1, len(map_result)):
            row = map_result[i]['Data']
            location = row[0]['VarCharValue']
            region = row[1]['VarCharValue']
            locations[location] = region

        with open(cache_file, 'w') as outfile:
            yaml.dump(locations, outfile, default_flow_style=False)
        return locations

    with utils.get_read_handle(cache_file) as input:
        locations = yaml.load(input, Loader=yaml.FullLoader)
        return locations

def cli():
    import argparse, yaml
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    print(yaml.dump(load(utils.load_config(args.config)), default_flow_style=False))

if __name__ == '__main__':
    cli()
