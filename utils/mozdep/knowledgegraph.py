# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from random import choices
from string import ascii_letters, digits
from json import dumps, loads
from typing import Iterator

logger = logging.getLogger(__name__)


class OldKnowledgeGraph(object):

    class Vertex(object):

        def __init__(self, mid: str, name: str):
            self.mid = mid
            self.name = name

    class Edge(object):

        def __init__(self, mid: str, name: str, left: str, right: str):
            self.mid = mid
            self.name = name
            self.left = left
            self.right = right

    def __init__(self):
        self.__mid_index = dict()
        self.__v = dict()
        self.__e = dict()

    def __contains__(self, mid_or_vertex_or_edge: str or Vertex or Edge):
        # return mid not in self.__v and mid not in self.__e
        if type(mid_or_vertex_or_edge) is str:
            return mid_or_vertex_or_edge in self.__mid_index
        elif type(mid_or_vertex_or_edge) is self.Vertex or type(mid_or_vertex_or_edge) is self.Edge:
            return mid_or_vertex_or_edge.mid in self.__mid_index
        else:
            raise Exception(f"KnowledgeGraph can't contain `{repr(mid_or_vertex_or_edge)}`")

    @staticmethod
    def __random_mid(length: int = 10) -> str:
        """Generate random machine ID"""
        return "".join(choices(ascii_letters + digits, k=length))

    def generate_mid(self) -> str:
        for _ in range(4):
            mid = self.__random_mid()
            if mid not in self:
                return mid
        raise Exception("KnowledgeGraph is full. Too many retries for generating MID.")

    def add_vertex(self, name: str) -> Vertex:
        v = self.Vertex(self.generate_mid(), name)
        self.__v[v.mid] = v
        self.__mid_index[v.mid] = v
        return v

    def add_edge(self, name: str, left: Vertex, right: Vertex) -> Edge:
        e = self.Edge(self.generate_mid(), name, left.mid, right.mid)
        self.__e[e.mid] = e
        self.__mid_index[e.mid] = e
        return e

    def iter_vertices(self, copy=False) -> Iterator[Vertex]:
        if not copy:
            yield from self.__v.values()
        else:
            for v in self.__v.values():
                yield self.Vertex(v.mid, v.name)

    def iter_edges(self, copy=False) -> Iterator[Edge]:
        if not copy:
            yield from self.__e.values()
        else:
            for e in self.__e.values():
                yield self.Edge(e.mid, e.name, e.left, e.right)

    def as_dict(self) -> dict:
        """Return deep copy dict representation of the graph"""
        r = {
            "vertices": {},
            "edges": {}
        }
        for v in self.__v.values():
            r["vertices"][v.mid] = {
                "mid": v.mid,
                "name": v.name
            }
        for e in self.__e.values():
            r["edges"][e.mid] = {
                "mid": e.mid,
                "name": e.name,
                "left": e.left,
                "right": e.right
            }
        return r

    def as_json(self, pretty=False) -> str:
        """Return JSON representation of the graph"""
        if pretty:
            return dumps(self.as_dict(), indent=4, pretty=True)
        else:
            return dumps(self.as_dict())

    def validate(self):
        assert len(self.__mid_index) == len(self.__v) + len(self.__e)
        for v in self.iter_vertices(copy=False):
            assert v.mid in self.__v
            assert v.mid not in self.__e
            assert v.mid in self.__mid_index
        for e in self.iter_edges(copy=False):
            assert e.mid in self.__e
            assert e.mid not in self.__v
            assert e.mid in self.__mid_index
            assert e.left in self.__v
            assert e.right in self.__v

    def from_dict(self, data: dict, validate: bool = True):
        self.__mid_index = {}
        self.__v = {}
        self.__e = {}
        for v in data["vertices"]:
            n = self.Vertex(v["mid"], v["name"])
            self.__v[n.mid] = n
            self.__mid_index[n.mid] = n
        for e in data["edges"]:
            n = self.Edge(e["mid"], e["name"], e["left"], e["right"])
            self.__e[n.mid] = n
            self.__mid_index[n.mid] = n
        if validate:
            self.validate()

    def from_json(self, json_str: str):
        self.from_dict(loads(json_str))


class Edge(object):

    def __init__(self, graph, *, name: str, mid: str, right: str):
        self.g = graph
        self.name = name
        self.mid = mid
        self.right = right

    def __str__(self):
        return f"<Edge(graph=0x{hex(id(self.g))} mid={self.mid} name={self.name} right={self.right})>"


class Vertex(object):

    def __init__(self, graph, mid_or_edge):
        self.g = graph
        if type(mid_or_edge) is str:
            self.mid = mid_or_edge
        else:
            self.mid = mid_or_edge.mid

    def edges(self):
        yield from self.g.mid_map[self.mid].values()


