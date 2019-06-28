# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
import pytest
from random import random, choices, sample
from string import ascii_letters
from time import time as now

import mozdep.knowledgegraph as mk

logger = getLogger(__name__)


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


def test_knowledgegraph_subjects():
    g = mk.KnowledgeGraphX()

    subject_a = mk.Subject(g)
    subject_b = mk.Subject(g)
    subject_c = mk.Subject(g, mid=subject_b.mid)

    assert subject_a == subject_a
    assert subject_a != subject_b
    assert subject_a != subject_c
    assert subject_a.mid != subject_b.mid
    assert subject_a.mid != subject_c.mid

    assert subject_b != subject_a
    assert subject_b == subject_b
    assert subject_b == subject_c
    assert subject_b.mid == subject_c.mid

    assert subject_c != subject_a
    assert subject_c == subject_b
    assert subject_c == subject_c

    assert subject_a == subject_a.mid
    assert subject_a != subject_b.mid
    assert subject_a.mid != subject_c  # CAVE: this way around there's no equality


def test_knowledgegraph_literals():
    g = mk.KnowledgeGraphX()

    literal_a = mk.Literal(g, "literal a")
    literal_a_again = mk.Literal(g, "literal a")
    literal_b = mk.Literal(g, "literal b")

    assert literal_a == literal_a
    assert literal_a == literal_a_again
    assert literal_a != literal_b
    assert literal_a == "literal a"
    assert id(literal_a) != id(literal_a_again)
    assert "literal a" == literal_a
    assert hash(literal_a) == hash("literal a")

    assert literal_a_again == literal_a
    assert literal_a_again == literal_a_again
    assert literal_a_again != literal_b
    assert "literal a" == literal_a_again
    assert hash(literal_a_again) == hash("literal a")

    assert literal_b != literal_a
    assert literal_b != literal_a_again
    assert literal_b == literal_b
    assert literal_b == "literal b"
    assert "literal b" == literal_b
    assert hash(literal_b) == hash("literal b")


