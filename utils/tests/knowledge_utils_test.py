# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
from pathlib import Path

import mozdep.knowledge_utils as ku
import mozdep.knowledgegraph as mk

logger = getLogger(__name__)


def test_dependency_learning():
    g = mk.KnowledgeGraph()
    tree_path = Path("/tmp/tree")

    dep_a_path = tree_path / "test_dep_a"
    dva = ku.learn_dependency(g,
                              name="dep_a",
                              version="0.0.1",
                              detector_name="test_detector",
                              language="js",
                              version_type="_generic",
                              upstream_version=None,
                              top_path=dep_a_path,
                              tree_path=tree_path,
                              repository_url=None,
                              files=[dep_a_path / "a.js", dep_a_path / "b.js"],
                              vulnerabilities=None)

    dep_aa_path = tree_path / "test_dep_aa"
    dvaa = ku.learn_dependency(g,
                               name="dep_a",
                               version="0.0.2",
                               detector_name="test_detector",
                               language="js",
                               version_type="_generic",
                               upstream_version="0.0.5",
                               top_path=dep_aa_path,
                               tree_path=tree_path,
                               repository_url="https://github.com/mozilla/dep_a",
                               files=[dep_aa_path / "a.js", dep_aa_path / "b.js"],
                               vulnerabilities=None)

    dep_b_path = tree_path / "test_dep_b"
    dvb = ku.learn_dependency(g,
                              name="dep_b",
                              version="0.0.1",
                              detector_name="test_detector",
                              language="js",
                              version_type="_generic",
                              upstream_version="0.0.2",
                              top_path=dep_b_path,
                              tree_path=tree_path,
                              repository_url="https://github.com/mozilla/dep_b",
                              files=[dep_b_path / "a.js", dep_b_path / "b.js"],
                              vulnerabilities=None)

    dep_bb_path = tree_path / "test_dep_bb"
    dvbb = ku.learn_dependency(g,
                               name="dep_b",
                               version="0.0.2",
                               detector_name="test_detector",
                               language="js",
                               version_type="_generic",
                               upstream_version="0.0.2",
                               top_path=dep_bb_path,
                               tree_path=tree_path,
                               repository_url="https://github.com/mozilla/dep_b",
                               files=[dep_bb_path / "a.js", dep_bb_path / "b.js"],
                               vulnerabilities=None)

    dep_c_path = tree_path / "test_dep_c"
    dvc = ku.learn_dependency(g,
                              name="dep_c",
                              version="0.0.1",
                              detector_name="test_detector",
                              language="cpp",
                              version_type="_generic",
                              upstream_version="0.0.1",
                              top_path=dep_c_path,
                              tree_path=tree_path,
                              repository_url="https://github.com/mozilla/dep_c",
                              files=[dep_c_path / "a.js", dep_c_path / "b.js"],
                              vulnerabilities=None)

    # Test merging by adding same dependency from different detector,
    # but with fewer info and files.
    dvcc = ku.learn_dependency(g,
                               name="dep_c",
                               version="0.0.1",
                               detector_name="test_detector2",
                               language="cpp",
                               version_type="_generic",
                               upstream_version=None,
                               top_path=dep_c_path,
                               tree_path=tree_path,
                               repository_url=None,
                               files=[dep_c_path / "a.js"],
                               vulnerabilities=None)

    assert dvc == dvcc, "adding same dependency doesn't create new node"
