# Ariel

> Ariel is an AWS Lambda designed to collect, analyze, and make
recommendations about Reserved Instances for EC2.

## Table of Contents
- [Background](#backgorund)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Dependencies](#dependencies)
  - [Optional Functionality](#optional-functionality)
  - [Recommendations Algorithm](#recommendations-algorithm)
  - [Outputs](#outputs)
- [Usage](#usage)
  - [Additional Considerations](#additional-considerations)
- [Contributing](#contributing)
- [Maintainers](#maintainers)
- [License](#license)

## Background

Ariel is a tool designed to make purchase recommendations for Reserved
Instances for EC2. There are many tools that currently provide similar functionality to generate recommendations for either all accounts, where there is no indication of which account will benefit from the Reserved Instance, or for each account individually, which does not properly take into consideration Reserved Instance float, resulting in a recommendation of too many Reserved
Instances.

The main benefit of Ariel, and what all other tools appear to lack, is the ability to combine these two approaches. Reserved Instances demand is calculated based on overall company usage, but specific recommendations are made by account such that an individual account will never purchase more than it is currently using, and also the combine Reserved Instances total will never exceed the current demand for the whole company.

Ariel also has more configuration options to allow finer tuning of the
purchase recommendation algorithm; additional details can be found
below in the Algorithms section.

## Installation

Please refer to [INSTALL.md](INSTALL.md) for installation instructions.

## Configuration

Configuration inputs are documented in [config-example.yaml](config-example.yaml).
It is expected that you will:
- Copy and modify this file for your specific environment
- Deploy this configuration file to S3
- Configure the Lambda input parameter to point to this file in S3

### Dependencies

There are many components and dependencies for Ariel that allow different deployments.

**Master Billing Account - Reserved Instances**

Ariel needs access to the Master Billing Account to collect all active
Reserved Instances.  This is collected through the Reserved Instances
Utilization report provided by Cost Explorer.  In addition to this
report including Reserved Instances information about all active
accounts in your Organization, this is one of the only ways to collect
information about Reserved Instances in suspended accounts in your
Organization.  While suspended accounts are otherwise inactive, their
Reserved Instances are still active with their monthly fee being charged
to the otherwise closed account, and they are still able to float to any
account linked to your Master Billing Account.

**Master Billing Account - Account Names**

Ariel can be configured to gather account names from the Organizations
API only accessible from the Master Billing Account.  This access is not
required, as a flat file may be used instead, or if neither are
specified, Accound IDs will be used instead of names.

**Master Billing Account - Cost and Usage Reports + Athena**

This version of Ariel requires [Athena Optimized Cost and Usage Reports](https://aws.amazon.com/about-aws/whats-new/2018/11/aws-cost-and-usage-report-integrates-with-amazon-athena/).
Cost and Usage Reports can only be written to a bucket in the Master
Billing Account.  Athena Optimization only works when the data is stored
in the bucket it was originally written to.  Report data is written from
a 3rd party AWS account and can not be shared with other accounts.  The
end result of these three statements is that Athena must be used from the
Master Billing Account.

Access requirements for the Master Billing Account have been separated
into a standalone CloudFormation template so that Ariel can run in an
account other than the Master Billing Account, and just use a
cross-account role when necessary.

**VPC**

Ariel does not need a VPC to run. However, if you want to deploy it to
a VPC you will want to create your own VPC with the necessary Subnets, Route Tables, Internet Gateway, NAT Gateways, Network ACLs, and Security Groups, we do not provide a VPC template.

### Optional Functionality

* **VPC** - Ariel can be deployed with or without a VPC.  Unfortunately the
AWS::Serverless transform does not yet support conditionals, so the
Ariel VPC and non-VPC templates are separate files.

* **AuroraDB/RDS** - Ariel can be configured to publish the results to a Postgres Database.
If using this database, it is recommended that you deploy Ariel in a VPC
and prevent internet access directly to your database.

### Recommendations Algorithm

Proper Reserved Instances management is an art form that is very
difficult and complex, and mistakes can be costly.  When making
purchases, you really must be certain that you will use the Reserved
Instances for at least as long as the break-even term for each
Reserved Instance. The following content describes how to fine tune your Ariel recommendations.

#### Utilization vs Coverage

Reserved Instance utilization and coverage are inversely related
metrics.  As you increase your coverage, your utilization will usually
decrease.  Properly managing Reserved Instances involves maximizing
coverage, while keeping utilization high enough to be cost beneficial.
Additionally, since the most cost effective Reserved Instance has a
three year term, you will also need to predict your future usage to make
effective purchases.

For Reserved Instances purchase recommendations in Ariel, a target
utilization value is specified.  To achieve higher coverage, specify
a lower desired utilization.  Ariel also has a special `BREAK_EVEN`
keyword for utilization that will calculate the specific break even
utilization percents for the currently evaluated region and family.

#### Break Even

Actual break even numbers vary by region and instance type family, but
for a rough rule to follow for Standard Reserved Instances in US regions:

* A one year Reserved Instance breaks even in about 7 months.
* A three year Reserved Instance breaks even in about 13 months.
* Renewing a one year Reserved Instance once will cost more than if
  a three year Reserve Instance was purchased initially.

#### Aggressive / Conservative

Ariel supports two thresholds that control 3 configurations for
purchasing aggressiveness.  For both thresholds, the instances run rate,
for an individual instance type family, region, tenancy, and operating
system, is fit to a straight line, and the threshold is applied to the
slope of that line.

* If the slope is greater than `AGGRESSIVE_THRESHOLD`, the `AGGRESSIVE`
  configuration is used.
* If the slope is smaller than `CONSERVATIVE_THRESHOLD`, the
  `CONSERVATIVE` configuration is used.
* Otherwise, the `DEFAULT` configuration is used.

These thresholds are specified in "normalized units" per day.  For
example, a value of 1000 means an average increase of 125xlarge
instances per day.  Normalized units can be found in the
[Reserved Instances Documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ri-modifying.html#ri-modification-instancemove)

#### Standard / Convertible

Convertible Reserved Instances allow for greater flexibility, but also
cost on average 25% more than standard Reserved Instances.  Ariel tries
to give you the ability to purchase a baseline of standard Reserved
Instances, while simultaneously pushing up your coverage with
convertible Reserved Instances, reducing your risk if some workloads
migrate away.

Convertible Reserved Instances recommendations will always be calculated
after standard, and will assume that the standard Reserved Instances are
also being purchased.

##### Slush Account

There are some cases where the total Reserved Instances recommendation
by account will be less than the overall company demand.  As a trivial
example, if two accounts would benefit from a single Reserved Instance
during different halves of the day, neither account would have sufficient
demand to make the purchase independently, but the company would still
benefit from purchasing one.

In this case, Ariel can be configured to make a purchase recommendation
in a slush account.

The algorithm evaluates in this order:

* Standard in-account
* Standard slush account
* Convertible in-account
* Convertible slush account

#### Regional / Availability Zone

With the introduction of [OnDemand Capacity Reservations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-reservations.html),
there is no longer any benefit from ever using Availability Zone based
Reserved Instances.  This support has been removed from Ariel, and
Regional Reserved Instances will always be recommended.

### Outputs

Please refer to [REPORTS.md](REPORTS.md) for detailed information about
the reports generated.

## Usage

Ariel is typically run daily.  It's possible to configure it to run
more frequently, but this provides little additional value, as Cost
and Usage Reports are only updated two to three times per day.  There
are no concerns with running Ariel less frequently.

Some of the report data is useful to look at every day, such as the
ri-usage report to find available excess Reserved Instances for shifting
workloads that are easy to move across instance types.  The main report
from Ariel, ri-purchases, tends to have a slower cadence.  It is
recommended to evaluate a single ri-purchases report monthly or
quarterly to make decisions about which recommendations to purchase.
This review and decision making process is necessarily manual.

Assuming that a purchase is completed through a support case or your
Concierge, it will take some time for your order to be processed.  Ariel
will automatically pick up new Reserved Instances once they have been
purchased through the report accessed from Cost Explorer.

### Opening a support case

If your Support Plan allows for it, you can bulk purchase Reserved Instances
though a support case.

* Case Type: `Account and billing support`
* Type: `Billing`
* Category: `Reserved Instances`
* Severity: `General question`

You will want to download the [AWS RI Transaction Request Worksheet](https://s3.amazonaws.com/awsreservedinstancetransactionrequestworksheet/AWS+RI+Transaction+Request+Worksheet.xlsb), fill it out, and attach it to the case.

For the account list, you may want to `cat ri-purchases.csv | cut -f1 -d, | grep -v Account | sort -u > accounts.txt`

For the purchase sheet, you can load ri-purchases.csv into Excel, then copy the columns A-J, excluding the header, then `Paste Values` into the worksheet.  You will need to manually populate the `Desired Start Date` field.

### Additional Considerations

Ariel does not yet make any recommendations related to modifying
existing convertible Reserved Instances.  Before making a purchase
you should:

* Check the ri-usage report to find instance type families with excess
  unused Reserved Instances
* Check the reserved instances report to find matching convertible
  Reserved Instances
* Modify the unused Reserved Instances to cover new recommended Reserved
  Instances
* Subtract the modified Reserved Instances from the recommendation

## Contributing

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for information about
how to get involved. We welcome issues, questions, and pull requests.
Pull Requests are welcome.

## Maintainers
Sean Bastille: sean.bastille@verizonmedia.com
Micah Meckstroth: micah.meckstroth@verizonmedia.com

## License
This project is licensed under the terms of the
[Apache License, Version 2.0](LICENSE) open source license. Please refer
to [LICENSE](LICENSE) for the full terms.
