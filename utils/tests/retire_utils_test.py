# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from json import loads
from logging import getLogger
import pytest

import mozdep.node_utils as nu
from mozdep.detectors.retirejs import RetireScanner

logger = getLogger(__name__)


if nu.npm_bin is None or nu.yarn_bin is None:
    pytest.skip("Retire tests require npm and yarn binaries in $PATH", allow_module_level=True)


def test_retire_scanning():
    env = nu.NodeEnv("retire_scanning")
    env.install("retire@1")
    env.install("yarn")
    env_list = env.list()
    assert "dependencies" in env_list, "NodeEnv list contains dependencies"
    assert "retire" in env_list["dependencies"], "NodeEnv lists retire.js as dependency"
    retire_module_version = env_list["dependencies"]["retire"]["version"]
    retire_bin_version = env.run("retire", ["--version"]).stdout.decode("utf-8").split("\n")
    assert retire_module_version in retire_bin_version, "Retire.js binary reports expected module version"
    retire_args = [
        "--outputformat", "json",
        "--path", str(env.path),
        # "--path", "/Users/cr/src/mozilla-unified",
        "--outputpath", str(env.path / "scan.out"),
        "--verbose"
    ]
    retire_result = env.run("retire", retire_args)
    assert retire_result.returncode in [0, 13]
    with (env.path / "scan.out").open("rb") as f:
        retire_out = f.read().decode("utf-8")
    assert len(retire_out) > 0
    retire_json = loads(retire_out)
    if retire_module_version.startswith("2.0."):
        assert "data" in retire_json and len(retire_json["data"]) > 0, "Retire.js delivers scan results"
        for d in retire_json["data"]:
            assert "file" in d
            assert "results" in d
    elif retire_module_version.startswith("1.6."):
        assert type(retire_json) is list and len(retire_json) > 10
        for d in retire_json:
            if type(d) is dict:
                assert ("file" in d and "results" in d) or ("component" in d and "version" in d)
            elif type(d) is list:
                for l in d:
                    assert "component" in l and "version" in l
    else:
        assert False, "Test only supports retire.js versions 1.6 and 2.0"


@pytest.mark.slow
def test_retire_scanner():
    rs = RetireScanner()
    results = rs.run(rs.env.path)
    assert len(results) > 50
    semver_found = False
    glob_found = False
    for r in results:
        if type(r) is dict:
            # file result
            assert "file" in r and "results" in r and len(r["results"]) == 0
        elif type(r) is list:
            assert len(r) == 1
            assert "component" in r[0] and "version" in r[0]
            if r[0]["component"] == "glob":
                glob_found = True
            elif r[0]["component"] == "semver":
                semver_found = True
    assert glob_found and semver_found


@pytest.mark.slow
def test_retire_scanner_on_repo():
    rs = RetireScanner()
    from pathlib import Path
    results = rs.run(Path("/Users/cr/Documents/src/mozilla-unified"))
    assert len(results) > 50
    rr = []
    for x in range(len(results)):
        k = int(x/10000)
        try:
            rr[k].append(results[x])
        except IndexError:
            rr.append([results[x]])
        m = results[x]
        if "results" in m and len(m["results"]) > 1 and "vulnerabilities" in m["results"][0] \
                and len(m["results"][0]["vulnerabilities"]) > 0:
            pass
