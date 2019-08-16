# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from abc import abstractmethod, ABC, abstractproperty
from pathlib import Path

from mozdep.knowledgegraph import KnowledgeGraph
from mozdep.repo_utils import HgRepo


class DependencyDetector(ABC):
    """
    Abstract base class for detectors, scanning a local copy of
    mozilla-central for in-tree third-party dependencies.
    """

    @staticmethod
    @abstractmethod
    def name() -> str:
        return "dummy"

    @staticmethod
    @abstractmethod
    def priority() -> int:
        return 0

    def __init__(self, tree: Path, graph: KnowledgeGraph, **kwargs):
        self.args = kwargs
        self.g = graph
        self.hg = HgRepo(tree)
        self.state = None
        super().__init__()

    @staticmethod
    def setup() -> bool:
        return True

    @staticmethod
    @abstractmethod
    def run() -> None:
        pass

    @staticmethod
    def teardown() -> None:
        pass
