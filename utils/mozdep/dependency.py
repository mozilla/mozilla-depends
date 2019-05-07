# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from abc import ABC, abstractmethod
from pathlib import PosixPath, Path
import itertools
from typing import Iterator
import logging
from subprocess import run, check_output, check_call, DEVNULL, PIPE, CalledProcessError
from json import loads, decoder
import os
import toml
import yaml
import urllib.request

from .tree import HgRepo, get_mozilla_component

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


class DependencyDescriptor(object):

    def __init__(self, detector, data: dict):
        self.detector = detector.name
        self.dependants = data["dependants"]
        self.dependencies = data["dependencies"]
        self.name = data["name"]
        self.repo_top_directory = data["repo_top_directory"]
        self.repo_files = data["repo_files"]
        self.sourcestamp = data["sourcestamp"]
        self.target_store = data["target_store"]
        self.upstream_ref = data["upstream_ref"]
        self.version = data["version"]

    def __str__(self):
        return f"<DependencyDescriptor from {self.detector}: `{self.target_store}: {self.name}-{self.version}`>"


class DependencyDetector(ABC):
    """
    Abstract base class for detectors, scanning a local copy of
    mozilla-central for in-tree third-party dependencies.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        return "dummy"

    def __init__(self, tree: Path, **kwargs):
        self.args = kwargs
        self.result = None
        self.hg = HgRepo(tree)
        self.state = None
        super().__init__()

    def prepare(self) -> bool:
        return True

    @abstractmethod
    def run(self) -> Iterator[DependencyDescriptor]:
        yield None

    def is_scanning(self) -> bool:
        return self.result is None

    def wait(self) -> None:
        return


class CargoTomlDependencyDetector(DependencyDetector):

    @property
    def name(self) -> str:
        return "cargotoml"

    def prepare(self):
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
        self.result = None
        for ctf in self.hg.find("Cargo.toml"):
            logger.debug("Parsing %s" % ctf)
            rp = RustPackage(ctf)
            for d in self.as_dependency_descriptor(rp):
                if d is not None:
                    yield d

    def as_dependency_descriptor(self, rp: RustPackage):
        key = rp.name + "-" + rp.version
        try:
            deps = list(self.state["deps"][key])
        except KeyError:
            deps = []
        dd = DependencyDescriptor(self, {
            "name": rp.name,
            "version": rp.version,
            "repo_top_directory": rp.path,
            "repo_files": list(self.hg.find(start=rp.path)),
            "target_store": "RustStore",
            "dependants": [],
            "dependencies": deps,
            "sourcestamp": self.hg.source_stamp,
            "upstream_ref": rp.repository,
        })
        yield dd


class MozYamlDependencyDetector(DependencyDetector):

    @property
    def name(self) -> str:
        return "mozyaml"

    def run(self):
        for m in self.hg.find("moz.yaml"):
            for d in self.as_dependency_descriptor(m):
                if d is not None:
                    yield d

    def as_dependency_descriptor(self, file_path: Path):
        with file_path.open() as f:
            logger.debug(f"Parsing {str(file_path)} as YAML")
            try:
                y = yaml.load(f, Loader=yaml.SafeLoader)
                dd = DependencyDescriptor(self, {
                    "name": y["origin"]["name"],
                    "version": y["origin"]["release"],
                    "repo_top_directory": file_path.parent,
                    "repo_files": list(file_path.rglob("*")),
                    "target_store": "JsStore",
                    "dependants": [],
                    "dependencies": [],
                    "sourcestamp": self.hg.source_stamp,
                    "upstream_ref": None,
                })
                yield dd
            except yaml.scanner.ScannerError:
                logger.error(f"Broken YAML in {str(file_path)}. Ignoring file")
                yield None


class RetireDependencyDetector(DependencyDetector):

    @property
    def name(self) -> str:
        return "retire"

    def prepare(self) -> bool:
        if "retire_bin" in self.args:
            retire_bin = self.args["retire_bin"]
        else:
            try:
                cmd = ["npm", "bin"]
                node_bin_path = check_output(cmd).decode("utf-8").split()[0]
            except FileNotFoundError:
                logger.critical("Node Package Manager not found")
                return False
            retire_bin = os.path.join(node_bin_path, "retire")
            logger.debug("Checking `%s`" % retire_bin)
            if not os.path.isfile(retire_bin):
                if os.path.isfile("%s.exe" % retire_bin):
                    retire_bin = "%s.exe" % retire_bin
                    logger.debug("Checking `%s`" % retire_bin)
                else:
                    logger.critical("Unable to find retire.js binary")
                    return False
            self.args["retire_bin"] = retire_bin
        logger.debug("Using retire.js binary at `%s`" % retire_bin)
        cmd = [retire_bin, "--version"]
        try:
            check_call(cmd, stdout=DEVNULL, stderr=DEVNULL)
        except CalledProcessError as e:
            logger.critical("Error running retire.js binary: `%s`" % str(e))
            return False
        return True

    def run(self):
        cmd = [
            self.args["retire_bin"],
            "--outputformat", "json",
            "--outputpath", "/dev/stdout",
            "--path", str(self.hg.path),
            "--ignore", str(self.hg.path / ".hg"),
            "--verbose"
        ]
        logger.debug("Running shell command `%s`" % " ".join(cmd))
        cmd_output = run(cmd, check=False, stdout=PIPE, stderr=DEVNULL).stdout
        logger.debug("Shell command output: `%s`" % cmd_output)
        try:
            result = loads(cmd_output.decode("utf-8"))
        except decoder.JSONDecodeError:
            logger.warning("retirejs call failed, probably due to network failure")
            logger.warning("Failing output is `%s`" % cmd_output)
            raise Exception("Retire.js failed to run, likely due to network error")
        for r in result["data"]:
            for d in self.as_dependency_descriptor(r):
                if d is not None:
                    yield d

    def as_dependency_descriptor(self, data: dict):
        fp = Path(data["file"]).resolve()
        for r in data["results"]:
            dd = DependencyDescriptor(self, {
                "name": r["component"],
                "version": r["version"],
                "repo_top_directory": fp.parent,
                "repo_files": [fp],
                "target_store": "JsStore",
                "dependants": [],
                "dependencies": [],
                "sourcestamp": self.hg.source_stamp,
                "upstream_ref": None,
            })
            yield dd


class ThirdPartyAlertDetector(DependencyDetector):

    url = """https://raw.githubusercontent.com/mozilla-services/third-party-library-alert/master/libraries.json"""

    @property
    def name(self) -> str:
        return "thirdpartyalert"

    def run(self):
        logger.debug(f"Fetching {self.url}")
        lines = []
        with urllib.request.urlopen(self.url) as response:
            for line in response.readlines():
                # TODO: un-comment commented JSON lines that are valuable
                line = line.decode("utf-8")
                if not line.strip().startswith("#"):
                    lines.append(line)

        response = "".join(lines)
        logger.debug("File content: `%s`" % repr(response))
        try:
            result = loads(response)
        except decoder.JSONDecodeError as e:
            logger.error(f"JSON parser error: {str(e)}")
            return
        for r in result:
            for d in self.as_dependency_descriptor(r):
                if d is not None:
                    yield d

    def as_dependency_descriptor(self, data: dict):
        loc = (self.hg.path / data["location"]).resolve()
        if loc.is_dir():
            dd = DependencyDescriptor(self, {
                "name": data["title"],
                "version": None,
                "repo_top_directory": loc,
                "repo_files": list(self.hg.find(start=loc)),
                "target_store": "CppStore",
                "dependants": [],
                "dependencies": [],
                "sourcestamp": self.hg.source_stamp,
                "upstream_ref": None,
            })
            yield dd
        elif loc.is_file():
            dd = DependencyDescriptor(self, {
                "name": data["title"],
                "version": None,
                "repo_top_directory": loc.parent,
                "repo_files": [loc],
                "target_store": "CppStore",
                "dependants": [],
                "dependencies": [],
                "sourcestamp": self.hg.source_stamp,
                "upstream_ref": None,
            })
            yield dd
        else:
            # Does it glob?
            matches = list(self.hg.find(glob=loc.name + "*", start=loc.parent))
            if len(matches) == 0:
                logger.warning(f"Broken ThirdPartyAlert reference {loc}")
                dd = DependencyDescriptor(self, {
                    "name": data["title"],
                    "version": None,
                    "repo_top_directory": loc.parent,
                    "repo_files": [],
                    "target_store": "CppStore",
                    "dependants": [],
                    "dependencies": [],
                    "sourcestamp": self.hg.source_stamp,
                    "upstream_ref": None,
                })
                yield dd
            else:
                dd = DependencyDescriptor(self, {
                    "name": data["title"],
                    "version": None,
                    "repo_top_directory": loc,
                    "repo_files": matches,
                    "target_store": "CppStore",
                    "dependants": [],
                    "dependencies": [],
                    "sourcestamp": self.hg.source_stamp,
                    "upstream_ref": None,
                })
                yield dd


