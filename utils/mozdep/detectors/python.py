# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
import logging
from pathlib import Path
from tempfile import mkdtemp
from typing import Iterable
from subprocess import CalledProcessError

from .basedetector import DependencyDetector
import mozdep.knowledge_utils as ku
import mozdep.python_utils as pu

# tempfile.mkdtemp(suffix=None, prefix=None, dir=None

logger = logging.getLogger(__name__)


def bulk_process(venv, all_pkgs: Iterable[Path]) -> dict:
    safety_db = pu.SafetyDB()
    base_state = set(pu.check_pip_freeze(venv))
    current_state = base_state.copy()
    setup_map = dict()
    for pkg_path in all_pkgs:
        logger.info(f"Processing Python package from {pkg_path}")
        try:
            # CAVE:
            # Installing Python packages si essentially arbitrary code execution.
            # We can only do this as long as we trust those setup.py files.
            pu.run_pip(venv, "install", "--force-reinstall", "--no-deps", str(pkg_path.parent))
        except CalledProcessError:
            logger.error(f"Unable to install {pkg_path}. Ignoring packet")
            continue
        new_state = set(pu.check_pip_freeze(venv))
        state_diff = new_state - current_state
        current_state = new_state
        for package_name, installed_version in state_diff:
            logger.debug(f"New package: {package_name} {installed_version}")
            if package_name in setup_map:
                logger.warning(f"Ignoring duplicate package at {pkg_path}")
            else:
                setup_map[package_name] = pkg_path

    result = dict()
    installed_state = current_state - base_state
    for package_name, installed_version, upstream_version, upstream_repo in pu.pip_check_result(venv):
        if (package_name, installed_version) not in installed_state:
            continue
        vulnerabilities = list(safety_db.match(package_name, installed_version))
        for vuln in vulnerabilities:
            logger.warning(f"Vulnerability found: {repr(vuln)}")

        setup_path = setup_map[package_name]
        result[package_name] = {
            "setup_path": setup_path,
            "package_name": package_name,
            "installed_version": installed_version,
            "upstream_version": upstream_version,
            "upstream_repo": upstream_repo,
            "vulnerabilities": vulnerabilities
        }
        logger.debug(result[package_name])

    return result


class PythonDependencyDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "python"

    @staticmethod
    def priority() -> int:
        return 70

    def setup(self) -> bool:
        if find_executable("virtualenv") is None:
            logger.error("Cannot find `virtualenv`")
            return False

        tmpdir = Path(mkdtemp(prefix="mozdep_"))
        try:
            venv = pu.make_venv(tmpdir)
        except CalledProcessError as e:
            logger.error(f"Error while creating virtual environment: {str(e)}")
            return False
        logger.debug(f"Created virtual environment in {venv}, installing `pip-check`")

        try:
            pu.run_pip(venv, "install", "pip-check")
        except CalledProcessError as e:
            logger.error(f"Error while installing `pip-check`: {str(e)}")
            return False

        try:
            safety_db = pu.SafetyDB()
        except AssertionError:
            logger.error(f"Failed to fetch Safety DB from `{pu.SafetyDB.db_url}`")
            return False

        self.state = {
            "safety_db": safety_db,
            "tmpdir": tmpdir,
            "venv": venv
        }

        return True

    def run(self):
        # setup_files = list(self.hg.path.glob("third_party/python/*/setup.py"))
        setup_files = list(self.hg.find("setup.py"))
        results = bulk_process(self.state["venv"], setup_files)

        for result in results.values():
            self.process(result)

    def process(self, arg):

        setup_path = arg["setup_path"]
        library_name = arg["package_name"]
        library_version = arg["installed_version"]
        upstream_version = arg["upstream_version"]
        repo_url = arg["upstream_repo"]

        logger.debug(f"Adding package info: {library_name} {library_version} {upstream_version} {repo_url}")

        # Various ways of parsing setup.py, but we chose to pipe them through pipenv
        # with setup_path.open() as f:
        #     import mock  # or `from unittest import mock` for python3.3+.
        #     import setuptools
        #
        #     with mock.patch.object(setuptools, 'setup') as mock_setup:
        #         import setup  # This is setup.py which calls setuptools.setup
        #
        #     # called arguments are in `mock_setup.call_args`
        #     args, kwargs = mock_setup.call_args
        #     print
        #     kwargs.get('install_requires', [])
        ###
        # >> > import imp
        # >> > module = """
        # ... def setup(*args, **kwargs):
        # ...     print(args, kwargs)
        # ... """
        # >> >
        # >> > setuptools = imp.new_module("setuptools")
        # >> > exec
        # module in setuptools.__dict__
        # >> > setuptools
        # < module
        # 'setuptools'(built - in) >
        # >> > setuptools.setup(3)
        # ((3,), {})
        ###
        # >> > import setuptools
        # >> >
        #
        # def setup(**kwargs):
        #     print(kwargs)
        #
        # >> > setuptools.setup = setup
        # >> > content = open('setup.py').read()
        # >> > exec(content)

        # rel_top_path = str(setup_path.parent.relative_to(self.hg.path))

        logger.info(f"Adding `{str(setup_path)}`")

        # # Get existing library node or create one
        # try:
        #     lv = self.g.V(library_name).In(Ns().fx.mc.lib.name).Has(Ns().language.name, "cpp").All()[0]
        # except IndexError:
        #     lv = self.g.new_subject()
        #     lv.add(Ns().fx.mc.lib.name, library_name)
        #     lv.add(Ns().language.name, "cpp")
        #
        # dv = self.g.new_subject()
        # dv.add(Ns().fx.mc.lib.dep.name, library_name)
        # dv.add(Ns().fx.mc.lib, lv)
        # dv.add(Ns().language.name, "python")
        # dv.add(Ns().fx.mc.detector.name, self.name())
        # dv.add(Ns().version.spec, library_version)
        # dv.add(Ns().version.type, "generic")
        # dv.add(Ns().fx.mc.dir.path, rel_top_path)
        #
        # if repo_url is not None:
        #     dv.add(Ns().gh.repo.url, repo_url)
        #     dv.add(Ns().gh.repo.version, upstream_version)
        #
        # # Create file references
        # for f in setup_path.parent.rglob("*"):
        #     logger.debug(f"Processing file {f}")
        #     rel_path = str(f.relative_to(self.hg.path))
        #     fv = self.g.new_subject()
        #     fv.add(Ns().fx.mc.file.path, rel_path)
        #     fv.add(Ns().fx.mc.file.part_of, dv)

        dv = ku.learn_dependency(self.g,
                                 name=library_name,
                                 version=library_version,
                                 detector_name=self.name(),
                                 language="python",
                                 version_type="_generic",
                                 upstream_version=upstream_version,
                                 top_path=setup_path.parent,
                                 tree_path=self.hg.path,
                                 repository_url=repo_url,
                                 files=[setup_path],
                                 vulnerabilities=None)

        if "vulnerabilities" in arg:
            for vuln in arg["vulnerabilities"]:
                logger.critical(repr(vuln))
                ku.learn_vulnerability(self.g,
                                       vulnerability_identifier=vuln["id"],
                                       database="pyup.io",
                                       info_links=[],
                                       affects=[dv],
                                       title=vuln["cve"],
                                       description=vuln["advisory"],
                                       weakness_identifier=None,
                                       severity=None)
