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
from json import dumps, loads
from typing import Iterator, List, Set, Tuple

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
                    },
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
                "id": None,
                "version_match": None,
                "summary": None,
                "description": None,
                "class": None,
                "severity": None,
                "info_link": None,
                "affects": None,
                "database": None,
                "detector_name": None,
            },
        },
    }

    _index = None

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
                next_ns = getattr(ns, key)
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


class Vertex(object):
    """A regular graph vertex associated with one or more edges"""

    def __init__(self, graph, mid_or_edge):
        self.g = graph
        if type(mid_or_edge) is str:
            self.mid = mid_or_edge
        else:
            self.mid = mid_or_edge.mid

    def __iter__(self) -> Iterator["Edge"]:
        for name, right_set in self.g.mid_map[self.mid].items():
            for right in right_set:
                yield Edge(self.g, mid=self.mid, name=name, right=right)

    def __getitem__(self, item):
        return self.g.mid_map[self.mid][item]

    def add(self, name: str, right: "Vertex" or "Sink" or str) -> "Vertex":
        self.g.add(name, right, mid_or_vertex=self.mid)
        return self


class Sink(object):
    """A regular graph vertex associated with one or more edges"""

    def __init__(self, graph, right_or_edge):
        self.g = graph
        if type(right_or_edge) is str:
            self.mid = right_or_edge
        else:
            self.mid = right_or_edge.mid

    def __iter__(self) -> Iterator["Edge"]:
        yield from ()

    def add(self, name: str, right: "Vertex" or "Sink" or str) -> "Vertex":
        raise NotImplemented


class Edge(object):

    def __init__(self, graph, *, name: str, mid: str, right: str):
        self.g = graph
        self.name = name
        self.mid = mid
        self.right = right

    def __str__(self) -> str:
        return f"<Edge(graph=0x{hex(id(self.g))} mid={self.mid} name={self.name} right={self.right})>"

    def left(self) -> "Vertex":
        return Vertex(self.g, self.mid)

    def r(self) -> "Vertex" or "Sink":
        if self.g.is_mid(self.right):
            return Vertex(self.g, self.right)
        else:
            return Sink(self.g, self.right)


class EdgeQuery(object):
    def __init__(self, graph, pipe: Iterator[Edge]):
        self.g = graph
        self.p = pipe

    def __iter__(self) -> Iterator[Edge]:
        yield from self.p

    def All(self) -> List[Edge]:
        return list(self)


class VertexQuery(object):
    def __init__(self, graph, pipe: Iterator[str]):
        self.g = graph
        self.p = pipe

    def __iter__(self) -> Iterator[str]:
        yield from self.p

    def __has_yield(self, name: str, right_or_vertex: str or Vertex or None) -> Iterator[str]:
        if right_or_vertex is None:
            right = None
        elif type(right_or_vertex) is Vertex:
            right = right_or_vertex.mid
        else:
            right = right_or_vertex
        for mid_or_right in self:
            if self.g.is_mid(mid_or_right):
                # We have vertice's mid, so iterate edges
                for edge_name, right_set in self.g.mid_map[mid_or_right].items():
                    if edge_name == name:
                        if right is None or right in right_set:
                            yield mid_or_right
            elif self.g.is_right(mid_or_right):
                # Nothing to do if it's a pure right value
                continue
            else:
                raise Exception("まさか！")

    def Has(self, name: str, value_or_vertex: str or Vertex or None = None) -> "VertexQuery":
        """Only select vertices that have an edge with `name` pointing to `value_or_vertex`"""
        return VertexQuery(self.g, pipe=self.__has_yield(name, value_or_vertex))

    def __out_yield(self, via: str) -> Iterator[str]:
        yielded = set()
        for mid_or_right in self:
            if self.g.is_mid(mid_or_right):
                for name, right_set in self.g.mid_map[mid_or_right].items():
                    if via is None or name == via:
                        for right in right_set:
                            if right not in yielded:
                                yielded.add(right)
                                yield right
            elif self.g.is_right(mid_or_right):
                # Nothing to do if it's a pure right value
                continue
            else:
                raise Exception("まさか！")

    def Out(self, via: str or None = None) -> "VertexQuery":
        """Follow all vertices that this one points to, via edges named `via`"""
        return VertexQuery(self.g, pipe=self.__out_yield(via))

    def __in_yield(self, via: str) -> Iterator[str]:
        yielded = set()
        for mid_or_right in self:
            if mid_or_right in self.g.right_map:
                # We only care about those which occur as right values (ie. are being pointed to)
                for name, mid_set in self.g.right_map[mid_or_right].items():
                    if via is None or name == via:
                        for mid in mid_set:
                            if mid not in yielded:
                                yielded.add(mid)
                                yield mid

    def In(self, via: str or None = None) -> "VertexQuery":
        """Follow all vertices that point to this one, via edges named `via`"""
        return VertexQuery(self.g, pipe=self.__in_yield(via))

    def All(self) -> List[str]:
        return list(self)

    def AllV(self) -> List[Vertex or Sink]:
        all_v = list()
        for mid_or_right in self:
            if self.g.is_mid(mid_or_right):
                all_v.append(Vertex(self.g, mid_or_right))
            else:
                all_v.append(Sink(self.g, mid_or_right))
        return all_v

    def GetLimit(self, n: int) -> List[str]:
        r = []
        count = 0
        for mid in self:
            r.append(mid)
            if count >= n:
                break
        return r

    def GetLimitV(self, n: int) -> List[Vertex]:
        r = []
        count = 0
        for mid in self:
            r.append(Vertex(self.g, mid))
            if count >= n:
                break
        return r


