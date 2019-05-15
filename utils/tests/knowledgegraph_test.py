# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger

import mozdep.knowledgegraph as mk

logger = getLogger(__name__)


def test_knowledgegraph():
    g = mk.KnowledgeGraph()

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

    h = mk.KnowledgeGraph()
    h.from_json(g.as_json())

    assert h.V("odd").In("parity").Out("minusone").Has("plusone", v_three).All() == [v_two.mid]
