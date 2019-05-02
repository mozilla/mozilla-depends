# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
from os.path import expanduser
from pathlib import Path
import pytest
from typing import Iterable

import mozdep.component as mc
from mozdep.dependency import DependencyDescriptor

logger = getLogger(__name__)


def test_chunking():
    list_of_things = ["a", "b", "c", "d", "e"]
    chunker = mc.chunked(iter(list_of_things), 2)

    c = next(chunker)
    assert isinstance(c, Iterable)
    assert list(c) == ["a", "b"]
    assert list(next(chunker)) == ["c", "d"]
    assert list(next(chunker)) == ["e"]

    with pytest.raises(StopIteration):
        next(chunker)

    with pytest.raises(StopIteration):
        next(mc.chunked([], 10))


def __guess_repo_path():
    home_dir = Path(expanduser('~'))
    guesses = [
        home_dir / "mozilla-unified",
        home_dir / "src" / "mozilla-unified",
        Path("../../mozilla-unified"),
        home_dir / "mozilla-central",
        home_dir / "src" / "mozilla-central",
        Path("../../mozilla-central"),
    ]
    for guess in guesses:
        if (guess / "mach").is_file():
            return guess.resolve()
    return None


def test_mach():
    repo_path = __guess_repo_path()
    assert repo_path is not None, "There's a local Firefox repo"
    test_set = {
        repo_path / "mach": "Firefox Build System :: Mach Core",
        repo_path / "layout/base/nsFrameManager.h": "Core :: Layout"
    }

    result = mc.call_mach_and_parse(map(lambda p: Path(p).resolve(), test_set.keys()))
    assert result == test_set


@pytest.fixture(name="dummy_deps")
def dependencies_fixture():

    class DummyDetector(object):
        @property
        def name(self):
            return "dummy_detector"

    repo_path = __guess_repo_path()
    assert repo_path is not None, "There's a local Firefox repo"
    d = DummyDetector()
    deps = [
        DependencyDescriptor(d, {
            "name": "TestDependency1",
            "version": None,
            "repo_top_directory": repo_path,
            "target_store": None,
            "dependants": [],
            "dependencies": [],
            "sourcestamp": None,
            "repo_files": [
                repo_path / "mach"
            ]
        }),
        DependencyDescriptor(d, {
            "name": "TestDependency2",
            "version": None,
            "repo_top_directory": repo_path,
            "target_store": None,
            "dependants": [],
            "dependencies": [],
            "sourcestamp": None,
            "repo_files": [
                repo_path / "mach",
                repo_path / "layout/base/nsFrameManager.h"
            ]
        }),
    ]
    return deps


def test_with_dependecies(dummy_deps):
    repo_path = __guess_repo_path()
    assert repo_path is not None, "There's a local Firefox repo"

    expected = [
        repo_path / "mach",
        repo_path / "layout/base/nsFrameManager.h"
    ]
    assert set(mc.iter_files_in_deps(dummy_deps)) == set(expected)

    result = list(mc.detect_components(dummy_deps))
    assert len(result) == 2
    a, b = result
    if not a.name == "Core :: Layout":
        a, b = b, a

    assert a.name == "Core :: Layout"
    assert b.name == "Firefox Build System :: Mach Core"
    logger.error(a.dependencies)
    logger.error(dummy_deps)
    assert a.dependencies == {[dummy_deps[1]]}
    assert a.files == set()  # FIXME: this shouldn't

    logger.error(b.dependencies)
    logger.error(dummy_deps)
    assert b.dependencies == set(dummy_deps)
    assert b.files == set()  # FIXME: this shouldn't
