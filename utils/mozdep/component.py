# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
from pathlib import Path
from subprocess import check_output
from typing import Iterator, Iterable

from .knowledgegraph import KnowledgeGraph

logger = getLogger(__name__)


class ComponentDescriptor(object):

    def __init__(self, name: str):
        self.name = name
        self.dependencies = set()
        self.files = set()

    def add_dependency(self, dependency):
        self.dependencies.add(dependency)

    def add_file(self, file):
        self.files.add(file)


def chunked(iterable: Iterable or Iterator, chunk_size: int) -> Iterator:
    """Iterator over iterators over chunks of the iterable"""

    def inner_iterator(l, i: Iterator, n: int) -> Iterator:
        """Iterator over the lookahead l and up to n-1 elements from the iterator i"""
        yield l
        try:
            for _ in range(n - 1):
                yield next(i)
        except StopIteration:
            pass

    iterator = iter(iterable)
    while True:
        try:
            lookahead = next(iterator)
        except StopIteration:
            break
        yield inner_iterator(lookahead, iterator, chunk_size)


def call_mach_and_parse(repo_path: Path, chunk: Iterator[str]) -> dict:
    """mach file-info bugzilla-component file [file ...]"""

    mach_path = repo_path.resolve() / "mach"

    # Compile mach command, run it, and parse the output
    cmd = [str(mach_path), "file-info", "bugzilla-component"] + list(chunk)
    logger.debug(f"Calling `{' '.join(cmd[:5])} ...`")
    p = check_output(cmd, cwd=str(repo_path.resolve()))
    component_map = {}
    component = None
    for line in p.decode("utf-8").split("\n"):
        if not line.startswith("  "):
            component = line
        else:
w            # Any path from mach is relative to the mozilla repo topdir
            f = line.lstrip(" ")
            assert (repo_path / f).exists()
            component_map[f] = component
    return component_map


def files_to_components(files: Iterator[Path], chunk_size=50) -> Iterator[str]:
    for chunk in chunked(files, chunk_size):
        yield call_mach_and_parse(chunk)


def detect_components(repo_path: Path, g: KnowledgeGraph):

    all_file_names = set(g.V().Has("ns:fx.mc.file.path").Out("ns:fx.mc.file.path"))
    files_mapping = {}
    for chunk in chunked(all_file_names, 500):
        files_mapping.update(call_mach_and_parse(repo_path, chunk))

    for fp, c in files_mapping.items():
        fv = g.V(fp).In("ns:fx.mc.file.path").GetLimitV(1)[0]
        fv.add("ns:bz.product.component.name", c)

    return
