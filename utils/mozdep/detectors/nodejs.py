# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
import logging
from pathlib import Path

from typing import Iterable

from .basedetector import DependencyDetector
import mozdep.knowledge_utils as ku
from mozdep.knowledgegraph import Ns
import mozdep.node_utils as nu

logger = logging.getLogger(__name__)


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
    unlocked_packages = set()
    npm_locked_packages = set()
    yarn_locked_packages = set()

    for p in map(nu.NodePackage, all_pkgs):
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

    result = {}
    for p in yarn_locked_packages.union(npm_locked_packages).union(unlocked_packages):
        name = p.name
        version = p.version
        repo = p.repository or ""
        upstream_version = None
        if "error" not in p.npm_view:
            if "dist-tags" in p.npm_view:
                upstream_version = p.npm_view["dist-tags"]["latest"]

        files = [p.dir / "package.json"]

        dependencies = {}
        # if p.npm_lock and "dependencies" in p.npm_lock:
        #     for d in p.npm_lock["dependencies"]:
        #         dependency_name = d
        #         dependency_version = p.npm_lock["dependencies"][d]["version"]
        #         if dependency_name not in dependencies:
        #             logger.warning(f"{p} list dependency {dependency_name} {dependency_version} outside tree")
        #             dependencies[dependency_name] = {}
        #         if dependency_version not in dependencies[dependency_name]:
        #             logger.warning(f"{p} list dependency {dependency_name} {dependency_version} outside tree")
        #             dependencies[dependency_name][dependency_version] = {}
        #         else:
        #             continue
        #         if dependency_name not in dependencies:
        #             dependencies[dependency_name] = {}
        #         if dependency_version not in dependencies[dependency_name]:
        #             dependencies[dependency_name][dependency_version] = {}
        #         dependencies[dependency_name][dependency_version] = {
        #             "name": dependency_name,
        #             "version": dependency_version,
        #             "repository": "",
        #             "required_by": p.dir / "package.json"
        #         }
        # if p.npm_lock and "_shrinkwrap" in p.npm_lock:
        #     for d in p.npm_lock["_shrinkwrap"]:
        #         dependency_name = d
        #         dependency_version = p.npm_lock["_shrinkwrap"][d]["version"]
        #         if dependency_name not in dependencies:
        #             logger.warning(f"{p} list dependency {dependency_name} {dependency_version} outside tree")
        #             dependencies[dependency_name] = {}
        #         if dependency_version not in dependencies[dependency_name]:
        #             logger.warning(f"{p} list dependency {dependency_name} {dependency_version} outside tree")
        #             dependencies[dependency_name][dependency_version] = {}
        #         else:
        #             continue
        #         if dependency_name not in dependencies:
        #             dependencies[dependency_name] = {}
        #         if dependency_version not in dependencies[dependency_name]:
        #             dependencies[dependency_name][dependency_version] = {}
        #         dependencies[dependency_name][dependency_version] = {
        #             "name": dependency_name,
        #             "version": dependency_version,
        #             "repository": "",
        #             "required_by": p.dir / "package.json"
        #         }

        # Flatten the dependency tree

        if name not in result:
            result[name] = {}
        if version not in result[name]:
            result[name][version] = {}
        result[name][version]["pkg"] = p
        result[name][version]["name"] = name
        result[name][version]["version"] = version
        result[name][version]["repository"] = repo
        result[name][version]["upstream_version"] = upstream_version
        if "files" not in result[name][version]:
            result[name][version]["files"] = files
        else:
            result[name][version]["files"] += files
        if "dependencies" not in result[name][version]:
            result[name][version]["dependencies"] = p.dependencies()
        else:
            result[name][version]["dependencies"].update(p.dependencies())

        logger.info("Node packet: %s@%s (latest: %s) repo: %s at %s", name, version,
                    upstream_version, repo, str(p.dir))

    return result

    # for p in npm_locked_packages:
    #     yield {
    #         "name": p.name,
    #         "version": p.version,
    #         "repository": p.repository,
    #         "upstream_version": p.latest_version
    #     }

    # for p in all_pkgs:
    #     pkg = NodePackage(p)
    #     if "private" in pkg.json and pkg.json["private"]:
    #         logger.debug("Found private node package %s", p)
    #     try:
    #         package_name = pkg.json["name"].split("/")[-1]
    #     except KeyError:
    #         logger.warning("Skipping nameless package %s", p)
    #         continue
    #     try:
    #         package_version = pkg.json["version"]
    #     except KeyError:
    #         logger.warning("Skipping versionless package %s", p)
    #         continue
    #     file_reference = pkg.dir / "package.json"
    #     repository_url = None
    #     if "repository" in pkg.json and type(pkg.json["repository"]) is str and len(pkg.json["repository"]) > 0:
    #         repository_url = pkg.json["repository"]
    #     if "repository" in pkg.json and type(pkg.json["repository"]) is dict and "url" in pkg.json["repository"]:
    #         repository_url = pkg.json["repository"]["url"]
    #     if package_name not in result:
    #         result[package_name] = {}
    #     if package_version not in result[package_name]:
    #         result[package_name][package_version] = {}
    #     else:
    #         logger.warning(f"{package_name} {package_version} in {p} is vendored multiple times, skipping")
    #         continue
    #     result[package_name][package_version] = {
    #         "name": package_name,
    #         "version": package_version,
    #         "repository": repository_url,
    #         "file_ref": file_reference
    #     }
    #
    #
    # from IPython import embed
    # embed()
    # return result


