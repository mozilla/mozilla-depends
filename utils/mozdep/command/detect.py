# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from pprint import PrettyPrinter
import os

from ..dependency import CargoTomlDependencyDetector, MozYamlDependencyDetector, \
    RetireDependencyDetector, ThirdPartyAlertDetector

from .basecommand import BaseCommand
logger = logging.getLogger(__name__)


class DetectCommand(BaseCommand):
    """
    Command for listing dependencies detected in tree
    """

    name = "detect"
    help = "list dependencies detected in tree"

    @classmethod
    def setup_args(cls, parser):
        """
        Add subparser for setup-specific arguments.

        :param parser: parent argparser to add to
        :return: None
        """
        pass

    def run(self) -> int:
        repo_dir = self.args.tree.resolve()

        deps = []

        # print(os.getcwd())
        # print("\n".join(os.listdir(repo_dir)))

        # pp = PrettyPrinter(width=120).pprint

        for detector in ThirdPartyAlertDetector, CargoTomlDependencyDetector, MozYamlDependencyDetector, \
                        RetireDependencyDetector:
        # for detector in [ThirdPartyAlertDetector]:
            det = detector(repo_dir)
            det.prepare()
            for dependency in det.run():
                print(str(dependency))
                deps.append(dependency)

        logger.info(f"Detectors returned {len(deps)} dependencies (including duplicates)")

        from IPython import embed
        embed()

        return 0
