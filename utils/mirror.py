#!/usr/bin/env python


from abc import ABC, abstractmethod
import coloredlogs
import json
from logging import getLogger
import os
from pathlib import Path, PosixPath
from pprint import pprint as pp
import subprocess
import sys
import toml


# Initialize coloredlogs
logger = getLogger(__name__)
coloredlogs.DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s"
coloredlogs.install(level="DEBUG")




class TransferManager(object):
    def __init__(self, root_dir: str, store_name: str, source_path: str):
        pass

    def list_from_source(self):
        pass

    def list_from_store(self):
        pass

    def sync(self):
        pass




class HgRepo(object):

    def __init__(self, path: Path):
        self.path = path.resolve()

    def find(self, glob: str = "*", relative: bool = False):
        matches = filter(lambda p: p.parents[1] != ".hg", self.path.rglob(glob))
        for path in matches:
            if relative:
                yield path.relative_to(self.path)
            else:
                yield path