def test_knowledgegraph():
    g = mk.KnowledgeGraphX()

    name_one = g.literal("subject one")
    name_two = g.literal("subject two")
    name_three = g.literal("subject three")

    label_a = g.literal("label a")
    label_b = g.literal("label b")
    label_c = g.literal("label c")

    s_one = g.new_subject({mk.Ns().id.name: name_one})
    g.add_relation(s_one, mk.Ns().id.label, label_a)
    s_two = g.new_subject({mk.Ns().id.name: name_two})
    s_two.add_relation(mk.Ns().id.label, label_b)
    s_two.add_relation(mk.Ns().id.label, label_b)  # Should have no effect
    s_two.add_relation(mk.Ns().id.label, label_a)  # Should have an effect, now has two labels
    s_three = g.new_subject({
        mk.Ns().id.name: name_three,
        mk.Ns().id.label: label_c,
        mk.Ns().rel.same_as: s_two})
    g.add_relation(s_one, mk.Ns().rel.contains, s_two)
    g.add_relation(s_two, mk.Ns().rel.part_of, s_three)

    expected_literals = {name_one, name_two, name_three, label_a, label_b, label_c}
    expected_subjects = {s_one, s_two, s_three}
    expected_entities = expected_literals.union(expected_subjects)

    expected_relations_from_one = {
        (s_one, mk.Ns().id.name, name_one),
        (s_one, mk.Ns().id.label, label_a),
        (s_one, mk.Ns().rel.contains, s_two),
    }
    expected_relations_from_two = {
        (s_two, mk.Ns().id.name, name_two),
        (s_two, mk.Ns().id.label, label_a),
        (s_two, mk.Ns().id.label, label_b),
        (s_two, mk.Ns().rel.part_of, s_three),
    }
    expected_relations_from_three = {
        (s_three, mk.Ns().id.name, name_three),
        (s_three, mk.Ns().id.label, label_c),
        (s_three, mk.Ns().rel.same_as, s_two),
    }
    expected_relations_to_one = set()
    expected_relations_to_two = {
        (s_one, mk.Ns().rel.contains, s_two),
        (s_three, mk.Ns().rel.same_as, s_two),
    }
    expected_relations_to_three = {
        (s_two, mk.Ns().rel.part_of, s_three),
    }
    expected_relations_to_label_a = {
        (s_one, mk.Ns().id.label, label_a),
        (s_two, mk.Ns().id.label, label_a),
    }
    expected_relations = expected_relations_from_one.union(
        expected_relations_from_two).union(
        expected_relations_from_three)

    entities = list(g.entities())
    subjects = list(g.subjects())
    relations = list(g.relations())

    # msg = []
    # msg.append("*** expected")
    # for x in expected_relations_from_one:
    #     msg.append(str(x))
    # msg.append("*** actual")
    # for x in s_one.relations_from():
    #     msg.append(str(x))
    # logger.error("\n".join(msg))

    # logger.error("****** graph dump")
    # logger.error(list(g.g.nodes(data=True)))
    # logger.error(list(g.g.edges(data=True)))

    # Nothing should be iterated twice
    assert len(entities) == len(set(entities)), "No duplicate entities"
    assert len(subjects) == len(set(subjects)), "No duplicate subjects"
    assert len(relations) == len(set(relations)), "No duplicate relations"

    assert set(entities) == expected_entities
    assert set(subjects) == expected_subjects
    assert set(relations) == expected_relations

    assert set(s_one.relations_from()) == expected_relations_from_one, "Expected relations from subject one"
    assert len(list(s_one.relations_from())) == len(expected_relations_from_one), "No duplicates from subject one"
    assert set(s_one.relations_to()) == expected_relations_to_one, "Expected relations to subject one"
    assert len(list(s_one.relations_to())) == len(expected_relations_to_one), "No duplicates to subject one"

    assert set(s_two.relations_from()) == expected_relations_from_two, "Expected relations from subject two"
    assert len(list(s_two.relations_from())) == len(expected_relations_from_two), "No duplicates from subject two"
    assert set(s_two.relations_to()) == expected_relations_to_two, "Expected relations to subject two"
    assert len(list(s_two.relations_to())) == len(expected_relations_to_two), "No duplicates to subject two"

    assert set(s_three.relations_from()) == expected_relations_from_three, "Expected relations from subject three"
    assert len(list(s_three.relations_from())) == len(expected_relations_from_three), "No duplicates from subject three"
    assert set(s_three.relations_to()) == expected_relations_to_three, "Expected relations to subject three"
    assert len(list(s_three.relations_to())) == len(expected_relations_to_three), "No duplicates to subject three"

    assert set(label_a.relations_to()) == expected_relations_to_label_a, "Expected relations to label a"
    assert len(list(label_a.relations_to())) == len(expected_relations_to_label_a), "No duplicates to label a"


def test_knowledgegraph_random():
    ns = list(mk.Ns.iter())
    g = mk.KnowledgeGraphX()

    # Keep track of what we know
    subjects = set()
    literals = set()
    relations = set()

    timeout_time = now() + 500  # Fuzz for at most 5 seconds
    while len(relations) < 1500 and now() < timeout_time:

        # With 25% chance, pick a known subject
        if random() > 0.25 and len(subjects) > 0:
            s = sample(subjects, 1)[0]
        else:
            s = g.new_subject()

        # Pick a random relation
        r = choices(ns)[0]

        # With 25% chance each, pick known subject, known literal, new subject or new literal as entity
        if random() < 0.25 and len(subjects) > 1:
            # When picking a random known subject, ensure there's more than one to pick from
            # and it's not the subject we're creating a relation with.
            e = s
            while e == s:
                e = sample(subjects, 1)[0]
        elif random() < 0.25 and len(literals) > 0:
            e = sample(literals, 1)[0]
        elif random() < 0.25:
            e = g.new_subject()
        else:
            e = g.literal("".join(choices(ascii_letters, k=20)))

        subjects.add(s)
        if type(e) is mk.Subject:
            subjects.add(e)
        else:
            literals.add(e)

        relations.add((s, r, e))
        g.add_relation(s, r, e)

        # msg = []
        # msg.append("*** expected subjects")
        # for x in subjects:
        #     msg.append(str(x))
        # msg.append("*** actual subjects")
        # for x in g.subjects():
        #     msg.append(str(x))
        # logger.error("\n".join(msg))
        #
        # msg = []
        # msg.append("*** expected entities")
        # for x in subjects.union(literals):
        #     msg.append(str(x))
        # msg.append("*** actual entities")
        # for x in g.entities():
        #     msg.append(str(x))
        # logger.error("\n".join(msg))
        #
        # msg = []
        # msg.append("*** expected relations")
        # for x in relations:
        #     msg.append(str(x))
        # msg.append("*** actual relations")
        # for x in g.relations():
        #     msg.append(str(x))
        # logger.error("\n".join(msg))
        #
        # logger.error("****** graph dump")
        # logger.error(list(g.g.nodes(data=True)))
        # logger.error(list(g.g.edges(data=True)))

        assert set(g.subjects()) == subjects
        assert set(g.entities()) == subjects.union(literals)
        assert set(g.relations()) == relations

    assert len(relations) >= 500, "Fuzzing performed at least 500 iterations"


