# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
from json import load, loads, dump
import logging
from pathlib import Path
from re import match
from requests import head
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


def check_url(url: str) -> bool:
    r = head(url)
    return 200 <= r.status_code < 300


def normalize_repository(repo: str) -> str:
    # Try to normalize some of the repo schemes.
    # Schemes observed so far:
    # hg+https://
    # git+http://
    # git+https://
    # git+ssh://
    # git://
    # http://
    # github:<githubuser>/<githubrepo>
    # <githubuser>/<githubrepo>

    # Normalize
    if len(repo) > 0:
        logger.debug(f"Normalizing repo string `%s`", repo)

    if repo.startswith("github:"):
        repo = f"https://github.com/{repo[7:]}"

    if len(repo) > 0 and "://" not in repo:
        # Probably <githubuser>/<githubrepo>
        repo = f"https://github.com/{repo}"

    if repo.startswith("git+"):
        repo = repo[4:]

    if repo.startswith("hg+"):
        repo = repo[3:]

    if repo is None:
        repo = ""

    if "github.com" in repo:
        m = match(r""".*github.com/(.+?)/(.+?)(.git)?$""", repo)
        if m is not None:
            repo = f"https://github.com/{m[1]}/{m[2]}"
        else:
            logger.warning(f"Repo URL looks like GitHub repo, but does not exist: {repo}")

    if len(repo) > 0:
        logger.debug("Normalization result: `%s`", repo)

    return repo


class NodeError(Exception):
    pass


