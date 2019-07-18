# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
from json import load
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
    result = dict()
    for p in all_pkgs:
        with open(p) as f:
            j = load(f)
        result[p] = j
    return result


class NodeDependencyDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "node"

    @staticmethod
    def priority() -> int:
        return 80

    def setup(self) -> bool:
        if find_executable("npm") is None:
            logger.error("Cannot find `npm`")
            return False

        tmpdir = Path(mkdtemp(prefix="mozdep_"))
        try:
            venv = make_venv(tmpdir)
        except CalledProcessError as e:
            logger.error(f"Error while creating node environment: {str(e)}")
            return False
        logger.debug(f"Created node environment in {venv}, installing `node-foo`")

        # try:
        #     run_pip(venv, "install", "pip-check")
        # except CalledProcessError as e:
        #     logger.error(f"Error while installing `pip-check`: {str(e)}")
        #     return False

        self.state = {
            "tmpdir": tmpdir,
            "venv": venv
        }

        return True

    def run(self):
        # setup_files = list(self.hg.path.glob("third_party/python/*/setup.py"))
        setup_files = list(self.hg.find("package.json"))
        results = bulk_process(self.state["venv"], setup_files)

        for result in results.items():
            self.process(result)

    def process(self, arg):
        p, j = arg

        logger.debug("Processing %s", p)

        name = j["name"] if "name" in j else "unknown_package"
        version = j["version"] if "version" in j else "unknown_version"
        repo = repr(j["repository"]) if "repository" in j and len(j["repository"]) > 0 else "unknown_repo"
        private = "private_true" if "private" in j and j["private"] else "private_false"
        deps = {}
        if "dependencies" in j:
            for dep, ver in j["dependencies"].items():
                deps[dep] = ver
        dev_deps = {}
        if "devDependencies" in j:
            for dep, ver in j["devDependencies"].items():
                dev_deps[dep] = ver

        if private == "private_true" and repo == "unknown_repo" and len(deps) + len(dev_deps) == 0:
            logger.warning(f"Ignoring dependency-free private node package without upstream repo: {p}")
            return

        print(f"{p}: {name}@{version}, {repo}, {private}, {deps}, {dev_deps}")
        return

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
