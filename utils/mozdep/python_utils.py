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
from shutil import rmtree
from tempfile import mkdtemp
from typing import Iterator, Tuple, List
from subprocess import run, PIPE, DEVNULL, CalledProcessError

from mozdep.cleanup import CleanUp

logger = logging.getLogger(__name__)
tmp_dir = Path(mkdtemp(prefix="mozdep_python_utils_"))

virtualenv_bin = find_executable("virtualenv.exe") or find_executable("virtualenv")


class RemoveRepoTmpdir(CleanUp):
    @staticmethod
    def at_exit():
        global tmp_dir
        if tmp_dir.exists():
            logger.debug("Removing temporary directory at `%s`", tmp_dir)
            rmtree(tmp_dir)


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
    global virtualenv_bin
    venv = tmpdir / "venv"
    logger.debug(f"Creating venv in {venv}")
    cmd = [str(virtualenv_bin), "--clear", "--no-wheel", "--python=python2", str(venv)]
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
        if line.startswith("-e "):
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
