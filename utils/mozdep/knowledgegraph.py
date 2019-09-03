# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from abc import ABC, abstractmethod
from collections import deque
from copy import deepcopy
import logging
import networkx as nx
from random import choices
from string import ascii_letters, digits
from typing import Iterator, List, Tuple

logger = logging.getLogger(__name__)


class NamespaceError(Exception):
    pass


class Ns(str):

    NS = {
        "ns": {
            "bz": {
                "product": {
                    "name": None,
                    "component": {
                        "name": None,
                    }
                },
            },
            "fx": {
                "mc": {
                    "dir": {
                        "path": None,
                    },
                    "file": {
                        "path": None,
                        "part_of": None,
                        "in_component": None,
                        "top_dependency": None
                    },
                    "file_set": None,
                    "lib": {
                        "name": None,
                        "description": None,
                        "dep": {
                            "name": None,
                            "detected_by": None
                        },
                    },
                    "detector": {
                        "name": None,
                    },
                },
            },
            "gh": {
                "repo": {
                    "url": None,
                    "version": None,
                }
            },
            "id": {
                "label": None,
                "name": None,
            },
            "language": {
                "name": None
            },
            "rel": {
                "contains": None,
                "part_of": None,
                "same_as": None,
            },
            "t": {
                "generic_type": None,
            },
            "version": {
                "spec": None,
                "type": None
            },
            "vuln": {
                "affects": None,
                "class": None,
                "database": None,
                "description": None,
                "detector_name": None,
                "id": None,
                "info_link": None,
                "severity": None,
                "summary": None,
                "title": None,
                "version_match": None,
                "weakness_id": None,
            },
        },
    }

    _index: list or None = None

    def __new__(cls, content=None, *, check=True):
        # logger.debug(f"Ns.__new__ content={content} check={check}")
        if content is None:
            return super().__new__(cls, "ns")
        else:
            return super().__new__(cls, content)

    def __init__(self, content=None, *, check=True):
        # logger.debug(f"Ns.__init__ content={content} check={check}")
        super().__init__()
        self._p = None
        self._r = None
        self._s = None
        self._check = check
        if check and not self.is_known():
            raise NamespaceError(f"Invalid namespace identifier `{self}`")

    @classmethod
    def iter(cls) -> Iterator["Ns"]:
        """Iterate the entire namespace"""
        queue = deque([(Ns(), cls.NS["ns"])])
        while len(queue) > 0:
            ns, sub_dict = queue.popleft()
            for key, sub_sub_dict in sub_dict.items():
                # The idea now is to get the attribute from the sub dict corresponding to `key`.
                # Normally, one would rely on getattr to do its thing, but whenever `key` also
                # specifies a method in Ns or its parent str (i.e. str.title), that method is
                # returned instead of the value in the dict. So you can't rely on getattr for
                # this job, as in: next_ns = getattr(ns, key)
                next_ns = ns.__getattr__(key)
                yield next_ns
                if sub_sub_dict is not None:
                    queue.append((getattr(ns, key), sub_sub_dict))

    @classmethod
    def len(cls) -> int:
        """Return length of namespace"""
        if cls._index is None:
            cls._index = list(cls.iter())
        return len(cls._index)

    @classmethod
    def index_of(cls, ns: "Ns") -> int:
        """
        Return the numerical index of a namespace object.

        The index may change between runs and must not be used
        for identification.
        """
        if cls._index is None:
            cls._index = list(cls.iter())
        return cls._index.index(ns)

    @classmethod
    def by_index(cls, n: int) -> "Ns":
        """Return namespace object associated with an index"""
        if cls._index is None:
            cls._index = list(cls.iter())
        return deepcopy(cls._index[n])

    @property
    def p(self):
        if self._p is None:
            self._p = self.split(":")[0]
        return self._p

    @property
    def r(self):
        if self._r is None:
            try:
                self._r = self.split(":")[1].split(".")
            except IndexError:
                self._r = []
        return self._r

    def is_known(self):
        try:
            ns_pointer = self.NS[self.p]
            for item in self.r:
                ns_pointer = ns_pointer[item]
        except KeyError:
            return False
        return True

    # def learn(self):
    #     # Add to NS dictionary
    #     raise NotImplemented

    def __repr__(self) -> str:
        return f"Ns('{self}')"

    def __getattr__(self, item) -> "Ns":
        if ":" in self:
            return Ns(self + "." + item, check=self._check)
        else:
            return Ns(self + ":" + item, check=self._check)

    def __gt__(self, other: str or "Ns"):
        return other.startswith(self)

    def __lt__(self, other: str or "Ns"):
        return self.startswith(other)

    def __deepcopy__(self, memo):
        return Ns(self, check=self._check)


