# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from pathlib import Path
from subprocess import run, PIPE, DEVNULL
from typing import Iterator
import logging

logger = logging.getLogger(__name__)


def get_mozilla_component(path: Path, tree: Path) -> str or None:
    cmd = [tree / "mach", "file-info", "bugzilla-component", str(path)]
    cmd_output = run(cmd, check=False, stdout=PIPE, stderr=DEVNULL).stdout
    if len(cmd_output) == 0:
        return None
    else:
        return cmd_output.decode("utf-8").split("\n")[0]


class HgRepo(object):

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.__source_stamp = None

    def find(self, glob: str = "*", relative: bool = False, start: Path = None) -> Iterator[Path]:
        start = start or self.path
        matches = filter(lambda p: p.parents[1] != ".hg", start.rglob(glob))
        for path in matches:
            if relative:
                yield path.relative_to(self.path)
            else:
                yield path

    @property
    def source_stamp(self):
        if self.__source_stamp is None:
            cmd = ["hg", "id", "-r", "tip", "-T", "{rev}:{node}"]
            cmd_output = run(cmd, cwd=str(self.path), check=True, stdout=PIPE, stderr=DEVNULL).stdout
            if len(cmd_output) == 0:
                self.__source_stamp = None
            else:
                self.__source_stamp = cmd_output.decode("utf-8").strip("\n")
        return self.__source_stamp
