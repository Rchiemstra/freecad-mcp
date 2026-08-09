import logging as logging
from pathlib import Path as Path

import vendor.capabilities.cache as cache


def add_constraint():
    return logging, Path, cache
