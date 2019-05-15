# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
import logging
from multiprocessing import Pool
from pathlib import Path
from random import randint
from tempfile import mkdtemp
from typing import Iterator, Tuple
from shutil import copytree, rmtree
from subprocess import run, PIPE, DEVNULL, CalledProcessError

from .basedetector import DependencyDetector

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


def parallel_process(args):
    venv, setup_path = args
    tempdir = Path(mkdtemp(prefix=f"mozdep_parallel_{randint(0, 1<<64)}_"))
    venv_copy = tempdir / "venvcopy"
    copytree(str(venv), str(venv_copy))

    try:
        library_name, library_version, upstream_version, repo_url = \
            check_package(venv_copy, setup_path)
    except CalledProcessError or TypeError:
        logger.warning(f"Error extracting information from `{setup_path}`")
        library_name = setup_path.parent.name
        library_version = "unknown"
        upstream_version = "unknown"
        repo_url = "unknown"

    logger.debug(f"Extracted package info: {library_name} {library_version} {upstream_version} {repo_url}")

    rmtree(str(tempdir))

    return setup_path, library_name, library_version, upstream_version, repo_url


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

        self.state = {
            "tmpdir": tmpdir,
            "venv": venv
        }

        logger.debug(f"Created virtual environment in {venv}, installing `pip-check`")

        try:
            run_pip(self.state["venv"], "install", "pip-check")
        except CalledProcessError as e:
            logger.error(f"Error while installing `pip-check`: {str(e)}")
            return False

        return True

    def run(self):

        from pprint import pprint as pp

        setup_files = list(self.hg.path.glob("third_party/python/*/setup.py"))
        worker_args = list(zip([self.state["venv"]] * len(setup_files), setup_files))

        pp(setup_files)
        pp(worker_args)

        mp = Pool()
        results = list(map(parallel_process, worker_args))
        mp.terminate()
        mp.close()
        pp(results)
        for result in results:
            self.process(result)

    def process(self, arg):
        setup_path, library_name, library_version, upstream_version, repo_url = arg
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
            lv = self.g.V(library_name).In("ns:fx.mc.lib.name").Has("ns:language.name", "cpp").AllV()[0]
        except IndexError:
            lv = self.g.add("ns:fx.mc.lib.name", library_name)
            lv.add("ns:language.name", "cpp")

        dv = self.g.add("ns:fx.mc.lib.dep.name", library_name)
        dv.add("ns:fx.mc.lib", lv)
        dv.add("ns:language.name", "python")
        dv.add("ns:fx.mc.detector.name", self.name())
        dv.add("ns:version.spec", library_version)
        dv.add("ns:version.type", "generic")
        dv.add("ns:fx.mc.dir.path", rel_top_path)

        if repo_url is not None:
            dv.add("ns:gh.repo.url", repo_url)
            dv.add("ns:gh.repo.version", upstream_version)

        # Create file references
        for f in setup_path.parent.rglob("*"):
            logger.debug(f"Processing file {f}")
            rel_path = str(f.relative_to(self.hg.path))
            fv = self.g.add("ns:fx.mc.file.path", rel_path)
            fv.add("ns:fx.mc.file.part_of", dv)
