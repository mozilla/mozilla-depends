# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
from json import loads
import logging
from pathlib import Path
from requests import get
from semantic_version import Version, Spec, validate
from tempfile import mkdtemp
from typing import Iterator, Tuple, Iterable, List
from subprocess import run, PIPE, DEVNULL, CalledProcessError

from .basedetector import DependencyDetector
from ..knowledgegraph import Ns

# tempfile.mkdtemp(suffix=None, prefix=None, dir=None

logger = logging.getLogger(__name__)


class SafetyDB(object):

    db_url = """https://raw.githubusercontent.com/pyupio/safety-db/master/data/insecure_full.json"""

    def __init__(self):
        r = get(self.db_url)
        assert r.status_code == 200
        self.db = loads(r.text)

    def match(self, package_name, version):
        if not validate(version):
            logger.debug(f"Package {package_name} has partial semver version {version}")
        try:
            v = Version(version, partial=True)
        except ValueError:
            logger.error(f"Invalid version {version}. Ignoring packet")
            return
        if package_name in self.db:
            for vuln in self.db[package_name]:
                for semver_spec in vuln["specs"]:
                    try:
                        if v in Spec(semver_spec):
                            yield vuln
                            break
                    except ValueError:
                        # Fallback for broken semver specs in deb: try raw comparison
                        logger.warning(f"Broken semver spec for {package_name} in SafetyDB: {semver_spec}")
                        if version == semver_spec:
                            yield vuln
                            break


def pip_check_result(venv: Path) -> Iterator[Tuple[str, str, str or None, str or None]]:
    lines = run_venv(venv, "pip-check", "-c", str(venv / "bin" / "pip"), "-a").split("\n")
    for l in lines:
        if l.startswith("|"):
            _, pkg, old, new, repo, _ = map(str.strip, l.split("|"))
            if old == "Version":
                continue
            if repo == "":
                repo = None
            yield pkg, old, new, repo


def make_venv(tmpdir: Path) -> Path:
    venv = tmpdir / "venv"
    logger.debug(f"Creating venv in {venv}")
    cmd = ["virtualenv", "--clear", "--no-wheel", "--python=python2", str(venv)]
    logger.debug("Running shell command `%s`" % " ".join(cmd))
    run(cmd, check=True, stdout=DEVNULL, stderr=PIPE)
    return venv


def run_venv(venv: Path, cmd: str, *args) -> str:
    cmd = [str(venv / "bin" / cmd)] + list(args)
    logger.debug("Running shell command `%s`" % " ".join(cmd))
    p = run(cmd, check=True, stdout=PIPE, stderr=PIPE)
    return p.stdout.decode("utf-8")


def run_pip(venv: Path, *args) -> str:
    return run_venv(venv, "pip", *args)


def check_pip_freeze(venv) -> Iterator[Tuple[str, str]]:
    for line in run_pip(venv, "freeze").split("\n"):
        if len(line) == 0:
            continue
        pkg, version = line.split("==")
        yield pkg, version


def check_package(venv: Path, pkg: Path) -> (Path, str, str or None, str or None):
    if pkg.name == "setup.py":
        pkg = pkg.parent
    logger.info(f"Checking {pkg}")
    before = set(pip_check_result(venv))
    try:
        run_pip(venv, "install", "--force-reinstall", "--no-deps", str(pkg))
    except CalledProcessError as e:
        raise e
    after = set(pip_check_result(venv))
    new = after - before
    if len(new) == 0:
        logger.warning(f"Package {str(pkg)} lacks upstream repo")
        # Fall back to pip freeze
        for name, version in check_pip_freeze(venv):
            if name == pkg.name:
                new.add((name, version, None, None))
                break
    if len(new) > 1:
        logger.warning(f"Package {str(pkg)} has pulled multiple dependencies: {str(new)}")
    for (name, old, new, repo) in new:
        return name, old, new, repo


def check_pip_show(venv: Path, pkg_list: List[str] or None = None) -> dict:
    # Name: attrs
    # Version: 18.1.0
    # Summary: Classes Without Boilerplate
    # Home-page: http://www.attrs.org/
    # Author: Hynek Schlawack
    # Author-email: hs@ox.cx
    # License: MIT
    # Location: /private/tmp/foenv/lib/python2.7/site-packages
    # Requires:
    # Required-by: pytest, mozilla-version
    if pkg_list is None:
        pkg_list = list(check_pip_freeze(venv))
    try:
        pip_out = run_pip(venv, "show", *[p for p, _ in pkg_list])
    except CalledProcessError as e:
        raise e
    result = {}
    line_dict = {}
    for pkg_out in pip_out.split("\n---\n"):
        for line in pkg_out.split("\n"):
            if len(line) == 0:
                continue
            key, *value = line.split(": ")
            value = ": ".join(value)
            line_dict[key] = value
            result[line_dict["Name"]] = line_dict
    if len(line_dict) > 0:
        result[line_dict["Name"]] = line_dict
    return result


def bulk_process(venv, all_pkgs: Iterable[Path]) -> dict:
    safety_db = SafetyDB()
    base_state = set(check_pip_freeze(venv))
    current_state = base_state.copy()
    setup_map = dict()
    for pkg_path in all_pkgs:
        logger.info(f"Processing Python package from {pkg_path}")
        try:
            # CAVE:
            # Installing Python packages si essentially arbitrary code execution.
            # We can only do this as long as we trust those setup.py files.
            run_pip(venv, "install", "--force-reinstall", "--no-deps", str(pkg_path.parent))
        except CalledProcessError as e:
            logger.error(f"Unable to install {pkg_path}. Ignoring packet")
            continue
        new_state = set(check_pip_freeze(venv))
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
    for package_name, installed_version, upstream_version, upstream_repo in pip_check_result(venv):
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
            venv = make_venv(tmpdir)
        except CalledProcessError as e:
            logger.error(f"Error while creating virtual environment: {str(e)}")
            return False
        logger.debug(f"Created virtual environment in {venv}, installing `pip-check`")

        try:
            run_pip(venv, "install", "pip-check")
        except CalledProcessError as e:
            logger.error(f"Error while installing `pip-check`: {str(e)}")
            return False

        try:
            safety_db = SafetyDB()
        except AssertionError:
            logger.error(f"Failed to fetch Safety DB from `{SafetyDB.db_url}`")
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

        rel_top_path = str(setup_path.parent.relative_to(self.hg.path))

        logger.info(f"Adding `{str(setup_path)}`")

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
        dv.add(Ns().language.name, "python")
        dv.add(Ns().fx.mc.detector.name, self.name())
        dv.add(Ns().version.spec, library_version)
        dv.add(Ns().version.type, "generic")
        dv.add(Ns().fx.mc.dir.path, rel_top_path)

        if repo_url is not None:
            dv.add(Ns().gh.repo.url, repo_url)
            dv.add(Ns().gh.repo.version, upstream_version)

        # Create file references
        for f in setup_path.parent.rglob("*"):
            logger.debug(f"Processing file {f}")
            rel_path = str(f.relative_to(self.hg.path))
            fv = self.g.new_subject()
            fv.add(Ns().fx.mc.file.path, rel_path)
            fv.add(Ns().fx.mc.file.part_of, dv)
