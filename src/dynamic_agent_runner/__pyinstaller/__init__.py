#!/usr/bin/env python
#
# Copyright (c) 2022, Oracle Corporation. All rights reserved.
#
# Author(s):
#   Bob Schumaker <bob.schumaker@oracle.com>
#
# pylint: disable=locally-disabled, line-too-long, invalid-name, bad-continuation
"""
Provide pyinstaller hooks for our library.
"""

import os


def get_hook_dirs():
    return [os.path.dirname(__file__)]