class ThirdPartyPathsDetector(DependencyDetector):

    @property
    def name(self) -> str:
        return "thirdpartypaths"

    def run(self):
        matches = list(self.hg.find("ThirdPartyPaths.txt"))
        if len(matches) > 1:
            logger.warning(f"Multiple locations for ThirdPartyPaths.txt, choosing first of {matches}")

        with matches[0].open() as f:
            for path in f:
                yield from self.as_dependency_descriptor(self.hg.path / path.rstrip("\n"))

    def as_dependency_descriptor(self, p: Path):
        if p.is_dir():
            dd = DependencyDescriptor(self, {
                "name": None,
                "version": None,
                "repo_top_directory": p,
                "repo_files": list(self.hg.find(start=p)),
                "target_store": None,
                "dependants": [],
                "dependencies": [],
                "sourcestamp": self.hg.source_stamp,
                "upstream_ref": None,
            })
            yield dd
        elif p.is_file():
            dd = DependencyDescriptor(self, {
                "name": None,
                "version": None,
                "repo_top_directory": p.parent,
                "repo_files": [p],
                "target_store": None,
                "dependants": [],
                "dependencies": [],
                "sourcestamp": self.hg.source_stamp,
                "upstream_ref": None,
            })
            yield dd
        else:
            logger.error(f"Ignoring broken reference {p}")

