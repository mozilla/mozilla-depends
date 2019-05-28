# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import os
from json import loads, decoder
from pathlib import Path
from subprocess import run, check_output, check_call, DEVNULL, CalledProcessError
from tempfile import mktemp

from .basedetector import DependencyDetector
from ..knowledgegraph import Ns

logger = logging.getLogger(__name__)


class RetireDependencyDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "retire"

    @staticmethod
    def priority() -> int:
        return 20

    def setup(self) -> bool:
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
        tmp_out = mktemp(prefix="mozdep_retire_")
        cmd = [
            self.args["retire_bin"],
            "--outputformat", "json",
            "--outputpath", str(tmp_out),
            "--path", str(self.hg.path),
            "--ignore", str(self.hg.path / ".hg"),
            "--verbose"
        ]
        logger.debug("Running shell command `%s`" % " ".join(cmd))
        logger.info("Running retirejs scanner (takes a while)")
        r = run(cmd, check=False, capture_output=True)
        if r.returncode not in [0, 13]:
            logger.error("retirejs call failed, probably due to network failure")
            logger.error("Failing stderr is `%s`" % r.stderr.decode("utf-8"))
            raise Exception("Retire.js failed to run")
        with open(tmp_out, "rb") as f:
            cmd_output = f.read()
        os.unlink(tmp_out)
        logger.debug("Shell command output: `%s`" % cmd_output)
        try:
            result = loads(cmd_output.decode("utf-8"))
        except decoder.JSONDecodeError:
            logger.error("retirejs call failed, probably due to network failure")
            logger.error("Failing output is `%s`" % cmd_output)
            raise Exception("Retire.js failed to run, likely due to network error")

        for f in result:
            if len(f["results"]) == 0:
                continue
            self.process(f)

    def process(self, data: dict):

        fp = Path(data["file"]).resolve()
        rel_top_path = str(fp.parent.relative_to(self.hg.path))

        logger.info(f"RetireDependency adding `{fp.relative_to(self.hg.path)}`")

        logger.debug(f"Processing file {fp}")
        rel_path = str(fp.relative_to(self.hg.path))
        fv = self.g.add("ns:fx.mc.file.path", rel_path)

        for r in data["results"]:
            library_name = r["component"]
            library_version = r["version"]

            # Get existing library node or create one
            try:
                lv = self.g.V(library_name).In("ns:fx.mc.lib.name").Has("ns:language.name", "js").AllV()[0]
            except IndexError:
                lv = self.g.add("ns:fx.mc.lib.name", library_name)
                lv.add("ns:language.name", "js")

            dv = self.g.add("ns:fx.mc.lib.dep.name", library_name)
            dv.add("ns:fx.mc.lib", lv)
            dv.add("ns:language.name", "js")
            dv.add("ns:fx.mc.detector.name", self.name())
            dv.add("ns:version.spec", library_version)
            dv.add("ns:version.type", "generic")
            dv.add("ns:fx.mc.dir.path", rel_top_path)

            fv.add("ns:fx.mc.file.part_of", dv)

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
                    continue
                try:
                    vv = self.g.V(ident).In(Ns().vuln.id).AllV()[0]
                    logger.debug(f"Updating existing vulnerability node for {ident}")
                except IndexError:
                    logger.debug(f"Creating new vulnerability node for {ident}")
                    vv = self.g.add(Ns().vuln.id, ident)
                if "summary" in vuln["identifiers"]:
                    vv.add(Ns().vuln.summary, vuln["identifiers"]["summary"])
                vv.add(Ns().vuln.severity, vuln["severity"])
                vv.add(Ns().vuln.info_link, ";".join(vuln["info"]))
                vv.add(Ns().vuln.affects, dv)
                # TODO: extract version_match info
