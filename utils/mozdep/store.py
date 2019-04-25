# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class StoreManager(object):
    """
    Abstract implementation of a language/technology-specific store
    inside the mirror. It implements sore-specific functionality like
    enumeration, update checking, and vulnerability scanning.
    """

    @property
    def name(self) -> str:
        return "dummy"

    def __init__(self, root: Path):
        self.root = root
        self.base = self.root / self.name

    def list(self) -> dict:
        res = {}
        for dependency_path in sorted(self.base.glob("*")):
            for version_path in sorted(dependency_path.glob("*")):
                version = version_path.name
                if version.startswith(dependency_path.name):
                    version = version[len(dependency_path.name)+1:]
                try:
                    res[dependency_path.name].append(version)
                except KeyError:
                    res[dependency_path.name] = [version]
        return res

    def diff(self) -> dict or None:
        return None

    @abstractmethod
    def update(self) -> bool:
        return False


class RustStoreManager(StoreManager):
    """
    This class represents the Rust store inside the mirror.
    It bundles all functionality common to Rust crates.
    """
    def name(self) -> str:
        return "rust"

    def list(self):
        pass


class NodeStoreManager(StoreManager):
    """
    This class represents the Rust store inside the mirror.
    It bundles all functionality common to Node modules.
    """
    pass


class CppStoreManager(StoreManager):
    """
    This class represents the C++ store inside the mirror.
    It bundles all functionality common to C++ libraries.
    """
    pass


class JsStoreManager(StoreManager):
    """
    This class represents the JS library store inside the mirror.
    It bundles all functionality common to JS libraries.
    """
    pass


class StoreObject():
    """
    This class represents a reference to a single library / dependency. It knows about
    associated files and directories in the source tree as well as files in the mirror.
    It implements logic to compare states.
    """
    pass