class KnowledgeGraph(object):

    def __init__(self, *, verify_namespace=True):
        self.mid_map = dict()  # mapping MIDs to named edges objects
        self.right_map = dict()  # mapping all Edge.right to MIDs
        self.verify = verify_namespace

    def __contains__(self, mid_or_right: str):
        return mid_or_right in self.mid_map or mid_or_right in self.right_map

    @staticmethod
    def __random_mid(length: int = 10) -> str:
        """Generate random machine ID"""
        return "mid:" + "".join(choices(ascii_letters + digits, k=length))

    def generate_mid(self) -> str:
        for _ in range(4):
            mid = self.__random_mid()
            if mid not in self:
                return mid
        raise Exception("KnowledgeGraph MID space exhausted. Too many retries for generating MID.")

    def is_mid(self, mid: str) -> bool:
        return mid.startswith("mid:") and mid in self.mid_map

    def is_right(self, right: str) -> bool:
        return right in self.right_map

    def get_v(self, mid_or_right) -> Vertex or str:
        if mid_or_right in self.mid_map:
            return Vertex(self, mid_or_right)
        else:
            return mid_or_right

    def add(self, name: str or "Ns", right_or_vertex: str or Vertex, *,
            mid_or_vertex: str or Vertex or None = None) -> Vertex:
        # logger.warn(name, mid_or_vertex, right_or_vertex)
        # assert type(name) is str
        # assert type(mid_or_vertex) is str or type(mid_or_vertex) is Vertex or mid_or_vertex is None
        # assert type(right_or_vertex) is str or type(right_or_vertex) is Vertex

        if type(name) is not Ns:
            name = Ns(name, check=self.verify)

        if self.verify and not name.is_known():
            raise NamespaceError(f"Unknown namespace identifier {name}")

        mid_or_vertex = mid_or_vertex or self.generate_mid()
        if type(mid_or_vertex) is Vertex:
            mid_or_vertex = mid_or_vertex.mid
        if type(right_or_vertex) is Vertex:
            right_or_vertex = right_or_vertex.mid
            assert self.is_right(right_or_vertex) or self.is_mid(right_or_vertex)

        if mid_or_vertex not in self.mid_map:
            self.mid_map[mid_or_vertex] = dict()
        if name not in self.mid_map[mid_or_vertex]:
            self.mid_map[mid_or_vertex][name] = set()
        self.mid_map[mid_or_vertex][name].add(right_or_vertex)

        if right_or_vertex not in self.right_map:
            self.right_map[right_or_vertex] = dict()
        if name not in self.right_map[right_or_vertex]:
            self.right_map[right_or_vertex][name] = set()
        self.right_map[right_or_vertex][name].add(mid_or_vertex)

        return Vertex(self, mid_or_vertex)

    def __delete_edge(self, mid: str, name: str, right: str):
        self.mid_map[mid][name].remove(right)
        self.right_map[right][name].remove(mid)
        if len(self.right_map[right][name]) == 0:
            del self.right_map[right][name]

    def delete_edge(self, edge: Edge):
        self.__delete_edge(edge.mid, edge.name, edge.right)

    def delete_vertex(self, mid: str or Vertex):
        if type(mid) is Vertex:
            mid = mid.mid
        for name in self.mid_map[mid]:
            for right in self.mid_map[mid][name]:
                self.__delete_edge(mid, name, right)

    def delete(self, mid_or_edge):
        if type(mid_or_edge) is Edge:
            self.delete_edge(mid_or_edge)
        else:
            self.delete_vertex(mid_or_edge)

    def __iter__(self):
        for mid in self.mid_map:
            yield from self.mid_map[mid].values()

    def edge_namespace(self) -> Set[str]:
        names = set()
        for name_map in self.mid_map.values():
            for name in name_map.keys():
                names.add(name)
        return names

    def as_dict(self) -> dict:
        """Return deep copy dict representation of the graph"""
        r = deepcopy(self.mid_map)
        for nd in r.values():
            for n in nd:
                nd[n] = list(nd[n])
        return r

    def as_json(self, pretty=False) -> str:
        """Return JSON representation of the graph"""
        if pretty:
            return dumps(self.as_dict(), indent=4, sort_keys=True)
        else:
            return dumps(self.as_dict())

    def from_dict(self, data: dict):
        self.mid_map = dict()
        self.right_map = dict()
        for mid in data:
            for name, right_set in data[mid].items():
                for right in right_set:
                    self.add(mid_or_vertex=mid, name=name, right_or_vertex=right)

    def from_json(self, json_str: str):
        self.from_dict(loads(json_str))

    # def __e_iter(self, mid_or_right: str or None = None) -> Iterator[Edge]:
    #     if mid_or_right is None:
    #         yield from self.g
    #     else:
    #         if mid_or_right in self.mid_map:
    #             yield from self.mid_map[mid_or_right].values()
    #         if mid_or_right in self.right_map:
    #             for name, mid_set in self.right_map[mid_or_right].items():
    #                 for mid in mid_set:
    #                     yield self.mid_map[mid][name]
    #
    # def E(self, mid_or_right: str or None = None) -> EdgeQuery:
    #     return EdgeQuery(graph=self, pipe=self.__e_iter(mid_or_right))

    def __v_iter(self, mid_or_right: str or List[str] or Vertex or List[Vertex] or None) -> Iterator[str]:
        yielded = set()
        if mid_or_right is None:
            for mid in self.mid_map:
                if mid in yielded:
                    continue
                yielded.add(mid)
                yield mid
            for right in self.right_map:
                if right not in yielded:
                    yielded.add(right)
                    yield right
        elif type(mid_or_right) is str:
            if mid_or_right in self.mid_map:
                if mid_or_right not in yielded:
                    yielded.add(mid_or_right)
                    yield mid_or_right
            elif mid_or_right in self.right_map:
                if mid_or_right not in yielded:
                    yielded.add(mid_or_right)
                    yield mid_or_right
        elif type(mid_or_right) is Vertex:
            yield mid_or_right.mid
        elif type(mid_or_right) is list:
            for str_or_vertex in mid_or_right:
                if type(str_or_vertex) is str:
                    if str_or_vertex in self.mid_map:
                        if str_or_vertex not in yielded:
                            yielded.add(str_or_vertex)
                            yield str_or_vertex
                    elif str_or_vertex in self.right_map:
                        if str_or_vertex not in yielded:
                            yielded.add(str_or_vertex)
                            yield str_or_vertex
                elif type(str_or_vertex) is Vertex:
                    yield str_or_vertex.mid
                else:
                    raise Exception(f"Graph can't iterate unsupported type in list {type(str_or_vertex)}")
        else:
            raise Exception(f"Graph can't iterate unsupported type {type(mid_or_right)}")

    def V(self, mid_or_right: str or List[str] or Vertex or List[Vertex] or None = None) -> VertexQuery:
        return VertexQuery(graph=self, pipe=self.__v_iter(mid_or_right))

    def to_x(self):
        g = nx.DiGraph()
        for mid in self.mid_map:
            for edge_name in self.mid_map[mid]:
                for right in self.mid_map[mid][edge_name]:
                    g.add_edge(mid, right, t=edge_name)
        return g


