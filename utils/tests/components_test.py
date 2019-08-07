# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest
from typing import Iterable

from mozdep.__main__ import guess_repo_path
import mozdep.component as mc
from mozdep.knowledgegraph import KnowledgeGraph, Ns

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


def test_mach():
    repo_path = guess_repo_path()
    assert repo_path is not None, "There's a local Firefox repo"
    test_set = {
        "mach": "Firefox Build System :: Mach Core",
        "layout/base/nsFrameManager.h": "Core :: Layout"
    }
    result = mc.call_mach_and_parse(repo_path, test_set.keys())
    assert result == test_set


@pytest.fixture(name="dummy_deps")
def dependencies_fixture() -> KnowledgeGraph:
    repo_path = guess_repo_path()
    assert repo_path is not None, "There's a local Firefox repo"

    g = KnowledgeGraph()

    dep_one = g.add(g.new_subject(), Ns().fx.mc.lib.dep.name, "TestDependency1")
    dep_two = g.add(g.new_subject(), Ns().fx.mc.lib.dep.name, "TestDependency2")

    mach_file = g.add(g.new_subject(), Ns().fx.mc.file.path, "mach")
    mach_file.add_relation(Ns().fx.mc.file.part_of, dep_one)
    mach_file.add_relation(Ns().fx.mc.file.part_of, dep_two)

    layout_file = g.add(g.new_subject(), Ns().fx.mc.file.path, "layout/base/nsFrameManager.h")
    layout_file.add_relation(Ns().fx.mc.file.part_of, dep_two)

    return g


def test_with_dependecies(dummy_deps: KnowledgeGraph):
    repo_path = guess_repo_path()
    assert repo_path is not None, "There's a local Firefox repo"

    mc.detect_components(repo_path, dummy_deps)

    r = set(
        dummy_deps.V()
                  .In(Ns().bz.product.component.name)
                  .Out(Ns().bz.product.component.name)
                  .All()
    )
    assert r == {"Firefox Build System :: Mach Core", "Core :: Layout"}

    r = set(
        dummy_deps.V("Core :: Layout")
                  .In(Ns().bz.product.component.name)
                  .Out(Ns().fx.mc.file.part_of)
                  .Out(Ns().fx.mc.lib.dep.name)
                  .All()
    )
    assert r == {"TestDependency2"}

    r = set(
        dummy_deps.V("Firefox Build System :: Mach Core")
                  .In(Ns().bz.product.component.name)
                  .Out(Ns().fx.mc.file.part_of)
                  .Out(Ns().fx.mc.lib.dep.name)
                  .All()
    )
    assert r == {"TestDependency1", "TestDependency2"}
