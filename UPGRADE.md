# Ariel Upgrade Documentation

### v2.0.8

Version 2.0.8 introduced some incompatible Aurora DB changes.

* Addition of CMK / DBEngine / Snapshot support in auroradb.yaml CloudFormation Template
  * Changing any of these parameters will rebuild your database which will
    1. Alter your db connection endpoint
    2. Delete all data in your database
    3. Delete all automatic snapshots created for your database
  * To enable CMK Encryption you should:
    1. Create a manual snapshot of your database
    2. Update your template specifying both UseCmk, and the DbSnapshotIdentifier that you created
    3. DBEngine must match the version of your snapshot.
    4. Once DbSnapshotIdentifier has been specified, the value must be maintained or the database will be rebuilt again.
* Schema modifications to reserved_instances_recommendations and unlimited_usage tables
  * Since these tables contain current data an no history, it was determined to be easier to just drop and recreate:
    1. Connect to the database as aurora_dbo
    2. drop table reserved_instances_recommendations;
    3. drop table unlimited_usage;
    4. \i schema/02_tbl_reserved_instances_recommendations.sql
    5. \i schema/02_tbl_unlimited_usage.sql
    6. Re-run Ariel Lambda to re-populate these tables