# {'package': {'name': 'chrono',
#   'version': '0.4.6',
#   'authors': ['Kang Seonghoon <public+rust@mearie.org>',
#    'Brandon W Maister <quodlibetor@gmail.com>'],
#   'description': 'Date and time library for Rust',
#   'homepage': 'https://github.com/chronotope/chrono',
#   'documentation': 'https://docs.rs/chrono/',
#   'readme': 'README.md',
#   'keywords': ['date', 'time', 'calendar'],
#   'categories': ['date-and-time'],
#   'license': 'MIT/Apache-2.0',
#   'repository': 'https://github.com/chronotope/chrono',
#   'metadata': {'docs': {'rs': {'all-features': True}},
#    'playground': {'all-features': True}}},
#  'lib': {'name': 'chrono'},
#  'dependencies': {'num-integer': {'version': '0.1.36',
#    'default-features': False},
#   'num-traits': {'version': '0.2', 'default-features': False},
#   'rustc-serialize': {'version': '0.3.20', 'optional': True},
#   'serde': {'version': '1', 'optional': True},
#   'time': {'version': '0.1.39', 'optional': True}},
#  'dev-dependencies': {'bincode': {'version': '0.8.0'},
#   'num-iter': {'version': '0.1.35', 'default-features': False},
#   'serde_derive': {'version': '1'},
#   'serde_json': {'version': '1'}},
#  'features': {'clock': ['time'], 'default': ['clock']},
#  'badges': {'appveyor': {'repository': 'chronotope/chrono'},
#   'travis-ci': {'repository': 'chronotope/chrono'}}}


# {
#     "title" : "fdlibm",
#     "location" : "modules/fdlibm/",
#     "filing_info" : "1343924 Javascript Engine CC::bbouvier ni::arai",
#     "most_recent_bug" : 1461344,
#
#     "latest_version_fetch_type" : "html_re",
#     "latest_version_fetch_location" : "https://github.com/freebsd/freebsd/commits/master/lib/msun/src",
#     "latest_version_date_format_string" : "%Y-%m-%dT%H:%M:%SZ",
#     "latest_version_re" : "<relative-time datetime=\"([^\"]+)\"",
#
#     "current_version_fetch_type" : "html_re",
#     "current_version_fetch_location" : "https://hg.mozilla.org/mozilla-central/
#     raw-file/tip/modules/fdlibm/README.mozilla",
#     "current_version_re" : "Current version: \\[commit [0-9a-fA-F]{40} \\(([^\\)]+)\\)",
#     "current_version_date_format_string" : "%Y-%m-%dT%H:%M:%SZ",
#
#     "compare_type" : "date",
#     "compare_date_lag" : 1
# }


# """
#  {'file': '/home/cr/src/mozilla-unified/mobile/android/tests/browser/chrome/tp5/
#  twitter.com/ajax.googleapis.com/ajax/libs/jquery/1.3.0/jquery.min.js',
#   'results': [{'component': 'jquery',
#                'detection': 'filecontent',
#                'version': '1.3',
#                'vulnerabilities': [{'below': '1.6.3',
#                                     'identifiers': {'CVE': ['CVE-2011-4969'],
#                                                     'summary': 'XSS with '
#                                                                'location.hash'},
#                                     'info': ['https://nvd.nist.gov/vuln/detail/CVE-2011-4969',
#                                              'http://research.insecurelabs.org/jquery/test/',
#                                              'https://bugs.jquery.com/ticket/9521'],
#                                     'severity': 'medium'},
#                                    {'below': '1.9.0b1',
#                                     'identifiers': {'CVE': ['CVE-2012-6708'],
#                                                     'bug': '11290',
#                                                     'summary': 'Selector '
#                                                                'interpreted as '
#                                                                'HTML'},
#                                     'info': ['http://bugs.jquery.com/ticket/11290',
#                                              'https://nvd.nist.gov/vuln/detail/CVE-2012-6708',
#                                              'http://research.insecurelabs.org/jquery/test/'],
#                                     'severity': 'medium'}]}]},
# """


def validate(deps: Iterator[DependencyDescriptor]):
    for d in deps:
        logger.debug(f"Validating {d.name}-{d.version}")

        if not d.repo_top_directory.is_dir():
            logger.warning(f"{d.name}-{d.version}: invalid repo top directory {d.repo_top_directory}")
        for f in d.repo_files:
            if not f.is_file():
                logger.warning(f"{d.name}-{d.version}: invalid file reference to {d.repo_top_directory}")
