# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest
from subprocess import run, PIPE

from mozdep.main import guess_repo_path
import mozdep.detectors.python as pydet

logger = getLogger(__name__)


@pytest.mark.slow
def test_venv_creation(tmp_path):
    venv_path = pydet.make_venv(tmp_path)

    python_exe = venv_path / "bin" / "python"
    pip_exe = venv_path / "bin" / "pip"

    assert venv_path.is_dir() and tmp_path in venv_path.parents, "Venv is subdirectory of temp dir"
    assert (venv_path / "bin"). is_dir()

    assert (python_exe).is_file(), "Venv contains python binary"
    assert (pip_exe).is_file(), "Venv contains pip binary"

    p = run([python_exe, "--version"], check=False, stdout=PIPE, stderr=PIPE)
    assert p.returncode == 0, "Python runs without error"
    assert p.stderr.startswith(b"Python 2.7"), "Python version is 2.7"

    p = run([pip_exe, "--version"], check=False, stdout=PIPE, stderr=PIPE)
    assert p.returncode == 0, "pip runs without error"
    assert p.stdout.startswith(b"pip"), "pip version is readable"


@pytest.fixture(name="venv")
def venv_fixture(tmp_path):
    return pydet.make_venv(tmp_path)


@pytest.mark.slow
def test_pip_freeze(venv):
    repo = guess_repo_path()
    good_pkg = repo / "third_party" / "python" / "slugid"
    weird_pkg = repo / "third_party" / "python" / "gyp"
    pydet.run_pip(venv, "install", str(good_pkg))
    pydet.run_pip(venv, "install", str(weird_pkg))
    freezed_zipped = list(pydet.check_pip_freeze(venv))
    freezed_unzipped = list(zip(*freezed_zipped))
    assert "slugid" in freezed_unzipped[0]
    assert "gyp" in freezed_unzipped[0]


@pytest.mark.slow
def test_pip_show(venv):
    repo = guess_repo_path()
    good_pkg = repo / "third_party" / "python" / "slugid"
    pydet.run_pip(venv, "install", str(good_pkg))
    show_out = pydet.check_pip_show(venv)
    assert "slugid" in show_out
    assert show_out["slugid"]["Author"] == "Pete Moore"
    assert show_out["slugid"]["License"] == "MPL 2.0"


@pytest.mark.slow
def test_pip_check(venv):
    pydet.run_pip(venv, "install", "pip-check")
    before = set(pydet.pip_check_result(venv))
    packages = set()
    for (pkg, inst, avail, repo) in before:
        assert type(pkg) is str and pkg not in packages
        packages.add(pkg)
        assert type(inst) is str and inst == avail
        assert repo.startswith("http")

    assert {"pip", "pip-check"} < packages

    repo = guess_repo_path()

    # slugid should install and update like any other PyPI package
    good_pkg = repo / "third_party" / "python" / "slugid"
    pydet.run_pip(venv, "install", str(good_pkg))
    after = set(pydet.pip_check_result(venv))
    new = after - before
    assert after > before
    assert len(new) == 1
    pkg, inst, avail, rep = new.pop()
    assert pkg == "slugid"
    assert rep == "https://pypi.python.org/pypi/slugid"

    # Gyp doesn't show in pip-check due to lack of PyPI repo
    weird_pkg = repo / "third_party" / "python" / "gyp"
    pydet.run_pip(venv, "install", str(weird_pkg))
    with_weird = set(pydet.pip_check_result(venv))
    assert with_weird == after
