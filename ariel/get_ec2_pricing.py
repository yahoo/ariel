# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from ariel import utils, LOGGER

import codecs
import csv
import json
import os
import sys
import time
import yaml

try:
    from urllib.request import urlopen  # Python 3
except:
    from urllib2 import urlopen  # Python 2

LOCATIONS = {
    "Asia Pacific (Mumbai)": "ap-south-1",
    "Asia Pacific (Osaka-Local)": "ap-northeast-3",
    "Asia Pacific (Seoul)": "ap-northeast-2",
    "Asia Pacific (Singapore)": "ap-southeast-1",
    "Asia Pacific (Sydney)": "ap-southeast-2",
    "Asia Pacific (Tokyo)": "ap-northeast-1",
    "AWS GovCloud (US-East)": "us-gov-east-1",
    "AWS GovCloud (US)": "us-gov-west-1",
    "Canada (Central)": "ca-central-1",
    "China (Beijing)": "cn-north-1",
    "China (Ningxia)": "cn-northwest-1",
    "EU (Frankfurt)": "eu-central-1",
    "EU (Ireland)": "eu-west-1",
    "EU (London)": "eu-west-2",
    "EU (Paris)": "eu-west-3",
    "EU (Stockholm)": "eu-north-1",
    "South America (Sao Paulo)": "sa-east-1",
    "US East (N. Virginia)": "us-east-1",
    "US East (Ohio)": "us-east-2",
    "US West (N. California)": "us-west-1",
    "US West (Oregon)": "us-west-2"
}

def load(config, locations=LOCATIONS):

    # If local files exists and is less than a day old, just use it.
    cache_file = '/tmp/cached-ec2-pricing.json'
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
        pricing_url  = utils.get_config_value(config, 'PRICING', 'URL', 'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.csv')

        csv_reader = csv.reader(codecs.iterdecode(urlopen(pricing_url), 'utf-8'), utils.CsvDialect())

        # Find header row
        header_map = None
        while header_map is None:
            header = next(csv_reader)
            if header[0] == "SKU":
                header_map = utils.parse_header(header)

        rowcount = 0
        prices = {}
        units = {}
        for row in csv_reader:
            if not check_row(header_map, row):
                continue

            sku = row[header_map['SKU']]
            location = row[header_map['Location']]
            instanceType = row[header_map['Instance Type']]
            tenancy = row[header_map['Tenancy']]
            operatingsystem = row[header_map['Operating System']]

            # Resolve the AWS Region from location information.
            if location not in locations:
                locations[location] = utils.get_config_value(config, 'LOCATIONS', location, '')
                if locations[location] == '':
                    LOGGER.info('Skipping unknown location: {}'.format(location))
            if locations[location] == '':
                continue
            region = locations[location]

            # Populate result set
            if region not in prices:
                prices[region] = {}
            if instanceType not in prices[region]:
                prices[region][instanceType] = {}
            if tenancy not in prices[region][instanceType]:
                prices[region][instanceType][tenancy] = {}
            if operatingsystem not in prices[region][instanceType][tenancy]:
                prices[region][instanceType][tenancy][operatingsystem] = {
                    "sku": sku,
                    "reserved": {}
                }
                try:
                    units[instanceType] = float(row[header_map['Normalization Size Factor']])
                except ValueError as e:
                    print('WARNING: Invalid pricing data: {}:{} -> {}'.format(region, instanceType, sku))
                    continue

            price = prices[region][instanceType][tenancy][operatingsystem]
            if price['sku'] != sku:
                print('WARNING: Duplicate sku: {}:{} -> {} != {}'.format(region, instanceType, sku, price['sku']))
                continue

            # Add pricing data
            if row[header_map['TermType']] == 'OnDemand':
                if row[header_map['Unit']] in ('Hrs', 'Hours'):
                    price['onDemandRate'] = float(row[header_map['PricePerUnit']])
            elif row[header_map['TermType']] == 'Reserved':
                id = '{}-{}-{}'.format(row[header_map['LeaseContractLength']], row[header_map['OfferingClass']],
                                       row[header_map['PurchaseOption']])
                if id not in price['reserved']:
                    price['reserved'][id] = { 'upfront': 0.0, 'hourly': 0.0 }
                if row[header_map['Unit']] in ('Hrs', 'Hours'):
                    price['reserved'][id]['hourly'] = float(row[header_map['PricePerUnit']])
                elif row[header_map['Unit']] in ('Quantity'):
                    price['reserved'][id]['upfront'] = float(row[header_map['PricePerUnit']])

            rowcount += 1
        LOGGER.info("Loaded {} pricing rows".format(rowcount))

        # Trim useless data
        rowcount = 0
        remove = []
        for region in prices:
            for instanceType in prices[region]:
                for tenancy in prices[region][instanceType]:
                    for operatingsystem in prices[region][instanceType][tenancy]:
                        if 'onDemandRate' not in prices[region][instanceType][tenancy][operatingsystem] or \
                                len(prices[region][instanceType][tenancy][operatingsystem]['reserved']) == 0:
                            remove.append([region, instanceType, tenancy, operatingsystem])
                        else:
                            rowcount += 1
        for keys in remove:
            del prices[keys[0]][keys[1]][keys[2]][keys[3]]
        prices['units'] = units
        LOGGER.info("Loaded prices for {} instance types".format(rowcount))

        with open(cache_file, 'w') as outfile:
            json.dump(prices, outfile, indent=4)
        return prices

    with utils.get_read_handle(cache_file) as input:
        prices = json.load(input)
        return prices

def check_row(header_map, row):
    
    if row[header_map['Product Family']] not in ['Compute Instance', 'Compute Instance (bare metal)']:        
        ###################
        #
        # meckstmd: 07/25/2019
        #
        # These metal instance types have a Product Family of "Compute Instance (bare metal)"
        #     i3.metal
        #     r5.metal
        #     r5d.metal
        #     z1d.metal
        #
        # These metal instance types have a Product Family of "Compute Instance"
        #     c5.metal
        #     m5.metal
        #     m5d.metal
        #
        #  From AWS Support Case #6286484301:
        #   There is no difference in the two families apart from the ones listed in the EC2 instance types 
        #   details page (https://aws.amazon.com/ec2/instance-types/). There seems to be an overlap of some 
        #   kind when new instance types were added and that is why you see them differentiated into two families.
        #   You can ignore this difference in classification for now and once the errors are rectified at our 
        #   end, you should not see the two families.
        #
        ###################
        return False
    if row[header_map['serviceCode']] != 'AmazonEC2':
        return False
    if row[header_map['Location Type']] != 'AWS Region':
        return False
    if not row[header_map['operation']].startswith('RunInstances'):
        return False
    if row[header_map['License Model']] != 'No License required':
        return False
    if row[header_map['Pre Installed S/W']] != 'NA':
        return False
    if row[header_map['instanceSKU']] != '': # Items with instancesku are children of the item we actually want
        return False
    return True

def handler(event, context):
    pass

def cli():
    import argparse
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    print(yaml.dump(load(utils.load_config(args.config))))

if __name__ == '__main__':
    cli()