# Plotting:
# https://stackoverflow.com/questions/20381460/networkx-how-to-show-node-and-edge-attributes-in-a-graph-drawing

class Entity(ABC):
    """
    Base clas for KnowledgeGraph entities which can be a subject, or a string literal.
    Guarantee for Entity objects:
      - Have a string representation
      - Are hashable
      - Contain a reference Entity.g to their base graph
    """

    def __init__(self, g: "KnowledgeGraphX"):
        self.g = g

    @abstractmethod
    def __str__(self) -> str:
        return ""

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other) -> bool:
        return str(self) == str(other)

    @abstractmethod
    def relations_to(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        del via
        yield from ()

    @abstractmethod
    def relations_from(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        del via
        yield from ()


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

    def __init__(self, parent_graph: "KnowledgeGraphX", *, mid: str = None):
        super().__init__(parent_graph)
        self.__mid = mid or self.__random_mid()

    def __str__(self) -> str:
        return self.mid

    @property
    def mid(self) -> str:
        return self.__mid

    def add_relation(self, predicate: Ns, entity: "Subject" or "Literal") -> None:
        self.g.add_relation(self, predicate, entity)

    def relations_to(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        yield from self.g.relations_to(self, via)

    def relations_from(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        yield from self.g.relations_from(self, via)

    def __repr__(self) -> str:
        return f"Subject('{self.mid}')"


class Literal(Entity):
    """
    Representation of a knowledge graph's subject.
    It stores a reference to its parent graph as Subject.g.
    Its string representation is its string value Literal.s.
    """

    def __init__(self, parent_graph: "KnowledgeGraphX", string_value: str):
        super().__init__(parent_graph)
        self.s = string_value

    def __str__(self) -> str:
        return self.s

    def __repr__(self) -> str:
        return f"Literal('{self.s}')"

    def relations_to(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        yield from self.g.relations_to(self, via)

    def relations_from(self, via: Ns = None) -> Iterator[Tuple["Subject", Ns, "Entity"]]:
        del via
        yield from ()


class KnowledgeGraphX(object):
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

    def add_relation(self, subject: Subject, predicate: Ns, entity: Subject or Literal or str) -> Subject:
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
        else:
            raise ValueError(f"Entity has unsupported type `{type(entity)}`")
        return subject

    def add(self, subject: Subject, predicate: Ns, entity: Subject or Literal) -> Subject:
        """Alias for .add_relation()"""
        return self.add_relation(subject, predicate, entity)

    def remove_relation(self, subject: Subject, predicate: Ns, entity: Subject or Literal):
        """
        Forget about the predicate relation between a subject and an entity.

        :param subject:
        :param predicate:
        :param entity:
        :return: None
        """
        self.g.remove_edge(subject, entity, predicate=predicate)

    def remove_entity(self, entity: Subject or Literal):
        """
        Forget about all relations with an entity.

        :param entity:
        :return: None
        """
        self.g.remove_node(entity)

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

    def subjects(self) -> Iterator[Entity]:
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

    def relations_to(self, entity: Entity, via: Ns = None) -> Iterator[Tuple[Subject, Ns, Entity]]:
        if type(entity) is Subject:
            for predecessor in self.g.predecessors(entity):
                for edge_data in self.g.get_edge_data(predecessor, entity).values():
                    predicate = edge_data["predicate"]
                    if type(predicate) is not Ns:
                        continue
                    if via is not None and predicate != via:
                        continue
                    yield predecessor, predicate, entity
        elif type(entity) is Literal:
            # FIXME: Iterating all relations is a dumb, slow approach. Speed this up by using a literals index.
            logger.warning("FIXME: the .relations_to() implementation is awfully slow for literals")
            for subject, predicate, to_entity in self.relations(via):
                if to_entity == entity:
                    if via is not None and predicate != via:
                        continue
                    yield subject, predicate, entity
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
            yield from start
        else:
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

    def __init__(self, graph: KnowledgeGraphX, pipe: Iterator[Entity]):
        self.g: KnowledgeGraphX = graph
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
        """Only select entities that have given relation with an entity."""
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
        """Move to all entities that this one points to, via edges named `via`"""
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
        """Move to all entities that point to this one, via edges named `via`"""
        return Gromlin(self.g, pipe=self.__in_yield(via))

    def All(self) -> List[Entity]:
        return list(self)

    def GetLimit(self, n: int) -> List[Entity]:
        result = []
        count = 0
        for entity in self.p:
            result.append(entity)
            if count >= n:
                break
        return result
