# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from pathlib import Path

import yaml

from .basedetector import DependencyDetector
from ..knowledgegraph import Ns

logger = logging.getLogger(__name__)


class MozYamlDependencyDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "mozyaml"

    @staticmethod
    def priority() -> int:
        return 60

    def run(self):
        for m in self.hg.find("moz.yaml"):
            self.process(m)

    def process(self, file_path: Path):

        with file_path.open() as f:
            logger.debug(f"Parsing {str(file_path)} as YAML")
            try:
                y = yaml.load(f, Loader=yaml.SafeLoader)
            except yaml.scanner.ScannerError:
                logger.error(f"Broken YAML in {str(file_path)}. Ignoring file")
                return

        library_name = y["origin"]["name"]
        library_version = y["origin"]["release"]
        rel_top_path = str(file_path.parent.relative_to(self.hg.path))

        logger.info(f"MozYamlDependency adding `{rel_top_path}/moz.yaml`")

        # Get existing library node or create one
        try:
            lv = self.g.V(library_name).In(Ns().fx.mc.lib.name).Has(Ns().language.name, "cpp").All()[0]
        except IndexError:
            lv = self.g.new_subject()
            lv.add(Ns().fx.mc.lib.name, library_name)
            lv.add(Ns().language.name, "cpp")

        dv = self.g.new_subject()
        dv.add(Ns().fx.mc.lib.dep.name, library_name)
        dv.add(Ns().fx.mc.lib, lv)
        dv.add(Ns().language.name, "cpp")
        dv.add(Ns().fx.mc.detector.name, self.name())
        dv.add(Ns().version.spec, library_version)
        dv.add(Ns().version.type, "generic")
        dv.add(Ns().fx.mc.dir.path, rel_top_path)

        # TODO: extract upstream repo info

        # Create file references
        for f in file_path.parent.rglob("*"):
            logger.debug(f"Processing file {f}")
            rel_path = str(f.relative_to(self.hg.path))
            fv = self.g.new_subject()
            fv.add(Ns().fx.mc.file.path, rel_path)
            fv.add(Ns().fx.mc.file.part_of, dv)