class Entity(ABC):
    """
    Base clas for KnowledgeGraph entities which can be a subject, or a string literal.
    Guarantee for Entity objects:
      - Have a string representation
      - Are hashable
      - Contain a reference Entity.g to their base graph
    """

    def __init__(self, g: "KnowledgeGraph"):
        self.g = g

    @abstractmethod
    def __str__(self) -> str:
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{str(self)}')"

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other) -> bool:
        return str(self) == str(other)

    @abstractmethod
    def add_relation(self, predicate: Ns, entity: "Entity") -> None:
        pass

    @abstractmethod
    def relations_to(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        pass

    @abstractmethod
    def relations_from(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        pass


class Subject(Entity):
    """
    Representation of a knowledge graph's subject.
    It stores a reference to its parent graph as Subject.g.
    Its string representation is its MID.
    """

    @staticmethod
    def __random_mid(length: int = 10) -> str:
        """Generate random machine ID"""
        return "mid:" + "".join(choices(ascii_letters + digits, k=length))

    def __init__(self, parent_graph: "KnowledgeGraph", *, mid: str = None):
        super().__init__(parent_graph)
        self.__mid = mid or self.__random_mid()

    def __str__(self) -> str:
        return self.mid

    @property
    def mid(self) -> str:
        return self.__mid

    def add_relation(self, predicate: Ns, entity: Entity or str) -> None:
        self.g.add_relation(self, predicate, entity)

    def add(self, predicate: Ns, entity: Entity or str) -> None:
        """Alias for Subject.add_relation()"""
        self.add_relation(predicate, entity)

    def relations_to(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, Entity]]:
        yield from self.g.relations_to(self, via)

    def relations_from(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, Entity]]:
        yield from self.g.relations_from(self, via)


