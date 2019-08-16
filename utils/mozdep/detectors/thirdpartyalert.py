# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import urllib.request
from json import loads, decoder

from .basedetector import DependencyDetector
import mozdep.knowledge_utils as ku

logger = logging.getLogger(__name__)


class ThirdPartyAlertDetector(DependencyDetector):
    url = """https://raw.githubusercontent.com/mozilla-services/third-party-library-alert/master/libraries.json"""

    @staticmethod
    def name() -> str:
        return "thirdpartyalert"

    @staticmethod
    def priority() -> int:
        return 30

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
            self.process(r)

    def process(self, data: dict):
        loc = (self.hg.path / data["location"]).resolve()

        library_name = data["title"]
        library_version = "unknown"

        logger.info(f"ThirdPartyLibraryAlert adding `{loc.relative_to(self.hg.path)}`")

        # # Get existing library node or create one
        # try:
        #     lv = self.g.V(library_name).In(Ns().fx.mc.lib.name).Has(Ns().language.name, "cpp").All()[0]
        # except IndexError:
        #     lv = self.g.new_subject()
        #     lv.add(Ns().fx.mc.lib.name, library_name)
        #     lv.add(Ns().language.name, "cpp")
        #
        # if loc.is_file():
        #     rel_top_path = str(loc.relative_to(self.hg.path))
        # else:
        #     rel_top_path = str(loc.parent.relative_to(self.hg.path))
        #
        # dv = self.g.new_subject()
        # dv.add(Ns().fx.mc.lib.dep.name, library_name)
        # dv.add(Ns().fx.mc.lib, lv)
        # dv.add(Ns().language.name, "cpp")
        # dv.add(Ns().fx.mc.detector.name, self.name())
        # dv.add(Ns().version.spec, library_version)
        # dv.add(Ns().version.type, "unknown")
        # dv.add(Ns().fx.mc.dir.path, rel_top_path)
        #
        # # TODO: extract version info
        # # TODO: extract upstream repo info

        files = []
        if loc.is_dir():
            files += list(self.hg.find(start=loc))

        elif loc.is_file():
            files.append(loc)

        else:
            # Does it glob?
            matches = list(self.hg.find(glob=loc.name + "*", start=loc.parent))
            if len(matches) == 0:
                logger.warning(f"Broken ThirdPartyLibraryAlert reference {loc}")
            else:
                files += matches

        _ = ku.learn_dependency(self.g,
                                name=library_name,
                                version=library_version,
                                detector_name=self.name(),
                                language="cpp",
                                version_type="_generic",
                                upstream_version=None,  # FIXME: extract upstream version
                                top_path=loc.parent if loc.is_file() else loc,
                                tree_path=self.hg.path,
                                repository_url=None,  # FIXME: extract upstream repo
                                files=files,
                                vulnerabilities=None)

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
