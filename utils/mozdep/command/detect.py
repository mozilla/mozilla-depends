# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from IPython import embed
import logging
from csv import DictWriter
from pathlib import Path

from .basecommand import BaseCommand
from ..component import detect_components
from ..detectors import run_all
from ..knowledgegraph import KnowledgeGraph

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
        parser.add_argument("-c", "--csv",
                            help="path to CSV export file",
                            type=Path,
                            action="store")
        parser.add_argument("-D", "--detector",
                            help="run specific detector(s)",
                            type=str,
                            default=[],
                            action="append")
        parser.add_argument("-i", "--ipython",
                            help="Drop into IPython shell before exiting",
                            action="store_true")

    def run(self) -> int:
        repo_dir = self.args.tree.resolve()

        g = KnowledgeGraph()

        run_all(repo_dir, g, choice=self.args.detector)

        file_count = len(g.V().Has("ns:fx.mc.file.path").All())
        dep_count = len(g.V().Has("ns:fx.mc.lib.dep.name").All())
        logger.info(f"Detectors found {file_count} files in {dep_count} dependencies (including duplicates)")

        detect_components(repo_dir, g)

        if self.args.csv:
            field_names = [
                "Name",
                "Version",
                "Language",
                "Upstream Version",
                "Upstream Repo",
                "Detector",
                "Component",
                "Files"
            ]
            with open(self.args.csv, "w", newline="") as f:
                c = DictWriter(f, field_names)
                c.writeheader()
                for dep_v in g.V().In("ns:fx.mc.lib.dep.name").AllV():
                    row = dict(zip(field_names, ["unknown"] * len(field_names)))
                    try:
                        row["Name"] = g.V(dep_v).Out("ns:fx.mc.lib.dep.name").All()[0]
                    except IndexError:
                        pass
                    try:
                        row["Version"] = g.V(dep_v).Out("ns:version.spec").All()[0]
                    except IndexError:
                        pass
                    try:
                        row["Language"] = g.V(dep_v).Out("ns:language.name").All()[0]
                    except IndexError:
                        pass
                    try:
                        row["Upstream Repo"] = g.V(dep_v).Out("ns:gh.repo.url").All()[0]
                    except IndexError:
                        pass
                    try:
                        row["Upstream Version"] = g.V(dep_v).Out("ns:gh.repo.version").All()[0]
                    except IndexError:
                        pass
                    try:
                        row["Detector"] = g.V(dep_v).Out("ns:fx.mc.detector.name").All()[0]
                    except IndexError:
                        pass

                    file_vs = g.V(dep_v).In("ns:fx.mc.file.part_of").AllV()
                    file_names = g.V(file_vs).Out("ns:fx.mc.file.path").All()
                    row["Files"] = "\n".join(file_names)

                    component_names = g.V(file_vs).Out("ns:bz.component.name").All()
                    row["Component"] = ";".join(component_names)

                    assert set(row.keys()) == set(field_names)
                    c.writerow(row)

            if self.args.ipython:
                embed()

        return 0
