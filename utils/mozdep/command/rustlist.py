# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging

from ..dependency import CargoTomlDependencyDetector
from .basecommand import BaseCommand

logger = logging.getLogger(__name__)


class RustListCommand(BaseCommand):
    """
    Command for listing Rust dependencies
    """

    name = "rustlist"
    help = "list rust dependencies detected in tree"

    def run(self) -> int:
        repo_dir = self.args.tree.resolve()

        deps = []

        # print(os.getcwd())
        # print("\n".join(os.listdir(repo_dir)))

        # pp = PrettyPrinter(width=120).pprint

        det = CargoTomlDependencyDetector(repo_dir)
        det.prepare()
        for dependency in det.run():
            deps.append(dependency)

        logger.info(f"Detector returned {len(deps)} dependencies (including duplicates)")

        for d in deps:
            print(f"{d.name}\t{d.repo_top_directory}\t{d.upstream_ref}")

        return 0
