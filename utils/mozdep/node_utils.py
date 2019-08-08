# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
from functools import lru_cache
from json import load, loads, dump
import logging
from pathlib import Path
from re import match
from requests import head
from shutil import rmtree
from subprocess import run, PIPE
from tempfile import mkdtemp, TemporaryDirectory
from typing import List

from mozdep.cleanup import CleanUp

logger = logging.getLogger(__name__)
tmp_dir = Path(mkdtemp(prefix="mozdep_nodeenv_"))

npm_bin = find_executable("npm.exe") or find_executable("npm")
yarn_bin = find_executable("yarn.exe") or find_executable("yarn")


class NodeError(Exception):
    pass


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
            logger.warning("Malformed GitHub repo: `%s`", repo)

    if len(repo) > 0:
        logger.debug("Normalization result: `%s`", repo)

    return repo


@lru_cache(maxsize=None)
def npm_view(package: Path or str) -> dict:
    """
    Call `npm view` on either a local package path or a package ref string.
    Return result as json.

    :param package: Path to package or str with package spec
    :return: dict with JSON returned by npm
    """
    global npm_bin
    if npm_bin is None:
        raise NodeError("Unable to find npm binary")

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


@lru_cache(maxsize=None)
def npm_audit(package: Path) -> dict:
    """
    Call `npm audit` on a local package path. Path must contain lock file.
    Return result as json.

    :param package: Path to package
    :return: dict with JSON returned by npm
    """
    global npm_bin
    if npm_bin is None:
        raise NodeError("Unable to find npm binary")

    npm_cmd = [str(npm_bin), "audit", "--json"]
    logger.debug("Running `%s` in `%s`", " ".join(npm_cmd), str(package))
    p = run(npm_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    audit_json = loads(p.stdout.decode("utf-8"))
    return audit_json


@lru_cache(maxsize=None)
def npm_list(package: Path) -> dict:
    """
    Call `npm list` on a local package path. Path must contain lock file.
    Return result as json.

    :param package: Path to package
    :return: dict with JSON returned by npm
    """
    global npm_bin
    if npm_bin is None:
        raise NodeError("Unable to find npm binary")

    npm_cmd = [str(npm_bin), "list", "--long", "--json"]
    logger.debug("Running `%s` in `%s`", " ".join(npm_cmd), str(package))
    p = run(npm_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    list_json = loads(p.stdout.decode("utf-8"))
    return list_json


@lru_cache(maxsize=None)
def yarn_audit(package: Path) -> list:
    """
    Call `yarn audit` on a local package path. Path must contain lock file.
    Yarn can work with npm-based lock files and shrinkwraps, too.
    Return result as json.

    :param package: Path to package
    :return: list with JSON dicts returned by yarn
    """
    global yarn_bin
    if yarn_bin is None:
        raise NodeError("Unable to find yarn binary")

    yarn_cmd = [str(yarn_bin), "audit", "--json"]
    logger.debug("Running `%s` in `%s`", " ".join(yarn_cmd), str(package))
    p = run(yarn_cmd, stdout=PIPE, stderr=PIPE, cwd=str(package))
    audit_json = []
    for l in p.stdout.decode("utf-8").split("\n"):
        if len(l) > 1:
            audit_json.append(loads(l))
    return audit_json


class NodePackage(object):

    def __init__(self, package: Path or str):
        """
        A node package can bei either specified by a regular node reference string
        like @foo/bar@0.0.1, or bar@0.0.2, or by a local path to a node module.

        :param package: Path or str
        """

        if type(package) is str:
            self.ref = package
            self.dir = None
        elif package.name == "package.json":
            self.ref = None
            self.dir = package.parent
        elif (package / "package.json").exists():
            self.ref = None
            self.dir = package
        else:
            raise NodeError(f"Unable to recognize node package reference `{package}`")

        self._json: dict or None = None
        self._npm_lock: dict or None = None
        self._yarn_lock: list or None = None
        self._repository: str or None = None
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
        if self._yarn_lock is None and self.is_yarn_locked():
            with (self.dir / "yarn.lock").open() as f:
                self._yarn_lock = load(f)
        return self._yarn_lock

    def is_private(self):
        return "private" in self.json and self.json["private"]

    @property
    def name(self):
        if self.ref:
            return "@".join(self.ref.split("@")[:-1])
        if "name" in self.json:
            return self.json["name"]
        if self.dir:
            return self.dir.name
        return None

    @property
    def version(self):
        if self.ref:
            return self.ref.split("@")[-1]
        if "version" in self.json:
            return self.json["version"]
        return None

    @property
    def name(self):
        if self.ref:
            return "@".join(self.ref.split("@")[:-1])
        if "name" in self.json:
            return self.json["name"]
        if self.dir:
            return self.dir.name
        return None

    @property
    def version(self):
        if self.ref:
            return self.ref.split("@")[-1]
        if "version" in self.json:
            return self.json["version"]
        return None

    @property
    def latest_version(self):
        try:
            return self.npm_view["dist-tags"]["latest"]
        except KeyError:
            return None

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
        if self.dir:
            return npm_view(self.dir)
        else:
            return npm_view(self.ref)

    @property
    def npm_list(self) -> dict:
        if self.dir:
            return npm_list(self.dir)
        else:
            raise NotImplemented(f"Ad-hock locking of unlocked {self} is not implemented")

    @property
    def npm_audit(self) -> dict:
        if self.dir:
            return npm_audit(self.dir)
        else:
            raise NotImplemented(f"Ad-hock locking of unlocked {self} is not implemented")

    @property
    def yarn_audit(self) -> list:
        if self.dir:
            return yarn_audit(self.dir)
        else:
            raise NotImplemented(f"Ad-hock locking of unlocked {self} is not implemented")

    def dependencies(self):

        if not self.npm_list:
            raise NodeError(f"Unable to extract dependencies from unlocked package {self}")

        # if "dependencies" not in self.npm_list:
        #     return {}
        #
        # deps = {}
        #
        # sections = ("dependencies", "devDependencies", "optionalDependencies")
        # todo = []
        # for section in sections:
        #     if section in self.npm_list and type(self.npm_list[section]) is not dict:
        #         continue
        #     todo += [x for x in self.npm_list[section].values()] if section in self.npm_list else []
        #
        # while len(todo) > 0:
        #     logger.error(todo)
        #     d = todo.pop()
        #     # Descent into dependency tree
        #     for section in sections:
        #         if section in d and type(d[section]) is not dict:
        #             continue
        #         todo += [x for x in d[section].values()] if section in d else []
        #     if "name" not in d:
        #         logger.warning(f"Skipping nameless dependency for {self}")
        #         continue
        #     dependency_name = d["name"]
        #     dependency_version = d["version"]
        #     if dependency_version.startswith("^"):
        #         continue
        #     if dependency_version.startswith("="):
        #         logger.error("Don't know how to handle pinned dependency %s@%s in %s",
        #                      dependency_name, dependency_version, self)
        #         continue
        #     dependency_path = Path(d["path"]) if "path" in d else None
        #     if dependency_name not in deps:
        #         deps[dependency_name] = {}
        #     if dependency_version not in deps[dependency_name]:
        #         deps[dependency_name][dependency_version] = {}
        #     deps[dependency_name][dependency_version] = {
        #         "name": dependency_name,
        #         "version": dependency_version,
        #         "package_path": dependency_path / "package.json" if dependency_path else None,
        #         "required_by": self
        #     }

        # _shrinkwrap represents a flattened view of the dependency tree, much easier to parse
        # and without polymorphism in the data.
        deps = set()
        try:
            for dep_name, dep_data in self.npm_list["_shrinkwrap"]["dependencies"].items():
                deps.add(NodePackage(f"{dep_name}@{dep_data['version']}"))
        except TypeError:
            return deps
        return deps

    def __str__(self):
        if self._str is None:
            name = self.name or "_ANONYMOUS"
            version = self.version or "_UNVERSIONED"
            path = str(self.dir) if self.dir else "_NO_LOCAL_PATH"
            self._str = f"NodePackage {name}@{version} [{path}]"
        return self._str

    def __repr__(self):
        if self.dir:
            return f"NodePackage('{str(self.dir)}/package.json')"
        else:
            return f"NodePackage('{self.ref}')"

    def __hash__(self):
        return hash(str(self))


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
