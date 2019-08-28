# Copyright 2019, Oath Inc.
# Licensed under the terms of the Apache License, Version 2.0. See LICENSE file for terms.
__all__ = ['generate_reports', 'get_account_instance_summary', 'get_account_names', 'get_ec2_pricing', 'get_locations',
           'get_reserved_instances', 'get_unlimited_summary', 'get_unused_box_summary', 'utils', 'LOGGER']
__version__='2.0.5'

import logging
LOG_LEVEL = logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt='%Y-%m-%dT%H:%M:%SZ')
LOGGER = logging.getLogger('ariel')
