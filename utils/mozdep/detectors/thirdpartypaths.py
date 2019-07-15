# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from pathlib import Path

from .basedetector import DependencyDetector
from ..knowledgegraph import Ns

logger = logging.getLogger(__name__)


class ThirdPartyPathsDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "thirdpartypaths"

    @staticmethod
    def priority() -> int:
        return 10

    def run(self):
        matches = list(self.hg.find("ThirdPartyPaths.txt"))
        if len(matches) > 1:
            logger.warning(f"Multiple locations for ThirdPartyPaths.txt, choosing first of {matches}")

        logger.info(f"ThirdPartyPathsDetector working through `{matches[0]}`")
        with matches[0].open() as f:
            for path in f:
                yield from self.process(self.hg.path / path.rstrip("\n"))

    def process(self, p: Path):
        yield from ()
        #
        #
        # if p.is_dir():
        #     dd = DependencyDescriptor(self, {
        #         "name": None,
        #         "version": None,
        #         "repo_top_directory": p,
        #         "repo_files": list(self.hg.find(start=p)),
        #         "target_store": None,
        #         "dependants": [],
        #         "dependencies": [],
        #         "sourcestamp": self.hg.source_stamp,
        #         "upstream_ref": None,
        #     })
        #     yield dd
        # elif p.is_file():
        #     dd = DependencyDescriptor(self, {
        #         "name": None,
        #         "version": None,
        #         "repo_top_directory": p.parent,
        #         "repo_files": [p],
        #         "target_store": None,
        #         "dependants": [],
        #         "dependencies": [],
        #         "sourcestamp": self.hg.source_stamp,
        #         "upstream_ref": None,
        #     })
        #     yield dd
        # else:
        #     logger.error(f"Ignoring broken reference {p}")
