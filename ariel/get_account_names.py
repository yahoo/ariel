# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from ariel import utils, LOGGER
from time import sleep

import boto3
import os
import sys
import time
import yaml

def load(config):

    # If local files exists and is less than a day old, just use it.
    cache_file = '/tmp/cached-account-names.yaml'
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
        retries = utils.get_config_value(config, 'ACCOUNT_NAMES', 'RETRIES', 5)
        file     = utils.get_config_value(config, 'ACCOUNT_NAMES', 'FILE', '')

        account_names = {}
        if role != '':
            # Organizations should be queried, load that first
            session = utils.assume_role(boto3.Session(), role)
            org = session.client('organizations', region_name='us-east-1')

            rsp = org.list_accounts()
            while True:
                for account in rsp['Accounts']:
                    account_names[account['Id']] = account['Name']

                if 'NextToken' in rsp:
                    for i in range(retries):
                        try:
                            rsp = org.list_accounts(NextToken=rsp['NextToken'])
                            break
                        except ClientError as e:
                            if i == retries:
                                raise e
                            sleep(0.5 + 0.1 * i)
                    continue
                break

        if file != '':
            # Update account names with file contents
            with utils.get_read_handle(file) as f:
                account_names.update(yaml.load(f, Loader=yaml.FullLoader))

        with open(cache_file, 'w') as outfile:
            yaml.dump(account_names, outfile, default_flow_style=False)

        return account_names

    with utils.get_read_handle(cache_file) as input:
        account_names = yaml.load(input, Loader=yaml.FullLoader)
        return account_names

def cli():
    import argparse
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    print(yaml.dump(load(utils.load_config(args.config)), default_flow_style=False))

if __name__ == '__main__':
    cli()