class Literal(Entity):
    """
    Representation of a knowledge graph's subject.
    It stores a reference to its parent graph as Subject.g.
    Its string representation is its string value Literal.s.
    """

    def __init__(self, parent_graph: "KnowledgeGraph", string_value: str):
        super().__init__(parent_graph)
        self.s = string_value

    def __str__(self) -> str:
        return self.s

    def add_relation(self, predicate: Ns, subject: Subject) -> None:
        if type(subject) is not Subject:
            raise ValueError(f"Literal must be related with Subject, not {type(subject)}")
        self.g.add_relation(subject, predicate, self)

    def add(self, predicate: Ns, subject: Subject) -> None:
        """Alias for Literal.add_relation()"""
        self.add_relation(predicate, subject)

    def relations_to(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        yield from self.g.relations_to(self, via)

    def relations_from(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        del via
        yield from ()


class KnowledgeGraph(object):
    """
    Simplified implementation of a knowledge graph-like structure

    Terminology used here is mostly aligned with RDF terminology:
    - The graph consists of triplets (s, p, o), describing a
      subject (s) and its relational predicate (p) with an entity.
    - Subjects are identified by a (random) machine identifier or mid.
    - An entity can be either another subject, represented by its mid
      string, prefixed with mid:, or a string literal.
    - All literals are strings, there are no expressive literal types.
      A literal's type is inferred from its predicate.
    - Predicates referring literals other subjects are implemented as
      graph edges.
    - Predicates referring to literals are implemented as graph node
      attributes to keep the graph clean from meaningless associations.
    - Predicates strictly adhere to the namespace definition.

    Graph traversal language is a simplified Gremlin dialect.
    """

    def __init__(self, *, namespace=Ns):
        self.g = nx.MultiDiGraph()
        self.ns = namespace
        self.literals_index = {}

    def __contains__(self, entity: Entity or str):
        return entity in self.g or entity in self.literals_index

    @staticmethod
    def is_mid(s: str) -> bool:
        return str(s).startswith("mid:")

    def new_subject(self, relations: dict = None) -> Subject:
        """Create a new subject with optional relations"""
        subject = Subject(self)
        if relations is not None:
            for relation, entity in relations.items():
                self.add_relation(subject, relation, entity)
        return subject

    def literal(self, string_value: str) -> Literal:
        """Create a new literal"""
        return Literal(self, string_value)

    def add_relation(self, subject: Subject, predicate: Ns, entity: Entity or str) -> Subject:
        """
        Add a triple for given subject, predicate, and object.

        :param subject: Subject
        :param predicate: Ns relation predicate
        :param entity: Subject or Literal
        :return: Subject
        """
        if type(entity) is str:
            entity = self.literal(entity)
        if type(entity) is Subject:
            self.g.add_edge(subject, entity, predicate=predicate)
        elif type(entity) is Literal:
            if subject not in self.g:
                self.g.add_node(subject)
            if predicate in self.g.node[subject]:
                self.g.node[subject][predicate].add(entity)
            else:
                self.g.node[subject][predicate] = {entity}

            # Update literals index
            if entity not in self.literals_index:
                self.literals_index[entity] = {predicate: {(subject, predicate, entity)}}
            elif predicate not in self.literals_index[entity]:
                self.literals_index[entity][predicate] = {(subject, predicate, entity)}
            else:
                self.literals_index[entity][predicate].add((subject, predicate, entity))

        else:
            raise ValueError(f"Entity has unsupported type `{type(entity)}`")

        return subject

    def add(self, subject: Subject, predicate: Ns, entity: Entity or str) -> Subject:
        """Alias for .add_relation()"""
        return self.add_relation(subject, predicate, entity)

    def remove_relation(self, subject: Subject, predicate: Ns, entity: Entity or str):
        """
        Forget about the predicate relation between a subject and an entity.

        :param subject:
        :param predicate:
        :param entity:
        :return: None
        """
        if type(entity) is str:
            entity = self.literal(entity)
        if type(entity) is Subject:
            self.g.remove_edge(subject, entity, key=predicate)
        elif type(entity) is Literal:
            self.g.node[subject][predicate].remove(entity)
            self.literals_index[entity][predicate].remove((subject, predicate, entity))
            if len(self.literals_index[entity][predicate]) == 0:
                del self.literals_index[entity][predicate]
            if len(self.literals_index[entity]) == 0:
                del self.literals_index[entity]
        else:
            raise ValueError("Can only remove relations between entities")

    def remove_entity(self, entity: Entity or str):
        """
        Forget about all relations with an entity.

        :param entity:
        :return: None
        """
        if type(entity) is str:
            entity = self.literal(entity)
        if type(entity) is Subject:
            # Update literals index while node still exists and edges are still iterable
            for _, to_relation, to_entity in self.relations_from(entity):
                if type(to_entity) is Literal:
                    self.literals_index[to_entity][to_relation].remove((entity, to_relation, to_entity))
                    if len(self.literals_index[to_entity][to_relation]) == 0:
                        del self.literals_index[to_entity][to_relation]
                    if len(self.literals_index[to_entity]) == 0:
                        del self.literals_index[to_entity]
            self.g.remove_node(entity)
        elif type(entity) is Literal:
            for subject, predicate, _ in self.relations_to(entity):
                self.g.node[subject][predicate].remove(entity)
                self.literals_index[entity][predicate].remove((subject, predicate, entity))
                if len(self.literals_index[entity][predicate]) == 0:
                    del self.literals_index[entity][predicate]
                if len(self.literals_index[entity]) == 0:
                    del self.literals_index[entity]
        else:
            raise ValueError(f"Entity has unsupported type `{type(entity)}`")

    def entities(self) -> Iterator[Entity]:
        """
        Iterate over all entities, both subjects and literals
        """
        yielded = set()
        for entity, entity_data in self.g.nodes(data=True):
            if entity not in yielded:
                yielded.add(entity)
                yield entity
            for k, v in entity_data.items():
                if type(k) is not Ns:
                    continue
                for literal in v:
                    if literal not in yielded:
                        yielded.add(literal)
                        yield literal

    def subjects(self) -> Iterator[Subject]:
        """
        Iterate over all subjects
        """
        for entity in self.entities():
            if type(entity) is Subject:
                yield entity

    def relations(self, via: Ns = None) -> Iterator[Tuple[Subject, Ns, Entity]]:
        """
        Iterate over all relation triplets
        """

        # Yield all relations among subjects (as stored in graph's edge data)
        for subject, entity, data in self.g.edges(data=True):
            # Only yield a subject's literal relations once even when it appears in multiple edges.
            if via is not None and data["predicate"] != via:
                continue
            yield subject, data["predicate"], entity

        # Yield all relations between subjects and literals (as stored in graph's node data)
        for subject, data in self.g.nodes(data=True):
            for predicate, literals in data.items():
                if type(predicate) is not Ns:
                    continue
                if via is not None and predicate != via:
                    continue
                for literal in literals:
                    yield subject, predicate, literal

    def relations_from(self, entity: Entity, via: Ns = None) -> Iterator[Tuple[Subject, Ns, Entity]]:
        if type(entity) is Subject:
            try:
                for predicate, literals in self.g.node[entity].items():
                    if type(predicate) is not Ns:
                        continue
                    if via is not None and predicate != via:
                        continue
                    for literal in literals:
                        yield entity, predicate, literal
                for successor in self.g.successors(entity):
                    for edge_data in self.g.get_edge_data(entity, successor).values():
                        predicate = edge_data["predicate"]
                        if type(predicate) is not Ns:
                            continue
                        if via is not None and predicate != via:
                            continue
                        yield entity, predicate, successor
            except nx.exception.NetworkXError as e:
                raise KeyError(f"Unknown subject `{entity}`") from e

    def relations_to(self, entity: Entity, via: Ns = None) -> Iterator[Tuple[Subject, Ns, Entity]]:
        if type(entity) is Subject:
            try:
                for predecessor in self.g.predecessors(entity):
                    for edge_data in self.g.get_edge_data(predecessor, entity).values():
                        predicate = edge_data["predicate"]
                        if type(predicate) is not Ns:
                            continue
                        if via is not None and predicate != via:
                            continue
                        yield predecessor, predicate, entity
            except nx.exception.NetworkXError as e:
                raise KeyError(f"Unknown subject `{entity}`") from e
        elif type(entity) is Literal:
            try:
                for predicate in list(self.literals_index[entity]):
                    if via is not None and predicate != via:
                        continue
                    # Must iterate over a list copy, because literals index might change outside iterator,
                    # resulting in RuntimeError: Set changed size during iteration
                    yield from list(self.literals_index[entity][predicate])
            except KeyError as e:
                raise KeyError(f"Unknown literal `{entity}`") from e
        else:
            raise ValueError(f"Unsupported entity type `{type(entity)}`")

    def __iter__(self) -> Iterator[Tuple[Subject, Ns, Entity]]:
        yield from self.relations()

    def to_graphml(self):
        # Stringify all entities in graph, because GraphML exporter doesn't like non-string objects.
        g = nx.DiGraph()
        for s, p, e in self.relations():
            g.add_edge(str(s), str(p), str(e))
        return nx.generate_graphml(g)

    def draw(self):

        # Plotting:
        # https://stackoverflow.com/questions/20381460/networkx-how-to-show-node-and-edge-attributes-in-a-graph-drawing

        # Compile list of edge labels
        edge_labels = {}
        for s, p, e in self:
            edge_labels[(s, e)] = str(p)

        # Compile list of node colors and sizes
        node_colors = []
        node_sizes = []
        for n in self.g.nodes():
            if type(n) is Subject:
                node_colors.append("blue")
                node_sizes.append(1200)
            else:
                node_colors.append("red")
                node_sizes.append(300)

        # Draw the graph
        pos = nx.drawing.nx_agraph.graphviz_layout(self.g, prog="neato", args="-Goverlap=prism")
        nx.draw_networkx_nodes(self.g, pos=pos,
                               node_color=node_colors,
                               node_size=node_sizes,
                               alpha=0.5)
        nx.draw_networkx_edges(self.g, pos=pos, alpha=0.7)
        nx.draw_networkx_edge_labels(self.g, pos=pos,
                                     edge_labels=edge_labels,
                                     font_size=6,
                                     font_weight="bold",
                                     alpha=0.7)
        nx.draw_networkx_labels(self.g, pos=pos,
                                font_size=9,
                                font_weight="bold")

    def __v_iter(self, start: Entity or List[Entity] or None) -> Iterator[Entity]:
        if start is None:
            yield from self.entities()
        elif type(start) is list:
            for entity in start:
                if entity in self:
                    yield entity
        else:
            if start in self:
                yield start

    def V(self, start: str or Entity or List[Entity or str] or Tuple[Entity or str] = None) -> "Gromlin":
        """Start a Gromlin query pipe"""
        if start is None:
            return Gromlin(graph=self, pipe=self.__v_iter(None))
        if type(start) is not list and type(start) is not tuple:
            start = [start]
        entity_list = []
        for thing in start:
            if type(thing) is str:
                entity_list.append(self.literal(thing))
            elif type(thing) is Literal or type(thing) is Subject:
                entity_list.append(thing)
        return Gromlin(graph=self, pipe=self.__v_iter(entity_list))


class Gromlin(object):
    """Minimalist knowledge graph query language inspired by Apache Gremlin"""

    def __init__(self, graph: KnowledgeGraph, pipe: Iterator[Entity]):
        self.g: KnowledgeGraph = graph
        self.p: Iterator[Entity] = pipe

    def __iter__(self) -> Iterator[Entity]:
        yield from self.p

    def __has_yield(self, relation: Ns, entity: Entity or None) -> Iterator[Entity]:
        yielded = set()
        for subject in self.p:
            if type(subject) is not Subject:
                continue
            for _, to_relation, to_entity in subject.relations_from(via=relation):
                if entity in yielded:
                    continue
                if to_relation != relation:
                    continue
                if entity is not None and to_entity != entity:
                    continue
                yielded.add(subject)
                yield subject

    def Has(self, relation: Ns, entity: Entity or str = None) -> "Gromlin":
        """Only select entities that have given relation with piped ones"""
        if type(entity) is str:
            entity = self.g.literal(entity)
        return Gromlin(self.g, pipe=self.__has_yield(relation, entity))

    def __out_yield(self, via: Ns or None) -> Iterator[Entity]:
        yielded = set()
        for subject in self.p:
            if type(subject) is not Subject:
                continue
            for _, to_relation, to_entity in subject.relations_from(via):
                if to_entity in yielded:
                    continue
                yielded.add(to_entity)
                yield to_entity

    def Out(self, via: Ns = None) -> "Gromlin":
        """Move on to all entities that piped ones point to, via edges named `via`"""
        return Gromlin(self.g, pipe=self.__out_yield(via))

    def __in_yield(self, via: Ns or None) -> Iterator[Subject]:
        yielded = set()
        for entity in self.p:
            for from_subject, to_relation, _ in entity.relations_to(via):
                if from_subject in yielded:
                    continue
                yielded.add(from_subject)
                yield from_subject

    def In(self, via: Ns = None) -> "Gromlin":
        """Move on to all entities that point to piped ones, via edges named `via`"""
        return Gromlin(self.g, pipe=self.__in_yield(via))

    def All(self) -> List[Entity]:
        return list(self)

    def GetLimit(self, n: int) -> List[Entity]:
        result = []
        for entity in self.p:
            result.append(entity)
            if len(result) >= n:
                break
        return result