def test_gromlin():
    g = mk.KnowledgeGraphX()

    # If you pass strings instead of Literal objects, they'll be wrapped for you.

    s_one = g.new_subject({mk.Ns().id.label: "odd", mk.Ns().id.name: "One"})
    s_two = g.new_subject({mk.Ns().id.label: "even", mk.Ns().id.name: "Two"})
    s_three = g.new_subject({mk.Ns().id.label: "odd", mk.Ns().id.name: "Three"})
    s_four = g.new_subject({mk.Ns().id.label: "even", mk.Ns().id.name: "Four"})
    s_five = g.new_subject({mk.Ns().id.label: "odd", mk.Ns().id.name: "Five"})

    g.add_relation(s_two, mk.Ns().rel.contains, s_one)
    g.add_relation(s_three, mk.Ns().rel.contains, s_one)
    g.add_relation(s_three, mk.Ns().rel.contains, s_two)
    g.add_relation(s_four, mk.Ns().rel.contains, s_three)
    g.add_relation(s_four, mk.Ns().rel.contains, s_two)
    g.add_relation(s_four, mk.Ns().rel.contains, s_one)
    g.add_relation(s_five, mk.Ns().rel.contains, s_four)
    g.add_relation(s_five, mk.Ns().rel.contains, s_three)
    g.add_relation(s_five, mk.Ns().rel.contains, s_two)
    g.add_relation(s_five, mk.Ns().rel.contains, s_one)

    assert g.V().All() == list(g.entities())
    assert set(g.V().In(mk.Ns().id.name)) == {s_one, s_two, s_three, s_four, s_five}
    assert set(g.V().In(mk.Ns().id.label)) == {s_one, s_two, s_three, s_four, s_five}
    assert set(g.V("even").In().Out(mk.Ns().id.name)) == {"Two", "Four"}
    assert set(g.V("odd").In().Out(mk.Ns().id.name)) == {"One", "Three", "Five"}

    assert set(g.V("One").In().Out(mk.Ns().id.label)) == {"odd"}
    assert set(g.V("Two").In().Out(mk.Ns().id.label)) == {"even"}
    assert set(g.V("Three").In().Out(mk.Ns().id.label)) == {"odd"}
    assert set(g.V("Four").In().Out(mk.Ns().id.label)) == {"even"}
    assert set(g.V("Five").In().Out(mk.Ns().id.label)) == {"odd"}

    assert set(g.V("One").In(mk.Ns().id.name).Out(mk.Ns().rel.contains).Out(mk.Ns().id.name)) \
        == set()
    assert set(g.V("Two").In(mk.Ns().id.name).Out(mk.Ns().rel.contains).Out(mk.Ns().id.name)) \
        == {"One"}
    assert set(g.V("Three").In(mk.Ns().id.name).Out(mk.Ns().rel.contains).Out(mk.Ns().id.name)) \
        == {"One", "Two"}
    assert set(g.V("Four").In(mk.Ns().id.name).Out(mk.Ns().rel.contains).Out(mk.Ns().id.name)) \
        == {"One", "Two", "Three"}
    assert set(g.V("Five").In(mk.Ns().id.name).Out(mk.Ns().rel.contains).Out(mk.Ns().id.name)) \
        == {"One", "Two", "Three", "Four"}
