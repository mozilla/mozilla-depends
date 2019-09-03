# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from pathlib import Path
import pytest

import tests
from mozdep.config import ConfigManager


@pytest.fixture(name="config_manager")
def fixture_config_manager(tmpdir):
    args = tests.ArgsMock(workdir=Path(tmpdir))
    return ConfigManager(args, singleton_check=False)


def test_config_manager_singleton(tmpdir):
    """Mindless (non-singleton) instantiation throws Exception"""
    args = tests.ArgsMock(workdir=Path(tmpdir))

    with pytest.raises(Exception):
        _ = ConfigManager(args)

    cm = ConfigManager.get_singleton(args)
    assert type(cm) is ConfigManager, "ConfigManager singleton has right type"
    assert cm is ConfigManager.get_singleton(args), "ConfigManager.get_singleton() yields true singleton"

    ConfigManager.reset_singleton()
    assert cm is not ConfigManager.get_singleton(args), "ConfigManager singleton reset works"

    ConfigManager.reset_singleton()


def test_config_manager(config_manager):
    """Checking ConfigManager facility"""

    # Create sample config
    config_manager.set("a", "a_1", "foo")
    config_manager.set("a", "a_2", "bar")
    config_manager.set("b", "b_1", "baz")

    assert config_manager.get("a", "a_1") == "foo", "Config reads back fine"
    assert config_manager.get("a", "a_2") == "bar", "Config reads back fine"
    assert config_manager.get("b", "b_1") == "baz", "Config reads back fine"

    # Unknown sections or options yield None
    assert config_manager.get("a", "a_3") is None, "Unknown option yields None"
    assert config_manager.get("c", "c_1") is None, "Unknown section yields None"

    # Optional fallback
    assert config_manager.get("c", "c_1", fallback="bamm") == "bamm", "Option fall back to default"
    assert config_manager.get("c", "c_1") == "bamm", "First fallback is stored permanently"

    # Overwriting
    config_manager.set("c", "c_1", "bam")
    assert config_manager.get("c", "c_1") == "bam", "Options can be overwritten"


def test_config_manager_persistence(tmpdir):
    args = tests.ArgsMock(workdir=Path(tmpdir))

    cm = ConfigManager(args, singleton_check=False)
    cm.set("foo", "bar", "baz")

    # Create fresh ConfigManager instance which should re-instantiate the old data
    cmm = ConfigManager(args, singleton_check=False)
    assert cmm.get("foo", "bar") == "baz", "Config is ephemeral"
