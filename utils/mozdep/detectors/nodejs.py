# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
from json import load, loads, dump
import logging
from pathlib import Path
from shutil import rmtree
from subprocess import run, PIPE, DEVNULL, CalledProcessError
from tempfile import mkdtemp, TemporaryDirectory
from typing import Iterator, Tuple, Iterable, List

from .basedetector import DependencyDetector
from mozdep.knowledgegraph import Ns
from mozdep.cleanup import CleanUp

logger = logging.getLogger(__name__)
tmp_dir = Path(mkdtemp(prefix="mozdep_nodeenv_"))


class RemoveTmpdir(CleanUp):
    @staticmethod
    def at_exit():
        global tmp_dir
        if tmp_dir.exists():
            rmtree(tmp_dir)


class NodeError(Exception):
    pass


class NodePackage(object):
    def __init__(self, package: Path):
        if package.name == "package.json":
            self.dir = package.parent
        elif (package / "package.json").exists():
            self.dir = package
        else:
            raise NodeError(f"Unable to recognize node package at {package}")
        self._json = None
        self._lock = None

    @property
    def json(self):
        if self._json is None:
            with open(self.dir / "package.json") as f:
                self._json = load(f)
        return self._json

    @property
    def lock(self):
        if self._lock is None and (self.dir / "package-lock.json").exists():
            with open(self.dir / "package-lock.json") as f:
                self._json = load(f)
        return self._lock


class NodeEnv(object):
    def __init__(self, name: str = "default"):
        global tmp_dir
        self.npm_bin = find_executable("npm.exe") or find_executable("npm")
        if self.npm_bin is None:
            raise NodeError("Unable to find npm binary")
        self.npm_bin = Path(self.npm_bin).absolute()
        self.name = name
        self.path = tmp_dir / self.name
        # If node_modules does not exist, npm will start looking for one up the tree.
        (self.path / "node_modules").mkdir(mode=0o755, parents=True, exist_ok=True)
        if not (self.path / "package.json").exists():
            with (self.path / "package.json").open("w") as f:
                dump({
                    "name": self.name,
                    "version": "0.0.0",
                    "description": "dummy package",
                    "dependencies": {},
                    "devDependencies": {},
                    "license": "MPL-2.0",
                    "private": True,
                    "scripts": {
                        "retire": "retire",
                        "test": """echo "Error: no test specified" && exit 1"""
                    }
                }, f, indent=4)

    def npm(self, args: List[str] = None, *, cwd=None):
        args = args or []
        npm_cmd = [str(self.npm_bin), "--prefix", str(self.path), "--json"] + args
        logger.debug("Running `%s`", " ".join(npm_cmd))
        p = run(npm_cmd, stdout=PIPE, stderr=PIPE, cwd=cwd or self.path)
        # Some npm subcommands (ie. pack) litter into their json output
        out = ""
        for line in p.stdout.decode("utf-8").split("\n"):
            if not line.startswith(">"):
                out += line + "\n"
        logger.debug("Command result: %s", repr(out))
        return loads(out)

    def list(self):
        return self.npm(["list"])

    def run(self, script: str, args: List[str] = None):
        args = args or []
        return self.npm(["run", script, "--"] + args)

    def install(self, package: str or Path):
        if issubclass(type(package), Path):
            if package.name == "package.json":
                package = package.parent
            else:
                if not (package / "package.json").exists():
                    raise NodeError(f"No `package.json` in `{str(package)}`")

        # npm refuses to copy local package files, always creates symlink.
        # Only workaround seems o be to create tgz package first, then install that.
        with TemporaryDirectory(prefix="npm_install_tgz_") as tmp:
            pack_result = self.npm(["pack", str(package)], cwd=tmp)
            if "error" in pack_result:
                raise NodeError(f"npm pack failed: {repr(pack_result)}")
            if len(pack_result) != 1:
                raise NodeError(f"npm failed should deliver a single result: "
                                f"{repr(pack_result)}")
            install_result = self.npm(["install", "-P", "-E", "--ignore-scripts",
                                       pack_result[0]["filename"]], cwd=tmp)
            if "error" in install_result:
                raise NodeError(f"npm failed: {repr(install_result)}")
            return install_result

    def audit(self):
        return self.npm(["audit"])


def bulk_process(node_env, all_pkgs: Iterable[Path]):
    result = {}
    for p in all_pkgs:
        pkg = NodePackage(p)
        if "private" in pkg.json and pkg.json["private"]:
            logger.debug("Found private node package %s", p)
        try:
            package_name = pkg.json["name"].split("/")[-1]
        except KeyError:
            logger.warning("Skipping nameless package %s", p)
            continue
        try:
            package_version = pkg.json["version"]
        except KeyError:
            logger.warning("Skipping versionless package %s", p)
            continue
        file_reference = pkg.dir / "package.json"
        repository_url = None
        if "repository" in pkg.json and type(pkg.json["repository"]) is str and len(pkg.json["repository"]) > 0:
            repository_url = pkg.json["repository"]
        if "repository" in pkg.json and type(pkg.json["repository"]) is dict and "url" in pkg.json["repository"]:
            repository_url = pkg.json["repository"]["url"]
        if package_name not in result:
            result[package_name] = {}
        if package_version not in result[package_name]:
            result[package_name][package_version] = {}
        else:
            logger.warning(f"{package_name} {package_version} in {p} is vendored multiple times, skipping")
            continue
        result[package_name][package_version] = {
            "name": package_name,
            "version": package_version,
            "repository": repository_url,
            "file_ref": file_reference
        }

    for p in all_pkgs:
        pkg = NodePackage(p)
        if pkg.lock is None:
            continue
        for d in pkg.lock["dependencies"]:
            dependency_name = d.split("/")[-1]
            dependency_version = pkg.lock["dependencies"][d]["version"]
            if dependency_name not in result:
                logger.warning(f"{p} list dependency {dependency_name} {dependency_version} outside tree")
                result[dependency_name] = {}
            if dependency_version not in result[dependency_name]:
                logger.warning(f"{p} list dependency {dependency_name} {dependency_version} outside tree")
                result[dependency_name][dependency_version] = {}
            else:
                continue
            result[dependency_name][dependency_version] = {
                "name": dependency_name,
                "version": dependency_version,
                "repository": None,
                "file_ref": pkg.dir / "package-lock.json"
            }

    from IPython import embed
    embed()
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

        n = NodeEnv()
        logger.debug(f"Created node environment in {n.path}")

        self.state = {
            "node_env": n
        }

        return True

    def run(self):
        # setup_files = list(self.hg.path.glob("third_party/python/*/setup.py"))
        logger.debug("Scanning for `package.json` files")
        package_files = list(self.hg.find("package.json"))
        logger.debug("Found: %s", package_files)

        logger.debug("Scanning for `package-lock.json` files")
        lock_files = list(self.hg.find("package-lock.json"))
        logger.debug("Found: %s", lock_files)
        # Ensure there are no rogue lock files around
        for l in lock_files:
            if not (l.parent / "package.json").exists():
                logger.warning("Found rogue lock file: %s", l)

        results = bulk_process(self.state["node_env"], package_files)

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
