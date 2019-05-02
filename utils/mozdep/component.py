# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
from os.path import realpath
from pathlib import Path
from subprocess import check_output
from typing import Iterator, Iterable, List

from .dependency import DependencyDescriptor

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


# Bugzilla component extraction via slow mach calls is slow unless you work in batches.

def iter_files_in_deps(deps: Iterator[DependencyDescriptor]) -> Iterator[Path]:
    for dep in deps:
        for f in dep.repo_files:
            yield f.resolve()


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


def call_mach_and_parse(chunk: Iterator[Path]) -> dict:
    """mach file-info bugzilla-component file [file ...]"""

    # Find mach executable somewhere up the tree
    mach_path = None
    first_file = next(chunk).resolve()
    f = first_file.parent
    root = Path("/")

    while mach_path is None and f != root:
        if (f / "mach").is_file() and (f / "moz.configure").is_file():
            mach_path = f / "mach"
    if mach_path is None:
        raise Exception("Unable to find mach binary")

    # Compile mach command, run it, and parse the output
    cmd = [str(mach_path), "file-info", "bugzilla-component"] + \
          [str(first_file)] + list(map(realpath, chunk))
    logger.debug(f"Calling `{' '.join(cmd[:5])} ...`")
    p = check_output(cmd)
    component_map = {}
    component = None
    for line in p.decode("utf-8").split("\n"):
        if not line.startswith("  "):
            component = line
        else:
            # Any path from mach is relative to the mozilla repo topdir
            f = mach_path.parent / Path(line.lstrip(" "))
            assert f.exists()
            component_map[f.resolve()] = component
    return component_map


def files_to_components(files: Iterator[Path], chunk_size=50) -> Iterator[str]:
    for chunk in chunked(files, chunk_size):
        yield call_mach_and_parse(chunk)


def detect_components(deps: Iterator[DependencyDescriptor]) -> Iterator[ComponentDescriptor]:

    # Unfortunately we need to break down the pipeline here for iterating it twice.
    # The speed-up from calling mach with huge chunks of files instead of once
    # per dependency is just too massive to ignore.

    all_deps = list(deps)
    all_files = set(iter_files_in_deps(all_deps))
    logger.debug(f"Extracting components for {len(all_files)} files from {len(all_deps)} dependencies")

    files_mapping = {}
    for chunk in chunked(all_files, 500):
        files_mapping.update(call_mach_and_parse(chunk))

    components_mapping = {}
    for dep in all_deps:
        components_for_dep = set()
        for f in iter_files_in_deps([dep]):
            component = files_mapping[f]
            components_for_dep.add(component)
        for component in components_for_dep:
            try:
                components_mapping[component].add(dep)
            except KeyError:
                components_mapping[component] = {dep}

    for component in components_mapping:
        cd = ComponentDescriptor(name=component)
        for dep in components_mapping[component]:
            cd.add_dependency(dep)
        yield cd
