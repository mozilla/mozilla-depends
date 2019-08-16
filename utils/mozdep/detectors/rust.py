# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from pathlib import Path

import toml

from .basedetector import DependencyDetector
import mozdep.knowledge_utils as ku

logger = logging.getLogger(__name__)


class RustPackage(object):

    def __init__(self, toml_path: Path):
        assert toml_path.name == "Cargo.toml"
        self.path = toml_path.parent
        with open(self.path / "Cargo.toml") as f:
            s = f.read()
            # if """read "unusual" numbers""" in s:
            #     logger.warning("Applying toml parser hotfix for bitreader crate (uiri/toml/issues/177)")
            #     s = s.replace("""read "unusual" numbers""", """read `unusual` numbers""")
            if """futures-cpupool = { version=""" in s:
                logger.warning("Applying toml parser hotfix for audioipc client crate (uiri/toml/issues/240)")
                s = s.replace("""default-features=false""", '''default-features="__broken parser fix__"''')

            self.toml = toml.loads(s)

    @property
    def name(self):
        try:
            return self.toml.get("package")["name"]
        except TypeError:
            # Top-level Cargo.toml contains no package name
            return "Firefox"

    @property
    def version(self):
        try:
            return self.toml.get("package")["version"]
        except TypeError:
            # Top-level Cargo.toml contains no package version
            return "0.0.0"

    @property
    def repository(self):
        try:
            return self.toml.get("package")["repository"]
        except KeyError:
            return None
        except TypeError:
            return None

    @property
    def authors(self):
        try:
            return self.toml.get("package")["authors"]
        except TypeError:
            # Top-level Cargo.toml contains no package authors
            return "Mozilla"

    @property
    def dependencies(self):
        return list(self.toml.get("dependencies", {}).keys())

    @property
    def dev_dependencies(self):
        return list(self.toml.get("dev-dependencies", {}).keys())

    @property
    def all_dependencies(self):
        return sorted(self.dependencies + self.dev_dependencies)

    def __str__(self):
        return "<RustPackage `%s-%s`>" % (self.name, self.version)


class CargoTomlDependencyDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "cargotoml"

    @staticmethod
    def priority() -> int:
        return 80

    def setup(self) -> bool:
        with (self.hg.path / "Cargo.lock").open() as f:
            self.state = {"Cargo.lock": toml.load(f)}
        self.state["deps"] = {}
        for p in self.state["Cargo.lock"]["package"]:
            key = p["name"] + "-" + p["version"]
            self.state["deps"][key] = set()
            if "dependencies" in p:
                for d in p["dependencies"]:
                    name, version, *_ = d.split(" ")
                    self.state["deps"][key].add(name + "-" + version)
        return True

    def run(self):
        for ctf in self.hg.find("Cargo.toml"):
            logger.debug("Parsing %s" % ctf)
            rp = RustPackage(ctf)
            self.as_dependency_descriptor(rp)

    def as_dependency_descriptor(self, rp: RustPackage):

        manual_list = [
            "gfx/wr/wrench"
        ]

        # Skip those rust packages that we don't care about
        rel_top_path = str(rp.path.relative_to(self.hg.path))
        if not rel_top_path.startswith("third_party/") and rp.repository is None and rel_top_path not in manual_list:
            logger.info(f"CargoTomlDependency skipping `{rel_top_path}/Cargo.toml`")
            return

        logger.info(f"CargoTomlDependency adding `{rel_top_path}/Cargo.toml`")

        # # Get existing library node or create one
        # try:
        #     lv = self.g.V(rp.name).In(Ns().fx.mc.lib.name).Has(Ns().language.name, "rust").All()[0]
        # except IndexError:
        #     lv = self.g.new_subject()
        #     lv.add(Ns().fx.mc.lib.name, rp.name)
        #     lv.add(Ns().language.name, "rust")
        #
        # dv = self.g.new_subject()
        # dv.add(Ns().fx.mc.lib.dep.name, rp.name)
        # dv.add(Ns().fx.mc.lib, lv)
        # dv.add(Ns().language.name, "rust")
        # dv.add(Ns().fx.mc.detector.name, self.name())
        # dv.add(Ns().version.spec, str(rp.version))
        # dv.add(Ns().version.type, "generic")
        # dv.add(Ns().fx.mc.dir.path, rel_top_path)

        repo = rp.repository
        if repo is not None:
            if not repo.startswith("http"):
                repo = "https://github.com/" + repo.lstrip("/")

        # # Create file references
        # for f in self.hg.find(start=rp.path):
        #     rel_path = str(f.relative_to(self.hg.path))
        #     fv = self.g.new_subject()
        #     fv.add(Ns().fx.mc.file.path, rel_path)
        #     fv.add(Ns().fx.mc.file.part_of, dv)

        # TODO: extract dependencies from global Cargo.lock
        # key = rp.name + "-" + rp.version
        # try:
        #     deps = list(self.state["deps"][key])
        # except KeyError:
        #     deps = []

        _ = ku.learn_dependency(self.g,
                                name=rp.name,
                                version=str(rp.version),
                                detector_name=self.name(),
                                language="rust",
                                version_type="_generic",
                                upstream_version=None,  # FIXME: extract upstream version
                                top_path=rp.path,
                                tree_path=self.hg.path,
                                repository_url=repo,  # FIXME: extract upstream repo
                                files=list(self.hg.find(start=rp.path)),
                                vulnerabilities=None)
