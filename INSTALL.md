# Ariel Install Documentation

### 0. Clone this repository

* Determine if you will be running Ariel in your Master Billing Account, or in a separate account.  Both are supported, however Ariel has many dependencies on Master Billing, and when using a separate account, cross account access to master is required.  For more information please review [README.md](README.md)
* `git clone https://github.com/yahoo/ariel.git`

### 1. Create an Athena Optimized Cost and Usage Report

* Log in to your master billing account
* Navigate to `Billing` -> `Cost & Usage Reports`
* Click `Create report`
  * Make sure to select `Enable report data integration for Amazon Athena`
  * Set `Time Granularity` to `Hourly`
  * All other values are up to your personal preference
  * Make note of the value you use for the `Report name`.  You will need this in step 4 for the `ATHENA` -> `CUR_TABLE_NAME` config setting.

### 2. Create Glue Crawler

Step 1 will create a cloudformation template for you at
`s3://<s3 bucket>/<report prefix>/crawler-cfn.yml`.
* Browse to this object and copy the Object URL to your clipboard.
  * For example, if your s3 bucket is `cur-reports` and your report prefix is `athena/cur` you would:
    * Navigate to `S3`
    * Select the `cur-reports` bucket
    * Select the `athena` folder then the `cur` folder.
    * Select `crawler-cfn.yml`
    * Copy the `Object URL` to the clipboard.  This is a link that starts with `https://s3.amazonaws.com/`
* Navigate to `CloudFormation`
* Click `Create stack`
  * Paste the URL for the crawler-cfn template in for `Amazon S3 URL`
  * All other values are up to your preference
* Navigate to `AWS Glue`
  * Select `Crawlers`
  * Select `AWSCURCrawler-cur`
  * Note the `Database` name listed on this page.  You will need this in step 4 for the `ATHENA` -> `CUR_DATABASE` config setting.

### 3. Install Athena Usage Role

* While still in `CloudFormation`
* Click `Create stack`
  * Select `Upload a template file`
  * Choose the file `cloudformation/master-usage.yaml` from your local ariel repository
  * Click `Next` to get to the stack parameters page
  * If you will be running Ariel in an account other than master, you must specify `UsageAccount` to be the Ariel execution account
  * All other parameters are up to personal perference

### 4. Install Ariel

* If running Ariel from an account other than master, switch to the Ariel account
* Create or select an S3 bucket to use for Ariel application packaging
* In a `Terminal` running in your local ariel repository
  * Run `./package.sh <s3-bucket>`
    * This will build the Ariel zip containing the native dependencies, and
      publish the Ariel CF and code to the specified S3 bucket
    * Note the final 2 lines of this output which will define the S3 path to use for installation
* Edit `config-example.yaml`
  * You must specify `MASTER` -> `ACCOUNT_ID` or `MASTER` -> `ROLE` if you are running Airle in an account other than master
  * You must specify `ATHENA` -> `CUR_DATABASE` - this must be set to the `Database` value from the `AWS Glue` configuration noted in Step 2
  * You must specify `ATHENA` -> `CUR_TABLE_NAME` - this must be set to the same value as the `Report name` you chose for the Cost and Usage report in Step 1.  
  * If you would like any reports published to S3, you must update the `CSV_REPORTS` section with the S3 path to publish each reports to
  * If you would like any reports published to RDS, you must update the `PG_REPORTS` section with `DB_HOST`, and the table name to publish each report to
  * All other values you can tune as necessary
* Upload your finalized configuration to S3.  Make sure to note the S3 URL for this object
* Navigate to `CloudFormation`
* Click `Create stack`
  * Paste the Ariel S3 Installation Path from earier in Step 4 in to `Amazon S3 URL`
  * Click `Next` to get to the stack parameters page
  * Set `ArielConfigurationLocation` to the S3 URL for your configuration object
  * Set the `S3WriteARNs` to a comma separated list of ARNs that Ariel will need write access to, based on your `CSV_REPORTS` configuration
  * All other values are up to your preference
    * If using optional AuroraDB, it is recommended to install in the VPC you will be using for Aurora.

### 5. Test Invocation

* Navigate to `AWS Lambda`
* Select the `ariel` Function
* Select `Configure test events` from the drop list next to the `Test` button.
* Add a Test event:
  `{ "config": "<S3 URL for your config object>"}`
* Click on `Test`

NOTE: Please review to [UPGRADE.md](UPGRADE.md) for upgrade considerations.


# Optional Aurora DB Install Documentation

The simplest data export method from Ariel is to publish CSV reports to S3, however that is not always the easiest to consume.  Ariel includes optional support for publishing reports to a Postgres compatible database, and we include CloudFormation support for a Postgres compatible Aurora DB Instance.

### Requirements
This Aurora DB template must be installed in an existing VPC.  You will need to manage your Network ACLs and Security Groups yourself to properly restrict access.

### 1. Install Aurora
* Navigate to `CloudFormation`
* Click `Create stack`
  * Select `Upload a template file`
  * Select `cloudformation/auroradb.yaml` from this project.
  * Configure the requested parameters
* Your auroradb host is listed in Outputs from the CF Stack.  You can configure a Route 53 alias if you want.

### 2. Install Schema
* In a `Terminal` running in your local ariel repository
  * Run `./schema/install_schema.sh <auroradb-hostname>`

NOTE: Please review to [UPGRADE.md](UPGRADE.md) for upgrade considerations.