def npm_view(npm_bin: Path, package: Path or str) -> dict:
    """
    Call `npm view` on either a local package path or a package ref string.
    Return result as json.

    :param npm_bin: Path to npm binary
    :param package: Path to package or str with package spec
    :return: dict with JSON returned by npm
    """
    if type(package) is str:
        npm_cmd = [str(npm_bin), "view", "--json", package]
        logger.debug("Running `%s`", " ".join(npm_cmd))
        p = run(npm_cmd, stdout=PIPE, stderr=PIPE)
    else:
        npm_cmd = [str(npm_bin), "view", "--json"]
        logger.debug("Running `%s` in `%s`", " ".join(npm_cmd), str(package))
        p = run(npm_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    view_json = loads(p.stdout.decode("utf-8"))
    return view_json


def npm_audit(npm_bin: Path, package: Path) -> dict:
    """
    Call `npm audit` on a local package path. Path must contain lock file.
    Return result as json.

    :param npm_bin: Path to npm binary
    :param package: Path to package
    :return: dict with JSON returned by npm
    """
    npm_cmd = [str(npm_bin), "audit", "--json"]
    logger.debug("Running `%s` in `%s`", " ".join(npm_cmd), str(package))
    p = run(npm_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    audit_json = loads(p.stdout.decode("utf-8"))
    return audit_json


def npm_list(npm_bin: Path, package: Path) -> dict:
    """
    Call `npm list` on a local package path. Path must contain lock file.
    Return result as json.

    :param npm_bin: Path to npm binary
    :param package: Path to package
    :return: dict with JSON returned by npm
    """
    npm_cmd = [str(npm_bin), "list", "--long", "--json"]
    logger.debug("Running `%s` in `%s`", " ".join(npm_cmd), str(package))
    p = run(npm_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    list_json = loads(p.stdout.decode("utf-8"))
    return list_json


def yarn_audit(yarn_bin: Path, package: Path) -> list:
    """
    Call `yarn audit` on a local package path. Path must contain lock file.
    Return result as json.

    :param yarn_bin: Path to yarn binary
    :param package: Path to package
    :return: list with JSON returned by npm
    """
    yarn_cmd = [str(yarn_bin), "audit", "--json"]
    logger.debug("Running `%s` in `%s`", " ".join(yarn_cmd), str(package))
    p = run(yarn_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    audit_json = []
    for l in p.stdout.decode("utf-8").split("\n"):
        if len(l) > 1:
            audit_json.append(loads(l))
    return audit_json


class NodePackage(object):

    _npm_bin = find_executable("npm.exe") or find_executable("npm")
    _yarn_bin = find_executable("yarn.exe") or find_executable("yarn")

    def __init__(self, package: Path):
        if self._npm_bin is None:
            raise NodeError("Unable to find npm binary")
        if self._yarn_bin is None:
            raise NodeError("Unable to find yarn binary")
        if package.name == "package.json":
            self.dir = package.parent
        elif (package / "package.json").exists():
            self.dir = package
        else:
            raise NodeError(f"Unable to recognize node package at {package}")
        self._json: dict or None = None
        self._npm_lock: dict or None = None
        self._yarn_lock: list or None = None
        self._repository: str or None = None
        self._npm_view: dict or None = None
        self._npm_list: dict or None = None
        self._npm_audit: dict or None = None
        self._yarn_audit: list or None = None
        self._str = None

    def is_npm_locked(self):
        return (self.dir / "package-lock.json").exists() or (self.dir / "npm-shrinkwrap.json").exists()

    def is_yarn_locked(self):
        return (self.dir / "yarn.lock").exists()

    def is_locked(self):
        return self.is_npm_locked() or self.is_yarn_locked()

    @property
    def json(self):
        if self._json is None:
            with (self.dir / "package.json").open() as f:
                self._json = load(f)
        return self._json

    @property
    def npm_lock(self):
        if self._npm_lock is None and self.is_npm_locked():
            if (self.dir / "package-lock.json").exists():
                with (self.dir / "package-lock.json").open() as f:
                    self._npm_lock = load(f)
            elif (self.dir / "npm-shrinkwrap.json").exists():
                with (self.dir / "npm-shrinkwrap.json").open() as f:
                    self._npm_lock = load(f)
            else:
                raise NodeError(f"Internal error: {self} is marked locked but without lock file")
        return self._npm_lock

    @property
    def yarn_lock(self):
        if self._npm_lock is None and self.is_yarn_locked():
            with (self.dir / "yarn.lock").open() as f:
                self._npm_lock = load(f)
        return self._npm_lock

    def is_private(self):
        return "private" in self.json and self.json["private"]

    @property
    def repository(self):
        if self._repository is None:
            if "repository" not in self.json:
                self._repository = ""
            elif type(self.json["repository"]) is str:
                self._repository = self.json["repository"]
            elif type(self.json["repository"]) is dict and "url" in self.json["repository"]:
                self._repository = self.json["repository"]["url"]
            else:
                self._repository = ""
            self._repository = normalize_repository(self._repository)

        if len(self._repository) == 0:
            return None
        else:
            return self._repository

    @property
    def npm_view(self) -> dict:
        if self._npm_view is None:
            self._npm_view = npm_view(self._npm_bin, self.dir)
        return self._npm_view

    @property
    def npm_list(self) -> dict:
        if self._npm_list is None:
            self._npm_list = npm_list(self._npm_bin, self.dir)
        return self._npm_list

    @property
    def npm_audit(self) -> dict:
        if self._npm_audit is None:
            self._npm_audit = npm_audit(self._npm_bin, self.dir)
        return self._npm_audit

    @property
    def yarn_audit(self) -> dict:
        if self._yarn_audit is None:
            self._yarn_audit = yarn_audit(self._yarn_bin, self.dir)
        return self._yarn_audit

    def __repr__(self):
        return f"NodePackage('{str(self.dir)}/package.json')"

    def __hash__(self):
        return hash(str(self))

    @property
    def name(self):
        return self.json["name"] if "name" in self.json else None

    @property
    def version(self):
        return self.json["version"] if "version" in self.json else None

    @property
    def latest_version(self):
        try:
            return self.npm_view["dist-tags"]["latest"]
        except KeyError:
            return None

    def dependencies(self):
        if self.is_npm_locked():
            if "dependencies" in self.npm_lock:
                for dep in self.npm_lock["dependencies"]:
                    yield dep, self.npm_lock["dependencies"][dep]["version"]

    def __str__(self):
        if self._str is None:
            name = self.name or "_ANONYMOUS"
            version = self.version or "_UNVERSIONED"
            self._str = f"{name}@{version} [{str(self.dir)}]"
        return self._str


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
    """
    The algorithm for processing node dependencies in the repo:

    For every package.json file in tree:
    1. Run `npm view` on directory and register as dependency.
    2. If there's a package-lock.json, call `npm audit` and evaluate result.
    3. If there's a yarn.lock call `yarn audit` and evaluate result. (TODO)
    4. If there is no lock file, run `npm install --package-lock-only`
       in temporary node env and proceed like 2.

    For every external dependency that's not been evaluated so far:
    1. Call `npm view` and evaluate result, register all dependencies.
    2. Repeat until all dependencies covered.

    False negatives:
    - Packages vendored into the tree might have dependencies down the
      tree that aren't covered yet.

    False positives:
    - dependencies are registered regardless of their type, and regardless
      of whether they're actually loaded/used.
    """
    result = {}
    unlocked_packages = set()
    npm_locked_packages = set()
    yarn_locked_packages = set()

    for p in map(NodePackage, all_pkgs):
        if p.is_npm_locked():
            # Handled by `npm view` and `npm audit`
            npm_locked_packages.add(p)
            if p.is_yarn_locked():
                logger.warning(f"Node package {str(p.dir)} is double-locked. "
                               f"package-lock.json takes precedence over yarn.lock")
        elif p.is_yarn_locked():
            # Handled by `yarn view` and `yarn audit`
            yarn_locked_packages.add(p)
        else:
            # Handled by temporary locking and `npm view` and `npm audit`
            unlocked_packages.add(p)

    logger.info("Node stats: detected %d/%d/%d yarn-locked/npm-locked/unlocked packages",
                len(yarn_locked_packages), len(npm_locked_packages), len(unlocked_packages))

    for p in yarn_locked_packages:
        logger.debug("yarn-locked package %s", str(p))
    for p in npm_locked_packages:
        logger.debug("npm-locked package %s", str(p))
        # results = join_results(npm_view_analysis(p), npm_audit_analysis(p))
    for p in unlocked_packages:
        logger.debug("unlocked package %s", str(p))

    for p in yarn_locked_packages.union(npm_locked_packages).union(unlocked_packages):
        deps = set()
        name = p.name
        version = p.version
        repo = p.repository
        upstream_version = None
        if not "error" in p.npm_view:
            if "dist-tags" in p.npm_view:
                upstream_version = p.npm_view["dist-tags"]["latest"]
        logger.info("Node dependency: %s@%s (latest: %s) repo: %s", name, version, upstream_version, repo)

    from IPython import embed
    embed()

    # for p in npm_locked_packages:
    #     yield {
    #         "name": p.name,
    #         "version": p.version,
    #         "repository": p.repository,
    #         "upstream_version": p.latest_version
    #     }

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
        if pkg.npm_lock is None:
            continue
        for d in pkg.npm_lock["dependencies"]:
            dependency_name = d.split("/")[-1]
            dependency_version = pkg.npm_lock["dependencies"][d]["version"]
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
        npm_bin = find_executable("npm.exe") or find_executable("npm")
        if npm_bin is None:
            logger.error("Cannot find `npm`")
            return False
        logger.debug("Using npm executable at %s", npm_bin)

        yarn_bin = find_executable("yarn.exe") or find_executable("yarn")
        if yarn_bin is None:
            logger.error("Cannot find `yarn`. Hint: run `npm install -g yarn`")
            return False
        logger.debug("Using yarn executable at %s", yarn_bin)

        n = NodeEnv()
        logger.debug(f"Created node environment in {n.path}")

        self.state = {
            "node_env": n,
            "npm_bin": npm_bin,
            "yarn_bin": yarn_bin
        }

        return True

    def run(self):
        logger.info("Looking for `package.json` files...")
        package_files = list(self.hg.find("package.json"))
        logger.debug("Found: %s", package_files)
        results = bulk_process(self.state["node_env"], package_files)
        # for result in results.items():
        #     self.process(result)

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
