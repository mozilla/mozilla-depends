# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from json import loads, decoder
from pathlib import Path
from tempfile import NamedTemporaryFile

from .basedetector import DependencyDetector
from mozdep.knowledgegraph import Ns
import mozdep.knowledge_utils as ku
from mozdep.node_utils import NodeEnv, NodeError

logger = logging.getLogger(__name__)


class RetireScannerError(Exception):
    pass


class RetireScanner(object):

    def __init__(self):
        # FIXME: retirejs is broken
        # See https://github.com/RetireJS/retire.js/issues/302
        # - retirejs 2.0 (current) complains about missing yarn, and fails to produce an output report
        # - retirejs 1.6 complains about missing yarn as well, but produces report on the rest
        self.env = NodeEnv("retire_scanner_env")
        self.env.install("retire@1")
        # self.env.install("yarn")

    def run(self, path: Path):
        with NamedTemporaryFile(prefix="retire_scanner_tmpfile_") as tmp_file:
            retire_args = [
                "--outputformat", "json",
                "--outputpath", tmp_file.name,
                "--path", str(path),
                "--verbose"
            ]
            if (path / ".hg").is_dir():
                retire_args += ["--ignore", str(path / ".hg")]

            try:
                p = self.env.run("retire", retire_args)
            except NodeError as e:
                raise RetireScannerError from e
            if p.returncode not in [0, 13]:
                logger.error("Retire.js call failed, probably due to network failure")
                logger.error("Failing stderr is `%s`", p.stderr.decode("utf-8"))
                raise RetireScannerError("Retire.js failed to run")

            with open(tmp_file.name, "rb") as f:
                cmd_output = f.read().decode("utf-8")
            try:
                result = loads(cmd_output)
            except decoder.JSONDecodeError:
                logger.error("Retire.js call failed, probably due to network failure: %s", repr(cmd_output))
                raise RetireScannerError("Retire.js failed to run, likely due to network error")

        return result


class RetireDependencyDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "retire"

    @staticmethod
    def priority() -> int:
        return 20

    def setup(self) -> bool:
        try:
            self.state = {
                "retire_scanner": RetireScanner()
            }
        except RetireScannerError as e:
            logger.error("Detector failed to init retire.js scanner: %s", str(e))
            return False
        return True

    def run(self):
        logger.info("Running retirejs scanner (takes a while)")
        result = self.state["retire_scanner"].run(self.hg.path)
        for f in result:
            if "results" not in f or len(f["results"]) == 0:
                continue
            self.process(f)

    def process(self, data: dict):
        fp = Path(data["file"]).resolve()

        logger.info(f"RetireDependency adding `{fp.relative_to(self.hg.path)}`")

        logger.debug(f"Processing file {fp}")

        for r in data["results"]:
            library_name = r["component"]
            library_version = r["version"]

            dv = ku.learn_dependency(self.g,
                                     name=library_name,
                                     version=library_version,
                                     detector_name=self.name(),
                                     language="js",
                                     version_type="_generic",
                                     upstream_version=None,  # FIXME: extract upstream version
                                     top_path=fp.parent,
                                     tree_path=self.hg.path,
                                     repository_url=None,  # FIXME: extract upstream repo
                                     files=[fp],
                                     vulnerabilities=None)

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

            # Add vulnerability info
            if "vulnerabilities" not in r:
                continue
            for vuln in r["vulnerabilities"]:
                if "CVE" in vuln["identifiers"]:
                    if len(vuln["identifiers"]["CVE"]) != 1:
                        logger.warning(f"Unexpected CVE entry: {vuln['identifiers']['CVE']}")
                    ident = vuln["identifiers"]["CVE"][0]
                else:
                    logger.error(f"Unexpected vulnerability identifier in `{repr(vuln['identifiers'])}`")
                    ident = "retirejs-" + str(hash(fp))
                description = vuln["summary"] if "summary" in vuln else None
                severity = vuln["severity"] if "severity" in vuln else None
                ku.learn_vulnerability(self.g,
                                       vulnerability_identifier=ident,
                                       database="retire.js",
                                       info_links=vuln["info"],
                                       affects=[dv],
                                       title=None,
                                       description=description,
                                       weakness_identifier=None,
                                       severity=severity)
