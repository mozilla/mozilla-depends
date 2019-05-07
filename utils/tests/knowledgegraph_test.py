# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger

import mozdep.knowledgegraph as mk

logger = getLogger(__name__)


def test_knowledgegraph():
    g = mk.KnowledgeGraph()

    e_one = g.add("name", "one")
    g.add("value", "1", mid=e_one.mid)
    g.add("parity", "odd", mid=e_one.mid)

    e_two = g.add("name", "two")
    g.add("value", "2", mid=e_two.mid)
    g.add("parity", "even", mid=e_two.mid)

    e_three = g.add("name", "three")
    g.add("value", "3", mid=e_three.mid)
    g.add("parity", "odd", mid=e_three.mid)
    g.add("minusone", e_two.mid, mid=e_three.mid)

    g.add("plusone", e_three.mid, mid=e_two.mid)

    assert g.V("odd").In("parity").Out("minusone").Has("plusone", e_three.mid).All() == {e_two.mid}
