# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
from time import sleep

import boto3
import csv
import io
import os
import tempfile
import yaml

class AutoVivification(dict):
    """Implementation of perl's autovivification feature."""
    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value

class CsvDialect(csv.Dialect):
    strict = True
    skipinitialspace = True
    quoting = csv.QUOTE_ALL
    delimiter = ','
    quotechar = '"'
    lineterminator = '\n'

def assume_role(session, role):
    assumedRole = session.client('sts').assume_role(RoleArn=role, RoleSessionName='ariel')
    access_key = assumedRole['Credentials']['AccessKeyId']
    access_secret = assumedRole['Credentials']['SecretAccessKey']
    session_token = assumedRole['Credentials']['SessionToken']
    return boto3.session.Session(aws_access_key_id = access_key, aws_secret_access_key = access_secret,
            aws_session_token = session_token)

def execute_athena_query(athena, staging, query):
    query_id = athena.start_query_execution(QueryString=query, ResultConfiguration={
        'OutputLocation': staging,
        'EncryptionConfiguration': {
            'EncryptionOption': 'SSE_S3'
        }
    })['QueryExecutionId']

    sleep_time = 1
    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        if status['QueryExecution']['Status']['State'] == 'SUCCEEDED':
            return query_id
        if status['QueryExecution']['Status']['State'] == 'FAILED':
            print("ERROR: Query Execution Failure ({0})".format(query))
            print(status)
            raise RuntimeError("Query Execution Failure")
        sleep(sleep_time)
        if sleep_time < 8:
            sleep_time *= 2

def get_master(config):
    account  = get_config_value(config, 'MASTER', 'ACCOUNT_ID', '')
    if account == '':
        role = get_config_value(config, 'MASTER', 'ROLE', '')
        if role != '':
            account = role.split(':')[4]
    else:
        role = get_config_value(config, 'MASTER', 'ROLE', 'arn:aws:iam::{}:role/ariel-master-usage'.format(account))
    return account, role

def get_read_handle(filename):
    if filename.startswith('s3:'):
        proto, empty, bucket, key = filename.split('/', 3)
        rsp = boto3.client('s3').get_object(Bucket=bucket, Key=key)
        return io.BytesIO(rsp['Body'].read())
    if filename.startswith('http:') or filename.startswith('https:'):
        raise NotImplementedError('HTTP support not yet implemented')

    if filename.startswith('file://'):
        proto, empty, filename = filename.split('/', 2)
    return open(filename, 'r')


def get_temp_write_handle(filename):
    if filename.startswith('s3://'):
        proto, empty, bucket, key = filename.split('/', 3)
        tmpfd, tmpfile = tempfile.mkstemp(suffix='csv', text=True)
        return FileUploader(tmpfd, tmpfile, bucket, key)
    if filename.startswith('file://'):
        dirname, basename = os.path.split(filename[7:])
        tmpfd, tmpfile = tempfile.mkstemp(suffix='csv', dir=dirname, text=True)
        return FileRenamer(tmpfd, tmpfile, filename[7:])


    raise NotImplementedError('Unknown file uri: ' + filename)


class FileRenamer(io.RawIOBase):
    def __init__(self, fd, tmpfilename, filename):
        self.fd = fd
        self.tmpfilename = tmpfilename
        self.filename = filename

    def __enter__(self):
        self.file = os.fdopen(self.fd, 'w')
        return self.file

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()
        os.rename(self.tmpfilename, self.filename)


class FileUploader(io.RawIOBase):
    def __init__(self, fd, tmpfilename, bucket, key):
        self.fd = fd
        self.tmpfilename = tmpfilename
        self.bucket = bucket
        self.key = key

    def __enter__(self):
        self.file = os.fdopen(self.fd, 'w')
        return self.file

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()
        boto3.resource('s3').meta.client.upload_file(self.tmpfilename, self.bucket, self.key)
        os.remove(self.tmpfilename)


def load_config(filename):
    with get_read_handle(filename) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    # Initialize Logging Config
    log_level = get_config_value(config, 'DEFAULTS', 'LOG_LEVEL', '')
    if log_level != '':
        from ariel import LOGGER
        import logging
        LOGGER.setLevel(logging.getLevelName(log_level))
    return config


def get_config_value(config, section_name, key, default=None):
    section = config.get(section_name, {})
    if section is None:
        value = default
    else:
        value = section.get(key, default)
    if value is None:
        if default is None:
            raise Exception('Missing required configuration value: {}.{}'.format(section, key))
        return default
    return value

def parse_header(header):
    return dict((header[i], i) for i in range(len(header)))
