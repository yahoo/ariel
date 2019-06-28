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
    cache_file = '/tmp/cached-reserved-instances.csv'
    caching = utils.get_config_value(config, 'DEFAULTS', 'CACHING', False)
    mtime = 0
    if caching:
        try:
            mtime = os.stat(cache_file).st_mtime
        except FileNotFoundError:
            pass

    if mtime > time.time() - 86400:
        LOGGER.info("Using existing cache file: " + cache_file)
        ris = pd.read_csv(cache_file)
    else:
        account, role = utils.get_master(config)
        region   = utils.get_config_value(config, 'RESERVED_INSTANCES', 'AWS_REGION',
                   utils.get_config_value(config, 'DEFAULTS', 'AWS_REGION',
                                          os.environ.get('AWS_DEFAULT_REGION')))
        # start date cannot be after 2 days ago for GetReservationUtilization
        monthend = datetime.date.today()
        monthstart = (datetime.date.today() - datetime.timedelta(days=31))

        ris = []
        if role != '':
            session = utils.assume_role(boto3.Session(), role)
            ce = session.client('ce', region_name=region)

            rsp = ce.get_reservation_utilization(
                TimePeriod={ "Start": str(monthstart), "End": str(monthend) },
                GroupBy=[{ "Type": "DIMENSION", "Key": "SUBSCRIPTION_ID" }]
            )

            while True:
                groups = rsp['UtilizationsByTime'][0]['Groups']
                for row in groups:
                    # Make sure to only capture active RIs
                    endDate = datetime.datetime.strptime(row['Attributes']['endDateTime'], "%Y-%m-%dT%H:%M:%S.000Z")
                    if endDate.date() > datetime.date.today():
                        operatingSystem = 'Linux' if row['Attributes']['platform'] == 'Linux/UNIX' else row['Attributes']['platform'] # for CUR compatibility
                        ri = {
                            'accountid': int(row['Attributes']['accountId']),
                            'accountname': row['Attributes']['accountName'],
                            'reservationid': row['Attributes']['leaseId'],
                            'subscriptionid': row['Attributes']['subscriptionId'],
                            'startdate': row['Attributes']['startDateTime'],
                            'enddate': row['Attributes']['endDateTime'],
                            'state': row['Attributes']['subscriptionStatus'],
                            'quantity': int(row['Attributes']['numberOfInstances']),
                            'availabilityzone': row['Attributes']['availabilityZone'],
                            'region': row['Attributes']['region'],
                            'instancetype': row['Attributes']['instanceType'],
                            'paymentoption': row['Attributes']['subscriptionType'],
                            'tenancy': row['Attributes']['tenancy'],
                            'operatingsystem': operatingSystem,
                            'amortizedhours': int(row['Utilization']['PurchasedHours']),
                            'amortizedupfrontprice': float(row['Utilization']['AmortizedUpfrontFee']),
                            'amortizedrecurringfee': float(row['Utilization']['AmortizedRecurringFee']),
                            'offeringclass': row['Attributes']['offeringType'],
                            'scope': row['Attributes']['scope'],
                        }
                        ris.append(ri)

                if 'NextToken' in rsp:
                    rsp = ce.get_reservation_utilization(NextToken=rsp['NextToken'])
                    continue
                break

        ris = pd.DataFrame.from_records(ris)
        ris.to_csv(cache_file, index=False)

    LOGGER.info("Loaded {} reserved instances".format(len(ris)))
    return ris


def cli():
    import argparse, csv
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    ris = load(utils.load_config(args.config))
    ris.to_csv(sys.stdout)

if __name__ == '__main__':
    cli()
