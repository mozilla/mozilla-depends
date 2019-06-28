# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest

from mozdep.knowledgegraph import Ns, NamespaceError

logger = getLogger(__name__)


def test_namespace():
    empty_ns = Ns()
    assert empty_ns.is_known()

    file_path = Ns().fx.mc.file.path
    assert file_path.is_known()
    assert str(file_path) == "ns:fx.mc.file.path"
    assert repr(file_path) == "Ns('ns:fx.mc.file.path')"

    unknown = Ns(check=False).fx.mc.file.foo
    assert str(unknown) == "ns:fx.mc.file.foo"
    assert not unknown.is_known()


def test_namespace_parser():
    n = Ns("ns:fx.mc.file.path")
    assert n.p == "ns"
    assert n.r == ["fx", "mc", "file", "path"]
    assert str(n) == "ns:fx.mc.file.path"


def test_namespace_hashing():
    x = Ns().fx.mc
    y = Ns().fx.mc
    assert hash(x) == hash(y)
    assert hash(x) == hash("ns:fx.mc")

    d = dict()
    d[x] = "test"
    assert "ns:fx.mc"
    assert d["ns:fx.mc"] == "test"


def test_namespace_relations():
    x = Ns().fx.mc
    y = Ns().fx.mc

    assert id(x) != id(y)
    assert x == y

    assert x == "ns:fx.mc"
    assert Ns("ns:fx.mc.file") == "ns:fx.mc.file"

    assert x.lib != x
    assert x.file < x
    assert x > x.lib

    assert not Ns().fx.mc.lib < Ns().fx.mc.file
    assert not Ns().fx.mc.lib > Ns().fx.mc.file


def test_namespace_errors():

    with pytest.raises(NamespaceError):
        Ns("foo")
    with pytest.raises(NamespaceError):
        Ns("ns:foo")
    with pytest.raises(NamespaceError):
        Ns().fx.foo

    # No error
    _ = Ns(check=False).unknown
    _ = Ns("foo:bar", check=False).unknown


def test_namespace_indexing():
    assert type(Ns.len()) is int
    assert Ns.len() > 10
    complete_namespace = list(Ns.iter())
    assert len(complete_namespace) == Ns.len()
    for index in range(Ns.len()):
        ns = Ns.by_index(index)
        assert Ns.index_of(ns) == index
        assert complete_namespace[index] == ns
        assert type(complete_namespace[index]) is Ns
