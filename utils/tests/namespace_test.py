# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest

from mozdep.knowledgegraph import Ns, NamespaceError

logger = getLogger(__name__)


def test_nameapace():
    empty_ns = Ns()
    assert empty_ns.is_known()

    file_path = Ns().fx.mc.file.path
    assert file_path.is_known()
    assert str(file_path) == "ns:fx.mc.file.path"
    assert repr(file_path) == "Ns('ns:fx.mc.file.path')"

    unknown = Ns().fx.mc.file.foo
    assert str(unknown) == "ns:fx.mc.file.foo"
    assert not unknown.is_known()


def test_namespace_parser():
    n = Ns("ns:fx.mc.file.path")
    assert str(n) == "ns:fx.mc.file.path"

    with pytest.raises(NamespaceError):
        Ns("nn:foo")

    with pytest.raises(NamespaceError):
        Ns("ns:foo:bar")


def test_namespace_relations():

    x = Ns().foo.bar
    y = Ns().foo.bar

    assert id(x) != id(y)
    assert x == y
    assert hash(x) == hash(y)
    assert hash(x) == hash("ns:foo.bar")

    assert x == "ns:foo.bar"
    assert Ns("foo") == "foo"

    assert x.baz != x
    assert x.baz < x
    assert x > x.baz

    assert not Ns().foo < Ns().baz
    assert not Ns().foo > Ns().baz
