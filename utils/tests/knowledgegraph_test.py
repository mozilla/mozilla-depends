# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest

import mozdep.knowledgegraph as mk

logger = getLogger(__name__)


def test_knowledgegraph():
    """Test with string primitives"""
    g = mk.KnowledgeGraph(verify_namespace=False)

    v_one = g.add("name", "one")
    v_one.add("value", "1")
    v_one.add("parity", "odd")

    v_two = g.add("name", "two")
    g.add("value", "2", mid_or_vertex=v_two.mid)
    g.add("parity", "even", mid_or_vertex=v_two)

    v_three = g.add("name", "three")
    v_three.add("value", "3")
    v_three.add("parity", "odd")
    v_three.add("minusone", v_two)

    v_two.add("plusone", v_three)

    assert set(g.V().Has("parity", "odd").All()) == {v_one.mid, v_three.mid}
    assert set(g.V().Has("value").All()) == {v_one.mid, v_two.mid, v_three.mid}

    assert g.V("odd").In("parity").Out("minusone").Has("plusone", v_three).All() == [v_two.mid]

    h = mk.KnowledgeGraph(verify_namespace=False)
    h.from_json(g.as_json())

    assert h.V("odd").In("parity").Out("minusone").Has("plusone", v_three).All() == [v_two.mid]


def test_knowledgegraph_namespace():
    """Test with Ns primitives"""
    g = mk.KnowledgeGraph(verify_namespace=True)

    v_bar = g.add("ns:fx.mc.file.path", "foo/bar")
    v_baz = g.add(mk.Ns().fx.mc.file.path, "foo/baz")

    assert set(g.V("foo/bar").All()) == {"foo/bar"}
    assert set(g.V("foo/bar").In(mk.Ns().fx.mc.file.path).All()) == {v_bar.mid}
    assert set(g.V().Out(mk.Ns().fx.mc.file.path).All()) == {"foo/bar", "foo/baz"}
    assert set(g.V().Has(mk.Ns().fx.mc.file.path, "foo/baz").All()) == {v_baz.mid}

    with pytest.raises(mk.NamespaceError):
        _ = g.add(mk.Ns().fx.mc.file.unknown, "foo/bam")