# class EdgeQuery(object):
#     def __init__(self, graph, pipe: Iterator[Edge]):
#         self.g = graph
#         self.p = pipe
#
#     def __iter__(self):
#         yield from self.p
#
#     def __has_yield(self, name: str, value: str):
#         for e in self.p:
#             if e.name == name and e.right == value:
#                 yield e
#
#     def Has(self, name: str, value: str):
#         """Yield all edges from pipe that have field `name` like `value`"""
#         return EdgeQuery(self.g, pipe=self.__has_yield(name, value))
#
#     def __out_yield(self, via):
#         yielded = set()
#         for in_e in self.p:
#             for name, out_e in self.g.right_map[in_e.right].items():
#                 if via is None or name == via:
#                     if out_e not in yielded:
#                         yielded.add(out_e)
#                         yield out_e
#
#     def Out(self, via: str or None = None):
#         """Follow all vertices that this one points to, via edges named `via`"""
#         return EdgeQuery(self.g, pipe=self.__out_yield(via))
#
#     def __in_yield(self, via):
#         yielded = set()
#         for in_e in self.p:
#             for name, mid_set in self.g.right_map[in_e.right].items():
#                 if via is None or name == via:
#                     for mid in mid_set:
#                         out_e = self.g.mid_map[mid][name]
#                         if out_e not in yielded:
#                             yielded.add(out_e)
#                             yield out_e
#
#     def In(self, via: str or None = None):
#         """Follow all vertices that point to this one, via edges named `via`"""
#         return EdgeQuery(self.g, pipe=self.__in_yield(via))
#
#     def All(self):
#         return list(self)


class VertexQuery(object):
    def __init__(self, graph, pipe: Iterator[str]):
        self.g = graph
        self.p = pipe

    def __iter__(self):
        yield from self.p

    def __has_yield(self, name: str, value_or_vertex: str or Vertex):
        if type(value_or_vertex) is Vertex:
            value = value_or_vertex.mid
        else:
            value = value_or_vertex
        for mid_or_right in self:
            if mid_or_right in self.g.mid_map:
                # We have vertice's mid, so iterate edges
                for e in self.g.mid_map[mid_or_right].values():
                    if e.name == name and e.right == value:
                        yield mid_or_right
                        break
            elif mid_or_right in self.g.right_map:
                # Nothing to do if it's a pure right value
                continue
            else:
                raise Exception("まさか！")

    def Has(self, name: str, value_or_vertex: str or Vertex):
        """Only select vertices that have an edge with `name` pointing to `value_or_vertex`"""
        return VertexQuery(self.g, pipe=self.__has_yield(name, value_or_vertex))

    def __out_yield(self, via: str):
        yielded = set()
        for mid_or_right in self:
            if mid_or_right in self.g.mid_map:
                for name, e in self.g.mid_map[mid_or_right].items():
                    if via is None or name == via:
                        if e.right not in yielded:
                            yielded.add(e.right)
                            yield e.right
            elif mid_or_right in self.g.right_map:
                # Nothing to do if it's a pure right value
                continue
            else:
                raise Exception("まさか！")

    def Out(self, via: str or None = None):
        """Follow all vertices that this one points to, via edges named `via`"""
        return VertexQuery(self.g, pipe=self.__out_yield(via))

    def __in_yield(self, via: str):
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

    def In(self, via: str or None = None):
        """Follow all vertices that point to this one, via edges named `via`"""
        return VertexQuery(self.g, pipe=self.__in_yield(via))

    def All(self):
        return set(self)


class KnowledgeGraph(object):

    def __init__(self):
        self.mid_map = dict()  # mapping MIDs to named edges objects
        self.right_map = dict()  # mapping all Edge.right to MIDs

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

    def add(self, name: str, right: str, *, mid: str or None = None) -> Edge:
        mid = mid or self.generate_mid()
        e = Edge(self, name=name, right=right, mid=mid)
        if e.mid not in self.mid_map:
            self.mid_map[e.mid] = dict()
        assert e.name not in self.mid_map[e.mid]  # FIXME: handle this gracefully by deleting existing edge from rights
        self.mid_map[e.mid][e.name] = e
        if e.right not in self.right_map:
            self.right_map[e.right] = dict()
        if e.name not in self.right_map[e.right]:
            self.right_map[e.right][e.name] = set()
        self.right_map[e.right][e.name].add(e.mid)
        return e

    def delete_edge(self, edge: Edge):
        del self.mid_map[edge.mid]
        self.right_map[edge.right][edge.name].remove(edge.mid)

    def delete_vertex(self, mid: str):
        for edge in self.mid_map[mid].values():
            self.delete_edge(edge)

    def delete(self, mid_or_edge):
        if type(mid_or_edge) is Edge:
            self.delete_edge(mid_or_edge)
        else:
            self.delete_vertex(mid_or_edge)

    def __iter__(self):
        for mid in self.mid_map:
            yield from self.mid_map[mid].values()

    def as_dict(self) -> dict:
        """Return deep copy dict representation of the graph"""
        r = dict()
        for mid in self.mid_map:
            for edge in self.mid_map[mid].values():
                if edge.mid not in r:
                    r[edge.mid] = {}
                r[edge.mid][edge.name] = edge.right
        return r

    def as_json(self, pretty=False) -> str:
        """Return JSON representation of the graph"""
        if pretty:
            return dumps(self.as_dict(), indent=4, sort_keys=True)
        else:
            return dumps(self.as_dict())

    def from_dict(self, data: dict):
        self.mid_map = {}
        self.right_map = {}
        for mid in data:
            for name, right in data[mid].items():
                self.add(mid=mid, name=name, right=right)

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

    def __v_iter(self, mid_or_right: str or None = None) -> Iterator[str]:
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
        else:
            if mid_or_right in self.mid_map:
                if mid_or_right not in yielded:
                    yielded.add(mid_or_right)
                    yield mid_or_right
            elif mid_or_right in self.right_map:
                if mid_or_right not in yielded:
                    yielded.add(mid_or_right)
                    yield mid_or_right

    def V(self, mid_or_right: str or None = None) -> VertexQuery:
        return VertexQuery(graph=self, pipe=self.__v_iter(mid_or_right))
