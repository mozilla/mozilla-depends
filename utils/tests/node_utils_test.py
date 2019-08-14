# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest

from mozdep.repo_utils import guess_repo_path, HgRepo
import mozdep.node_utils as nu

logger = getLogger(__name__)


if nu.npm_bin is None or nu.yarn_bin is None:
    pytest.skip("Node tests require npm and yarn binaries in $PATH", allow_module_level=True)


def test_against_eslint_plugin_mozilla():
    repo_dir = guess_repo_path()
    if repo_dir is None:
        pytest.skip("eslint-plugin-mozilla test requires `guessable` mozilla-central repo path")

    eslint_dir = repo_dir / "tools" / "lint" / "eslint" / "eslint-plugin-mozilla"
    assert eslint_dir.exists()
    assert (eslint_dir / "package.json").exists()

    eslint_pkg = nu.NodePackage(eslint_dir)
    assert eslint_pkg.dir == eslint_dir
    assert eslint_pkg.is_npm_locked()
    assert eslint_pkg.is_locked()
    assert not eslint_pkg.is_yarn_locked()
    assert eslint_pkg.name == "eslint-plugin-mozilla"
    assert type(eslint_pkg.version) is str

    # Test npm list parser
    assert "name" in eslint_pkg.npm_list and eslint_pkg.npm_list["name"] == eslint_pkg.name
    assert "version" in eslint_pkg.npm_list and eslint_pkg.npm_list["version"] == eslint_pkg.version
    assert "dependencies" in eslint_pkg.npm_list and len(eslint_pkg.npm_list["dependencies"]) >= 3
    assert "htmlparser2" in eslint_pkg.npm_list["dependencies"]
    assert "ini-parser" in eslint_pkg.npm_list["dependencies"]
    assert "sax" in eslint_pkg.npm_list["dependencies"]

    # Test npm view parser
    assert eslint_pkg.npm_view is not None
    assert "name" in eslint_pkg.npm_view and eslint_pkg.npm_view["name"] == eslint_pkg.name
    # There's a strange version mismatch with npm view reporting 2.0.1 while package.json says 2.0.0
    assert "version" in eslint_pkg.npm_view and eslint_pkg.npm_view["version"][:4] == eslint_pkg.version[:4]
    assert "dependencies" in eslint_pkg.npm_view and len(eslint_pkg.npm_view["dependencies"]) == 3
    assert "htmlparser2" in eslint_pkg.npm_view["dependencies"]
    assert "ini-parser" in eslint_pkg.npm_view["dependencies"]
    assert "sax" in eslint_pkg.npm_view["dependencies"]
    assert "devDependencies" in eslint_pkg.npm_view and len(eslint_pkg.npm_view["devDependencies"]) == 2
    assert "eslint" in eslint_pkg.npm_view["devDependencies"]
    assert "mocha" in eslint_pkg.npm_view["devDependencies"]

    # assert len(list(eslint_pkg.dependencies())) == 490
    dep = eslint_pkg.dependencies()
    assert len(dep) > 150


def test_against_remote_qs():
    pass


def test_against_primary_packages():
    repo_dir = guess_repo_path()
    if repo_dir is None:
        pytest.skip("Primary Package test requires `guessable` mozilla-central repo path")
    hg = HgRepo(repo_dir)
    primary_packages = list(map(nu.NodePackage, hg.find("package.json")))
    assert len(primary_packages) > 30
