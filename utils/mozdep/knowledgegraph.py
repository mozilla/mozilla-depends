# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from abc import ABC, abstractmethod
from copy import deepcopy
import logging
from random import choices
from string import ascii_letters, digits
from json import dumps, loads
from typing import Iterator, List, Set

logger = logging.getLogger(__name__)


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
            name = Ns(name)

        if self.verify and not name.is_known():
            raise NamespaceError(f"Unknown namespace identifier {name.s}")

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


class NamespaceError(Exception):
    pass


class Ns(object):

    NS = {
        "mid": None,
        "ns": {
            "bz": {
                "product": {
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
                        "dep": {
                            "": None,
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
            "language": {
                "Name": None
            },
            "version": {
                "spec": None,
                "type": None
            },
        },
    }

    def __init__(self, path: str or List[str] or None = None, *, prefix: str = "ns"):
        self._str = None
        if type(path) is list:
            self._path = path
        elif path is None:
            self._path = [prefix]
        elif type(path) is str:
            self._path = self.parse(path)
        else:
            raise NamespaceError(f"Unsupported namespace initializer {type(path)}")

    def is_known(self):
        ns_pointer = self.NS
        try:
            for item in self._path:
                ns_pointer = ns_pointer[item]
        except KeyError:
            return False
        return True

    # def learn(self):
    #     # Add to NS dictionary
    #     raise NotImplemented

    @classmethod
    def parse(cls, s: str) -> List[str]:
        prefix, *rest = s.split(":")
        if len(rest) == 0:
            return [prefix]
        if len(rest) > 1:
            raise NamespaceError(f"Invalid namespace identifier `{s}`")
        if prefix not in cls.NS:
            raise NamespaceError(f"Invalid namespace `{prefix}`")
        return [prefix] + rest[0].split(".")

    def __getattr__(self, item) -> "Ns":
        return Ns(self._path + [item])

    @property
    def s(self):
        if self._str is None:
            if len(self._path) == 1:
                self._str = self._path[0]
            else:
                self._str = f"{':'.join([self._path[0], '.'.join(self._path[1:])])}"
        return self._str

    def __str__(self) -> str:
        return self.s

    def __repr__(self) -> str:
        return f"Ns('{self.s}')"

    def __hash__(self):
        return hash(self.s)

    def __eq__(self, other: str or "Ns"):
        if type(other) is Ns:
            other = other.s
        return self.s == other

    def __gt__(self, other: str or "Ns"):
        if type(other) is Ns:
            other = other.s
        return other.startswith(self.s)

    def __lt__(self, other: str or "Ns"):
        if type(other) is Ns:
            other = other.s
        return self.s.startswith(other)

    def __deepcopy__(self, memo):
        return Ns(self.s)
