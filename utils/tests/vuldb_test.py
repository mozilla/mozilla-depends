# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
from os.path import expanduser
from pathlib import Path
import pytest

import tests
from mozdep.config import ConfigManager
from mozdep.detectors.vuldb import VulDBClient

logger = getLogger(__name__)


@pytest.fixture(name="vuldb_client")
def fixture_vuldb_client():
    args = tests.ArgsMock(workdir=Path(expanduser("~/.mozdep")))
    yield VulDBClient(args, singleton_check=False)

    # VulDBClient uses ConfigManager singleton which must be
    # reset after use to not persist state.
    ConfigManager.reset_singleton()


def test_vuldb_client(vuldb_client):
    assert vuldb_client.is_authenticated()
    vuldb_client.set_token("")
    r = vuldb_client.post()
    assert "request" in r and "response" in r
    assert r["response"]["version"].startswith("3."), "Expected VulDB API version"
    assert r["response"]["status"] == "401", "VulDB API reports unauthenticated request"