class NodeDependencyDetector(DependencyDetector):

    # CAVE: Not thread-safe caching method
    npm_view_cache = {}

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

        n = nu.NodeEnv()
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
        for package_name in results:
            for package_version in results[package_name]:
                self.process(results[package_name][package_version])

        # Figure out the vulnerabilities
        # TODO: Make this work for yarn-locked and unlocked packages as well
        for pkg_name in results:
            for pkg_version in results[pkg_name]:
                p = results[pkg_name][pkg_version]["pkg"]
                if p.is_npm_locked() and "advisories" in p.npm_audit:
                    for adv in p.npm_audit["advisories"].values():
                        dep_name = adv["module_name"]
                        links = [adv["url"]]
                        title = adv["title"]
                        severity = adv["severity"]
                        description = adv["overview"] + " " + adv["recommendation"]
                        weakness = adv["cwe"]
                        for finding in adv["findings"]:
                            dep_version = finding["version"]
                            logger.critical("Vulnerability %s affecting %s@%s, looking for nodes",
                                            "npm-" + str(adv["id"]), dep_name, dep_version)
                            deps = self.g.V(dep_name).In(Ns().fx.mc.lib.dep.name).Has(Ns().version.spec, dep_version)\
                                       .Has(Ns().language.name, "nodejs").All()
                            logger.critical("Found: %s", repr(deps))
                            for dep in deps:
                                ku.learn_vulnerability(self.g,
                                                       vulnerability_identifier="npm-" + str(adv["id"]),
                                                       database="npm",
                                                       info_links=links,
                                                       affects=[dep],
                                                       title=title,
                                                       description=description,
                                                       weakness_identifier=weakness,
                                                       severity=severity)

    def process(self, pd):
        logger.debug("Processing %s", repr(pd))

        library_name = pd["name"] if "name" in pd else "_unknown_package"
        library_version = pd["version"] if "version" in pd else "__unknown_version"
        repo_url = pd["repository"] if "repository" in pd and len(pd["repository"]) > 0 else "_unknown"
        upstream_version = pd["upstream_version"] or "_unknown"
        setup_path = pd["files"][0]

        logger.debug(f"Adding package info: {library_name} {library_version} {upstream_version} {repo_url}")

        # TODO: extract vulnerability information

        if library_name is not None and library_version is not None:
            _ = ku.learn_dependency(self.g,
                                    name=library_name,
                                    version=library_version,
                                    detector_name=self.name(),
                                    language="nodejs",
                                    version_type="_generic",
                                    upstream_version=upstream_version,
                                    top_path=self.hg.path,
                                    tree_path=self.hg.path,
                                    repository_url=repo_url,
                                    files=[setup_path],
                                    vulnerabilities=None)

        for dep in pd["dependencies"]:
            nv = dep.npm_view
            try:
                latest_version = nv["dist-tags"]["latest"]
            except KeyError:
                latest_version = None
            try:
                if type(nv["repository"]) is str:
                    repo_url = nu.normalize_repository(nv["repository"])
                else:
                    repo_url = nu.normalize_repository(nv["repository"]["url"])
            except KeyError:
                repo_url = None
            _ = ku.learn_dependency(self.g,
                                    name=dep.name,
                                    version=dep.version,
                                    detector_name=self.name(),
                                    language="nodejs",
                                    version_type="_generic",
                                    upstream_version=latest_version,
                                    top_path=None,
                                    tree_path=self.hg.path,
                                    repository_url=repo_url,
                                    files=None,
                                    vulnerabilities=None)
