# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from ariel import utils, LOGGER
from datetime import timedelta

import numpy as np
import pandas as pd
import operator
import sys

# Two reports to be generated:
# 1) By region / family - % chance a new instance is likely to be covered by an RI
#    Report 2 .groupby() will calculate this
# 2) By time of week / region / family - % chance a new instance is likely to be covered
# Needs for both:
#    Unused RIs -- If unused, chance = 100%
#    RIs not used by purchasing account -- If no unused, chance = unused-by-purchasing/not-covered-by-purchasing
def generate(config, instances, ris, pricing):

    def get_units(instancetype):
        try:
            return pricing['units'][instancetype]
        except KeyError as e:
            if '.' in instancetype:
                raise e
            for key in pricing['units']:
                if key.endswith('.' + instancetype):
                    return pricing['units'][key]
            raise e

    # Make sure we have a reasonable about of data
    if instances['usagestartdate'].max() - instances['usagestartdate'].min() < timedelta(days=14):
        raise ValueError('Insufficient Data')

    # Preaggregate some data
    timerange = instances['usagestartdate'].unique()

    # Add some additional data to instances
    hourofweek_column = instances.columns.get_loc('usagestartdate') + 1
    hourofweek_value = instances['usagestartdate'].dt.dayofweek * 24 + instances['usagestartdate'].dt.hour
    instances.insert(hourofweek_column, 'hourofweek', hourofweek_value)

    region_column = instances.columns.get_loc('availabilityzone')
    region_value = instances['availabilityzone'].str[:-1]
    instances.insert(region_column, 'region', region_value)

    family_column = instances.columns.get_loc('instancetype')

    # meckstmd:07/29/2019 - Metal RIs are no different than regular RIs - they are a family with a normalization factor
    #  for example, i3.metal is equivalent to i3.16xlarge.  See https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/apply_ri.html 
    #family_value = instances['instancetype'].apply(lambda x: x if x.endswith('.metal') else x.split('.')[0])
    family_value = instances['instancetype'].apply(lambda x: x.split('.')[0])
    instances.insert(family_column, 'instancetypefamily', family_value)

    # Amazon still hasn't fixed g4dn, so we need to filter out instance types and RIs that we don't have size data about.
    instances = instances[instances.instancetype.isin(pricing['units'].keys())].reset_index(drop=True)
    ris = ris[ris.instancetype.isin(pricing['units'].keys())].reset_index(drop=True)

    # Filter out instances and RIs we're not interested in
    skip_accounts = utils.get_config_value(config, 'RI_PURCHASES', 'SKIP_ACCOUNTS', '').split(' ')
    instances = instances[~instances.usageaccountid.isin(skip_accounts)].reset_index(drop=True)
    ris = ris[~ris.accountid.isin(skip_accounts)].reset_index(drop=True)

    include_accounts = utils.get_config_value(config, 'RI_PURCHASES', 'INCLUDE_ACCOUNTS', '').split(' ')
    if (include_accounts[0] != ''):
        instances = instances[instances.usageaccountid.isin(include_accounts)].reset_index(drop=True)
        ris = ris[ris.accountid.isin(include_accounts)].reset_index(drop=True)

    instance_units_column = instances.columns.get_loc('instances') + 2
    units_value = instances['instancetype'].apply(get_units) * instances['instances']
    instances.insert(instance_units_column, 'instance_units', units_value)

    reserved_units_column = instances.columns.get_loc('reserved') + 2
    units_value = instances['instancetype'].apply(get_units) * instances['reserved']
    instances.insert(reserved_units_column, 'reserved_units', units_value)

    # Add some additional data to ris
    family_column = ris.columns.get_loc('instancetype') + 1

    # meckstmd:07/29/2019 - Metal RIs are no different than regular RIs - they are a family with a normalization factor
    #  for example, i3.metal is equivalent to i3.16xlarge.  See https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/apply_ri.html     
    #family_value = ris['instancetype'].apply(lambda x: x if x.endswith('.metal') else x.split('.')[0])
    family_value = ris['instancetype'].apply(lambda x: x.split('.')[0])
    ris.insert(family_column, 'instancetypefamily', family_value)

    units_column = ris.columns.get_loc('quantity') + 1
    units_value = ris['instancetype'].apply(get_units) * ris['quantity']
    ris.insert(units_column, 'units', units_value)

    # Create aggregates for faster processing
    az_instance_groups = instances.groupby(['availabilityzone', 'instancetype', 'tenancy', 'operatingsystem'])
    az_account_instance_groups = instances.groupby(az_instance_groups.keys + ['usageaccountid'])
    region_instance_groups = instances.groupby(['region', 'instancetypefamily', 'tenancy', 'operatingsystem'])
    region_account_instance_groups = instances.groupby(region_instance_groups.keys + ['usageaccountid'])
    ri_groups = ris.groupby(region_instance_groups.keys + ['scope'])

    # Reference Lookup
    all_sizes = instances['instancetype'].apply(lambda x: x.split('.')[1]).unique()
    reference_sizes = {}
    for family in ris['instancetypefamily'].unique():
        for size in all_sizes:
            if "{}.{}".format(family, size) in pricing['us-east-1']:
                reference_sizes[family] = size
                break

    # Reports
    unused_az_ris = pd.DataFrame(columns=az_instance_groups.keys + ['min_unused_qty', 'avg_unused_qty', 'max_unused_qty'])
    ri_hourly_usage_report = pd.DataFrame(columns=region_instance_groups.keys + ['hourofweek'] +
            ['total_ri_units', 'total_instance_units', 'floating_ri_units', 'floating_instance_units', 'unused_ri_units', 'coverage_chance'])
    ri_purchases = pd.DataFrame(columns=['Account ID', 'Scope', 'Region / AZ', 'Instance Type', 'Operating System',
            'Tenancy', 'Offering Class', 'Payment Type', 'Term', 'Quantity', 'accountid', 'family', 'units',
            'ri upfront cost', 'ri total cost', 'ri savings', 'ondemand value', 'algorithm'])

    # NOTE: For usage values, AZ usage is booked by quantity (instances), Region usage is booked by units.

    # Iterate by Union of (Region Instance Groups and RI Groups)
    for group in sorted(list(set(region_instance_groups.groups.keys()) |
                             set(ris.groupby(region_instance_groups.keys).groups.keys()))):
    # for group in [('ap-northeast-1', 'c4', 'Shared', 'Linux')]:
        region, family, tenancy, operatingsystem = group
        LOGGER.debug("Evaluting {:>14}:{:3} ({}, {})".format(region, family, tenancy, operatingsystem))

        if region not in pricing:
            LOGGER.warning("Skipping region {} due to missing pricing information".format(region))
            continue

        # Account for In-Account AZ RI usage
        # In-Account RI usage only needs to be counted against Regional Usage for accuracy
        try:
            az_ris = ri_groups.get_group(group + tuple(['Availability Zone']))
        except KeyError:
            az_ris = pd.DataFrame(columns=ris.columns)
        az_account_hour_ri_usage = pd.DataFrame(columns=az_account_instance_groups.keys + ['hourofweek', 'instances'])
        region_account_hour_ri_usage = pd.DataFrame(columns=region_account_instance_groups.keys + ['hourofweek', 'instance_units'])

        for index, az_ri in az_ris.iterrows():
            LOGGER.debug("Evaluating In-Account AZ RI: {}:{} {} x{}".format(az_ri['accountid'], az_ri['availabilityzone'],
                                                                 az_ri['instancetype'], az_ri['quantity']))

            try:
                group_key = (az_ri['availabilityzone'], az_ri['instancetype'], tenancy, operatingsystem, az_ri['accountid'])
                az_account_instance_group = az_account_instance_groups.get_group(group_key)
            except KeyError:
                continue

            # Straight to hourofweek average, since there should not be multiple rows per usagestartdate
            in_account_usage = az_account_instance_group.groupby(['hourofweek'])['instances'].mean()

            # Account for already assigned usage from previously evaluated AZ RIs
            in_account_assigned = az_account_hour_ri_usage[
                (az_account_hour_ri_usage['availabilityzone'] == az_ri['availabilityzone']) &
                (az_account_hour_ri_usage['instancetype'] == az_ri['instancetype']) &
                (az_account_hour_ri_usage['usageaccountid'] == az_ri['accountid'])
                ].groupby('hourofweek')['instances'].sum()
            if len(in_account_assigned) > 0:
                in_account_usage -= in_account_assigned

            in_account_used = np.minimum(in_account_usage, az_ri['quantity'])

            # Build assignment usage rows
            usage_keys = pd.DataFrame([group_key], columns=az_account_instance_groups.keys)
            usage_data = pd.DataFrame({'key': 1, 'hourofweek': in_account_used.index, 'instances': in_account_used.values})
            usage = usage_keys.assign(key=1).merge(usage_data, on='key').drop('key', 1)
            LOGGER.debug("In-Account Assigned AZ Usage:\n" + str(usage.head()))
            az_account_hour_ri_usage = az_account_hour_ri_usage.append(usage, ignore_index=True)

            # Build regional usage rows
            usage_keys = pd.DataFrame([group + tuple([az_ri['accountid']])], columns=region_account_instance_groups.keys)
            usage_data = pd.DataFrame({'key': 1, 'hourofweek': in_account_used.index,
                                       'instance_units': in_account_used.values * get_units(az_ri['instancetype'])})
            usage = usage_keys.assign(key=1).merge(usage_data, on='key').drop('key', 1)
            LOGGER.debug("In-Account Regional Assigned AZ Usage:\n" + str(usage.head()))
            region_account_hour_ri_usage = region_account_hour_ri_usage.append(usage, ignore_index=True)

        # Account for Cross-Account AZ RI Usage
        # To simplify analysis, treat in-account and cross-account identically since we only report unused AZ RIs
        az_ris = az_ris.groupby(['availabilityzone', 'instancetype'])

        # for index, az_ri in az_ris.iterrows():
        for az_group in az_ris.groups.keys():
            availabilityzone, instancetype = az_group
            quantity = az_ris.get_group(az_group)['quantity'].sum()
            LOGGER.debug("Evaluating Cross-Account AZ RI: {} {} x{}".format(availabilityzone, instancetype, quantity))
            try:
                group_key = (availabilityzone, instancetype, tenancy, operatingsystem)
                az_instance_group = az_instance_groups.get_group(group_key)
            except KeyError:
                continue

            # Aggregate by hour before hourofweek
            total_usage = az_instance_group.groupby(['usagestartdate', 'hourofweek'])['instances'].sum(). \
                groupby(['hourofweek']).mean()

            # No pre-assigned usage since individual RI subscriptions are getting bundled
            total_used = np.minimum(total_usage, quantity)

            # Add to regional usage for purchase recommendations
            usage_keys = pd.DataFrame([group + tuple(['000000000000'])], columns=region_account_instance_groups.keys)
            usage_data = pd.DataFrame({'key': 1, 'hourofweek': total_used.index,
                                       'instance_units': total_used.values * get_units(az_ri['instancetype'])})
            usage = usage_keys.assign(key=1).merge(usage_data, on='key').drop('key', 1)
            LOGGER.debug("Cross-Account Regional Assigned AZ Usage:\n" + str(usage.head()))
            region_account_hour_ri_usage = region_account_hour_ri_usage.append(usage, ignore_index=True)

            unused = quantity - total_used
            if unused.max() > 0:
                unused_az_ri_row = {
                    'availabilityzone': availabilityzone,
                    'instancetype': instancetype,
                    'tenancy': tenancy,
                    'operatingsystem': operatingsystem,
                    'min_unused_qty': unused.min(),
                    'avg_unused_qty': unused.mean(),
                    'max_unused_qty': unused.max(),
                }
                unused_az_ris = unused_az_ris.append(unused_az_ri_row, ignore_index=True)
                LOGGER.debug("Unused AZ RIs:\n" + str(unused_az_ri_row))

        # Account for In-Account Region RI Usage
        # In-Account Region RI usage only needed to calculate RI Float
        try:
            region_ris = ri_groups.get_group(group + tuple(['Region']))
        except KeyError:
            region_ris = pd.DataFrame(columns=ris.columns)
        region_hour_ri_usage = pd.DataFrame(columns=region_instance_groups.keys + ['hourofweek', 'units'])

        account_region_ris = region_ris.groupby(['accountid'])
        for accountid in account_region_ris.groups.keys():
            ri_units = account_region_ris.get_group(accountid)['units'].sum()
            LOGGER.debug("Evaluating In-Account Region RI: {}:{} {} x{}".format(accountid, region, family, ri_units))

            try:
                group_key = (region, family, tenancy, operatingsystem, accountid)
                region_account_instance_group = region_account_instance_groups.get_group(group_key)
            except KeyError:
                continue

            # Aggregate by hour before hourofweek
            in_account_usage = region_account_instance_group.groupby(['usagestartdate', 'hourofweek']) \
                    ['instance_units'].sum().groupby(['hourofweek']).mean()

            # Account for already assigned usage from AZ RIs
            in_account_assigned = region_account_hour_ri_usage[
                (region_account_hour_ri_usage['usageaccountid'] == accountid)
                ].groupby('hourofweek')['instance_units'].sum()
            if len(in_account_assigned) > 0:
                in_account_usage -= in_account_assigned

            in_account_used = np.minimum(in_account_usage, ri_units)

            # Fix partial indexes
            in_account_used = in_account_used.reindex(range(168), copy=False, fill_value=0.0)

            # Build usage rows
            usage_keys = pd.DataFrame([group], columns=region_instance_groups.keys)
            usage_data = pd.DataFrame({'key': 1, 'hourofweek': in_account_used.index, 'units': in_account_used.values})
            usage = usage_keys.assign(key=1).merge(usage_data, on='key').drop('key', 1)
            LOGGER.debug("In-Account Assigned Region Usage:\n" + str(usage.head()))
            region_hour_ri_usage = region_hour_ri_usage.append(usage, ignore_index=True)

        try:
            region_instance_group = region_instance_groups.get_group(group)
        except:
            # This is a bit heavy, but it shouldn't be called frequently.
            # Create a new DataFrame that has the right structure
            region_instance_group = region_instance_groups.get_group(list(region_instance_groups.groups.keys())[0])
            region_instance_group = region_instance_group.assign(instances=0)
            region_instance_group = region_instance_group.assign(instance_units=0)
            region_instance_group = region_instance_group.assign(reserved=0)

        # Account for Cross-Account Region RI Usage
        if len(region_ris) == 0:
            ri_units = 0
        else:
            ri_units = region_ris['units'].sum()
            LOGGER.debug("Evaluating Cross-Account Region RI: {} {} x{}".format(region, family, ri_units))

            # Aggregate by hour before hourofweek
            total_usage = region_instance_group.groupby(['usagestartdate', 'hourofweek']) \
                ['instance_units'].sum().groupby(['hourofweek']).mean()

            # In-Account usage to calculate float
            in_account_usage = region_hour_ri_usage.groupby(['hourofweek'])['units'].sum()
            if len(in_account_usage) == 0:
                in_account_usage = pd.Series(0, index=total_usage.index)

            # Floating RIs
            floating_ri_units = ri_units - in_account_usage

            # Instances eligible for float
            floating_instance_units = total_usage - in_account_usage

            # Unused RIs
            unused_ri_units = np.maximum(ri_units - total_usage, 0)

            # % Change a new instance will be covered
            coverage_chance = np.minimum(floating_ri_units / floating_instance_units * 100, 100)

            # Build report rows
            usage_keys = pd.DataFrame([group], columns=region_instance_groups.keys)
            usage_data = pd.DataFrame({
                'key': 1,
                'hourofweek': total_usage.index,
                'total_ri_units': ri_units,
                'total_instance_units': total_usage.values,
                'floating_ri_units': floating_ri_units.values,
                'floating_instance_units': floating_instance_units.values,
                'unused_ri_units': unused_ri_units.values,
                'coverage_chance': coverage_chance.values,
            })
            usage = usage_keys.assign(key=1).merge(usage_data, on='key').drop('key', 1)
            LOGGER.debug("Cross-Account Region Usage Report:\n" + str(usage.head()))
            ri_hourly_usage_report = ri_hourly_usage_report.append(usage, ignore_index=True)

        # RI Utilization Evaluation complete.  Evaluate Purchase recommendations
        if region_instance_group['instance_units'].sum() > 0:

            # Calculate usage slope to determine purchase aggressiveness

            # First filter data to reduce noise.
            region_hourly_usage = region_instance_group.groupby(['usagestartdate', 'hourofweek'])['instance_units'].sum()
            threshold = int(utils.get_config_value(config, 'RI_PURCHASES', 'FILTER_THRESHOLD', 3))
            signal = region_hourly_usage.values.copy()
            delta = np.abs(signal - np.mean(signal))
            median_delta = np.median(delta)
            if median_delta > 0:
                mask = (delta / float(median_delta)) > threshold
                signal[mask] = np.median(signal)

            # Least squares fit
            ts = region_hourly_usage.reset_index()['usagestartdate'].apply(lambda x: x.timestamp())
            A = np.vstack([ts, np.ones(len(ts))]).T
            y = signal
            m, c = np.linalg.lstsq(A, y, rcond=None)[0]
            slope = m * 86400

            # Determine RI Algorithm
            algorithm = 'DEFAULT'
            aggressive_threshold = utils.get_config_value(config, 'RI_PURCHASES', 'AGGRESSIVE_THRESHOLD', 'NONE')
            try:
                if slope >= float(aggressive_threshold):
                    algorithm = 'AGGRESSIVE'
            except ValueError:
                pass

            conservative_threshold = utils.get_config_value(config, 'RI_PURCHASES', 'CONSERVATIVE_THRESHOLD', 'NONE')
            try:
                if slope <= float(conservative_threshold):
                    algorithm = 'CONSERVATIVE'
            except ValueError:
                pass

            # Subtract AZ RI Usage from instances since we for the most part can completely ignore them.
            az_assigned = region_account_hour_ri_usage.groupby('hourofweek')['instance_units'].sum()
            if len(az_assigned) > 0:
                region_hourly_usage -= az_assigned

            # Determine our purchase size for this family
            types = [key for key in pricing[region].keys() if key.startswith(family + '.')]
            type_units = {key: get_units(key) for key in types}
            desired_size = utils.get_config_value(config, 'RI_PURCHASES', 'RI_SIZE', 'largest')
            if desired_size == 'largest':
                purchase_size, purchase_size_units = max(type_units.items(), key=operator.itemgetter(1))
            elif desired_size == 'smallest':
                purchase_size, purchase_size_units = min(type_units.items(), key=operator.itemgetter(1))
            else:
                desired_size_units = get_units(desired_size)
                filtered_units = {k: v for k, v in type_units.items() if v <= desired_size_units}
                if len(filtered_units) > 0:
                    purchase_size, purchase_size_units = max(filtered_units.items(), key=operator.itemgetter(1))
                else:
                    purchase_size, purchase_size_units = min(type_units.items(), key=operator.itemgetter(1))

            # Get RI Details
            term = utils.get_config_value(config, 'RI_PURCHASES', 'RI_TERM')
            term_h = int(term) * 730
            term_y = '3yr' if term == 36 else '1yr'
            if region not in pricing or purchase_size not in pricing[region] or \
                    tenancy not in pricing[region][purchase_size] or \
                    operatingsystem not in pricing[region][purchase_size][tenancy]:
                LOGGER.error('Missing RI Pricing data for {}:{}:{}:{}'.format(region, purchase_size, tenancy, operatingsystem))
                continue

            for offering in ['standard', 'convertible']:
                # Get RI Pricing Data
                rates = pricing[region][purchase_size][tenancy][operatingsystem]
                od_rate = rates['onDemandRate']
                ri_rate = None
                option = utils.get_config_value(config, 'RI_PURCHASES', 'RI_OPTION')
                for o in (option, 'No Upfront', 'Partial Upfront', 'All Upfront'):
                    ri_key = '{}-{}-{}'.format(term_y, offering, o)
                    if ri_key in rates['reserved']:
                        ri_rate = rates['reserved'][ri_key]
                        option = o
                        break
                if ri_rate is None:
                    LOGGER.error('Missing RI Pricing data(2) for {}:{}'.format(region, purchase_size))
                    continue

                for slush in [False, True]:
                    utilization_key = "{}_{}_{}UTIL_TARGET".format(offering.upper(), algorithm, 'SLUSH_' if slush else '')
                    target_utilization = utils.get_config_value(config, 'RI_PURCHASES', utilization_key, 'NONE')

                    if target_utilization == 'BREAK_EVEN':
                        target_utilization = (ri_rate['upfront'] + ri_rate['hourly'] * term_h) / (od_rate * term_h) * 100
                                # RI Total Cost / OnDemand Cost = Break Even Utilization

                    LOGGER.debug("Purchase: {:>14}:{:3} {:11} {:5}: slope={} algo={} target={}". format(region, family,
                              offering, 'slush' if slush else 'acct', slope, algorithm, target_utilization))

                    if target_utilization == 'NONE':
                        continue

                    # Subtract existing RIs from usage to determine demand
                    demand_hourly_usage = region_hourly_usage - ri_units

                    # Edge case fix here...
                    # If usage only exists for a part of the timerange, it's percentile will be incorrect
                    # unless we fill it with zeros.
                    demand_hourly_usage = demand_hourly_usage.reset_index(level=1, drop=True).reindex(timerange, fill_value=0.0)

                    # Subtract previously recommended RIs from usage
                    prior_ri_units = ri_purchases[
                        (ri_purchases['Region / AZ'] == region) &
                        (ri_purchases['family'] == family) &
                        (ri_purchases['Operating System'] == operatingsystem) &
                        (ri_purchases['Tenancy'] == tenancy)]['units'].sum()
                    demand_hourly_usage -= prior_ri_units

                    # Evalute Demand
                    demand_units = sorted(demand_hourly_usage.values)[int(len(demand_hourly_usage.values) *
                                                                          (100 - target_utilization) / 100)]
                    demand_units -= demand_units % purchase_size_units
                    if demand_units < purchase_size_units:
                        LOGGER.debug("Purchase: {:>14}:{:3} : No additional RIs required".format(region, family))
                    else:
                        # Recommend purchases in accounts with the most uncovered demand

                        # Calculate per-account demand (single number at percentile)
                        if slush:
                            account_demand = pd.DataFrame({
                                'accountid': utils.get_config_value(config, 'RI_PURCHASES', 'SLUSH_ACCOUNT'),
                                'units': demand_units,
                            }, index=[0])
                        else:
                            # Edge case fix here...
                            # If an account only has usage for a part of the window, it's percentile will be incorrect
                            # unless we fill the timerange with zeros.
                            idx = pd.merge(
                                pd.DataFrame({'key': 1, 'usageaccountid': region_instance_group['usageaccountid'].unique()}),
                                pd.DataFrame({'key': 1, 'usagestartdate': timerange}),
                                on='key')[['usageaccountid', 'usagestartdate']]
                            account_demand = region_instance_group.groupby(['usageaccountid', 'usagestartdate']) \
                                ['instance_units'].sum().reindex(idx, fill_value=0.0).groupby('usageaccountid'). \
                                agg(lambda x: np.percentile(x, q=100 - target_utilization))

                            # subtract in-account RIs
                            account_ris = region_ris.groupby(['accountid'])['units'].sum()
                            account_demand = account_demand.subtract(account_ris, fill_value = 0)
                            account_demand = pd.DataFrame({'accountid': account_demand.index, 'units': account_demand.values})

                            # Noramlize to purchase units
                            account_demand['units'] -= account_demand['units'] % purchase_size_units

                            # Filter for positive demand
                            account_demand = account_demand[account_demand['units'] > 0]

                            # subtract from bottom to allow equal float opportunity
                            while account_demand['units'].sum() > demand_units + len(account_demand) * purchase_size_units:
                                excess_qty_per_account = int((account_demand['units'].sum() - demand_units) / purchase_size_units / len(account_demand))
                                account_demand['units'] -= excess_qty_per_account * purchase_size_units
                                account_demand = account_demand[account_demand['units'] > 0]

                            # Consistently distribute stragglers
                            if account_demand['units'].sum() > demand_units:
                                excess_qty = int((account_demand['units'].sum() - demand_units) / purchase_size_units)
                                sorted_accounts = account_demand.sort_values(['units', 'accountid'])
                                delta = pd.Series([purchase_size_units] * excess_qty + [0] * (len(account_demand) - excess_qty),
                                                  index=sorted_accounts.index)
                                account_demand['units'] -= delta
                                account_demand = account_demand[account_demand['units'] > 0]

                        # Build report rows
                        quantity = (account_demand['units'] / purchase_size_units).astype(int)
                        purchases = pd.DataFrame({
                            'Account ID': account_demand['accountid'].apply(lambda x: '{0:012}'.format(x)),
                            'Scope': 'Region',
                            'Region / AZ': region,
                            'Instance Type': purchase_size,
                            'Operating System': 'Linux/UNIX (Amazon VPC)' if operatingsystem == 'Linux' else operatingsystem,
                            'Tenancy': tenancy,
                            'Offering Class': offering,
                            'Payment Type': option,
                            'Term': term,
                            'Quantity': quantity,
                            'accountid': account_demand['accountid'].apply(lambda x: '="{0:012}"'.format(x)),
                            'family': family,
                            'units': account_demand['units'].astype(int),
                            'ri upfront cost': quantity * ri_rate['upfront'],
                            'ri total cost': quantity * (ri_rate['upfront'] + ri_rate['hourly'] * term_h),
                            'ri savings': quantity * ((od_rate - ri_rate['hourly']) * term_h - ri_rate['upfront']),
                            'ondemand value': quantity * od_rate * term_h,
                            'algorithm': algorithm
                        })
                        LOGGER.debug("Purchases:\n" + str(purchases.head()))
                        ri_purchases = ri_purchases.append(purchases, ignore_index=True)

                        # Assign to top until filly assigned
                        LOGGER.debug("Purchase: {:>14}:{:3} : type={} demand={}, recommend={} in {} accounts".
                                    format(region, family, purchase_size, demand_units, account_demand['units'].sum(), len(account_demand)))

    # GroupBy to assign appropriate index columns
    unused_az_ris = unused_az_ris.groupby(az_instance_groups.keys).sum()
    ri_hourly_usage_report = ri_hourly_usage_report.groupby(region_instance_groups.keys + ['hourofweek']).sum(numeric_only=None)
    instances = instances.drop('hourofweek', 1)

    # https://github.com/yahoo/ariel/issues/8: this is necessary if the accounts have not purchased any RIs
    if (len(ri_hourly_usage_report) == 0):
        ri_hourly_usage_report = pd.DataFrame(columns=['region', 'instancetypefamily', 'tenancy', 'operatingsystem',
                                              'hourofweek', 'total_ri_units', 'total_instance_units',
                                              'floating_ri_units', 'floating_instance_units', 'unused_ri_units',
                                              'coverage_chance'])
        ri_usage_report = pd.DataFrame(columns=['region', 'instancetypefamily', 'tenancy', 'operatingsystem',
                                                'total_ri_units', 'total_instance_units', 'floating_ri_units',
                                                'floating_instance_units', 'unused_ri_units', 'coverage_chance',
                                                'xl_effective_rate', 'monthly_ri_cost', 'monthly_od_cost',
                                                'monthly_ri_savings'])
    else:
        # Build RI Usage report with Actual cost benefit
        ri_usage_report = ri_hourly_usage_report.groupby(region_instance_groups.keys).mean()
        ri_cost = ris.groupby(region_instance_groups.keys)['amortizedupfrontprice'].sum() + ris.groupby(region_instance_groups.keys)['amortizedrecurringfee'].sum()
        od_cost = ri_usage_report.apply(lambda x: 720 * pricing[x.name[0]]["{}.{}".format(x.name[1], reference_sizes[x.name[1]])][x.name[2]][x.name[3]]['onDemandRate'] *
                                        min(x['total_ri_units'], x['total_instance_units']) / get_units(x.name[1] + '.' + reference_sizes[x.name[1]]),
                                        axis=1)
        xl_effective_rate = ((od_cost - ri_cost) * (100 - ri_usage_report['coverage_chance']) / 100 + ri_cost) / 720 / ri_usage_report['total_ri_units'] * 8
        ri_usage_report.insert(len(ri_usage_report.columns), 'xl_effective_rate', xl_effective_rate)
        ri_usage_report.insert(len(ri_usage_report.columns), 'monthly_ri_cost', ri_cost)
        ri_usage_report.insert(len(ri_usage_report.columns), 'monthly_od_cost', od_cost)
        ri_usage_report.insert(len(ri_usage_report.columns), 'monthly_ri_savings', od_cost - ri_cost)

        # Apply some column formats
        ri_hourly_usage_report['total_ri_units']          = ri_hourly_usage_report['total_ri_units']         .map('{:.0f}'.format)
        ri_hourly_usage_report['total_instance_units']    = ri_hourly_usage_report['total_instance_units']   .map('{:.0f}'.format)
        ri_hourly_usage_report['floating_ri_units']       = ri_hourly_usage_report['floating_ri_units']      .map('{:.0f}'.format)
        ri_hourly_usage_report['floating_instance_units'] = ri_hourly_usage_report['floating_instance_units'].map('{:.0f}'.format)
        ri_hourly_usage_report['unused_ri_units']         = ri_hourly_usage_report['unused_ri_units']        .map('{:.0f}'.format)
        ri_hourly_usage_report['coverage_chance']         = ri_hourly_usage_report['coverage_chance']        .map('{:.2f}'.format)
        ri_usage_report['total_ri_units']          = ri_usage_report['total_ri_units']         .map('{:.0f}'.format)
        ri_usage_report['total_instance_units']    = ri_usage_report['total_instance_units']   .map('{:.0f}'.format)
        ri_usage_report['floating_ri_units']       = ri_usage_report['floating_ri_units']      .map('{:.0f}'.format)
        ri_usage_report['floating_instance_units'] = ri_usage_report['floating_instance_units'].map('{:.0f}'.format)
        ri_usage_report['unused_ri_units']         = ri_usage_report['unused_ri_units']        .map('{:.0f}'.format)
        ri_usage_report['coverage_chance']         = ri_usage_report['coverage_chance']        .map('{:.2f}'.format)
        ri_usage_report['xl_effective_rate']       = ri_usage_report['xl_effective_rate']      .map('${:,.4f}'.format)
        ri_usage_report['monthly_ri_cost']         = ri_usage_report['monthly_ri_cost']        .map('${:,.2f}'.format)
        ri_usage_report['monthly_od_cost']         = ri_usage_report['monthly_od_cost']        .map('${:,.2f}'.format)
        ri_usage_report['monthly_ri_savings']      = ri_usage_report['monthly_ri_savings']     .map('${:,.2f}'.format)
        ri_purchases['ri upfront cost'] = ri_purchases['ri upfront cost'].map('${:,.2f}'.format)
        ri_purchases['ri total cost']   = ri_purchases['ri total cost']  .map('${:,.2f}'.format)
        ri_purchases['ri savings']      = ri_purchases['ri savings']     .map('${:,.2f}'.format)
        ri_purchases['ondemand value']  = ri_purchases['ondemand value'] .map('${:,.2f}'.format)

    reports = {
        "ACCOUNT_INSTANCE_SUMMARY": instances,
        "RI_SUMMARY": ris,
        "RI_PURCHASES": ri_purchases,
        "RI_USAGE": ri_usage_report,
        "RI_HOURLY_USAGE": ri_hourly_usage_report,
        "UNUSED_AZ_RIS": unused_az_ris,
    }

    return reports


