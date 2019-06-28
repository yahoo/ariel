# Ariel Reports Documentation

## Table of Contents
- [Reserved Instances Recommendations](#reserved-instances-recommendations)
- [Reserved Instances Usage](#reserved-instances-usage)
- [Unused AZ RIs](#unused-az-ris)
- [Unlimited Usage](#unlimited-usage)
- [Unused Box](#unused-box)
- [Account Instance Summary](#account-instance-summary)

## Reserved Instances Recommendations
* **Default filename:** ri-purchase.csv
* **DB Tablename:** reserved_instances_recommendations

This report contains the RI Purchase recommendations for all accounts.
This is the main report you will use from Ariel.

The first 11 columns are the data that AWS needs when processing a
purchase via an AWS Concierge.  This specific naming convention and
column order are preserved to minimize the effort when submitting this
request.

The remaining columns have been added to facilitate review prior to
ordering.

* `units` is better explained in the AWS
[Reserved Instances Documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ri-modifying.html#ri-modification-instancemove)
* `ondemand value` is calculated assuming that the RI will be 100% used.
Depending on your usage patterns, and recommendations configuration,
this is not a safe assumption.
* `ri savings` = `ondemand value` - `ri total cost`
* `algorithm` is provided to give additional context as to how Ariel
made this specific recommendation.  It is determined based on the
thresholds defined in your recommendations configuration.

## Reserved Instances Usage
* **Default filenames:** ri-usage.csv, ri-hourly-usage.csv
* **DB Tablenames:** reserved_instances_usage,
reserved_instances_hourly_usage

These reports contain details about your RIs and Instance Usage to help
identify underutilized RIs.

* `total_ri_units` is the total number of active RIs, displayed in
normalized instance units.
* `total_instance_units` is the average of the total number of instances
running per hour, displayed in normalized instance units.
* `floating_ri_units` is the average number of active RIs per hour that
are not used to cover instances in the account they were purchased in,
allowing them to float to cover instances in other accounts.
* `floating_instance_units` is the average number of instances running
per hour that are not covered by an RI from the account where they are
running.  These instances are eligible to be covered by a floating RI.
* `unused_ri_units` is the average number of RIs per hour that do not
cover any instances.  These RIs should be considered for conversion or
resale on the marketplace.
* `coverage_chance` is the percent change that an instance will be
covered by a floating RI.
* `xl_effective_rate` is the average rate you would expect to pay for
a new xlarge instance launched of this family, assuming no extra RIs
are active in the launching account.  This value will be between the
ondemand rate and the effective rate based on your purchased RIs.
* `monthly_ri_cost` is the amortized amount of money paid for the
active RIs.
* `monthly_od_cost` is the cost of `total_instance_units` if they were
not covered by RIs.
* `monthly_ri_savings` = `monthly_od_cost` - `monthly_ri_cost`
* `hourofweek`: for the hourly report/table, an hourofweek column exists
giving better insight into fluctuations through the week.  0 = Midnight
on Monday, 1 = 1am on Monday, and so on.

## Unused AZ RIs
* **Default filename:** unused-az-ris.csv
* **DB Tablename:** unused_az_ris

Due to [OnDemand Capacity Reservations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-reservations.html)
AZ RIs no longer provide any exclusive benefit on their own, but do not
incur any additional expense unless they go unused.  It is recommended
to migrate all AZ RIs to be Regional, and request Capacity Reservations
where needed.

This report shows AZ RIs that are currently not being used.  These RIs
are providing little or no value to your company, and may provide
more value simply by converting them to be regional.  It is highly
recommended to migrate these RIs to be Regional.

## Unlimited Usage
* **Default filename:** unlimited-usage.csv
* **DB Tablename:** unlimited_usage

T2/T3 Unlimited usage allows instances to exceed the amount of CPU
allocated for the purchase size.  While this is helpful in some cases,
continuous abuse of this feature results in significant usage charges
that can not be mitigated with RIs or any other method.

The data provided here is mostly information, but if you see accounts
with excessive unlimited charges, you may want to reach out to the
account owners to evaluate updating the application, changing the
instance size, or changing the instance type family.

## Unused Box
* **Default filename:** unused-box.csv
* **DB Tablename:** unused_box

With the migration to [OnDemand Capacity Reservations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-reservations.html)
there exists a new charge for unused capacity reservations.  Some
businesses may require this functionality, but often these charges can
and should be avoided.

If you see accounts with UnusedBox charges, and you do not have a
business case that requires that additional expense, you should reach
out to the account owners and ask them to release the reservations.

## Account Instance Summary
* **DB Tablename:** account_instance_summary

This is the only report that is an append operation in the database.
When evaluating purchase recommendations, it is frequently useful to
visualize instance usage over time to confirm usage assumptions.  Ariel
does not include visualizations for this data, but most data
visualization tools should easily render this table.