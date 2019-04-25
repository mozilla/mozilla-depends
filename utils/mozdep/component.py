# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from itertools import islice
from pathlib import Path
from typing import Iterator, List

from .dependency import DependencyDescriptor

class ComponentDescriptor(dict):
    pass


# Bugzilla component extraction via slow mach calls is slow unless you work in batches.

def iter_files_in_deps(deps: Iterator[DependencyDescriptor]) -> Iterator[Path]:
    for dep in deps:
        for f in dep.repo_files:
            yield f


def chunked(iterable, n: int) -> Iterator[list]:
    i = iter(iterable)
    while True:
        chunk = list(islice(i, n))
        if not chunk:
            return
        yield chunk

def call_mach_and_parse():
    """mach file-info bugzilla-component"""


def files_to_components(files: Iterator[Path], chunk_size=50) -> Iterator[str]:
    for chunk in chunked(files, chunk_size):
        call_mach_and_parse(chunk)

def detect_components(deps: Iterator[DependencyDescriptor]) -> Iterator[ComponentDescriptor]:

    # Extract files to components mapping