def cli():
    import argparse, csv
    parser = argparse.ArgumentParser(prog='{} {}'.format(*(sys.argv[0], sys.argv[1])))
    parser.add_argument('--config', required=True, help='Config file to load for Ariel configuration')

    args = parser.parse_args(args=sys.argv[2:])
    config = utils.load_config(args.config)

    from ariel import get_account_names, get_account_instance_summary, get_ec2_pricing, get_reserved_instances
    account_names = get_account_names.load(config)
    instances = get_account_instance_summary.load(config)
    ris = get_reserved_instances.load(config)
    pricing = get_ec2_pricing.load(config)

    reports = generate(config, instances, ris, pricing)

    for key, report in reports.items():
        LOGGER.info("Writing {} report to ./output_{}.csv".format(key, key.lower()))

        # Decorate report
        if 'accountid' in report.columns and 'accountname' not in report.columns:
            accountname_column = report.columns.get_loc('accountid') + 1
            input_column = 'Account ID' if 'Account ID' in report.columns else 'accountid'
            accountname_value = report[input_column].apply(lambda x: account_names[x] if x in account_names else x)
            report.insert(accountname_column, 'accountname', accountname_value)

        store_index = type(report.index) != pd.RangeIndex
        report.to_csv("output_{}.csv".format(key.lower()), index=store_index)
        LOGGER.debug("Report {}:\n".format(key) + str(report))

if __name__ == '__main__':
    cli()
