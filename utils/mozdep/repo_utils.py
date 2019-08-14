# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from distutils.spawn import find_executable
from os.path import expanduser
from pathlib import Path
from re import compile
from shutil import rmtree
from subprocess import run, PIPE, DEVNULL
from tempfile import mkdtemp
from typing import Iterator, List
import logging

from mozdep.cleanup import CleanUp

logger = logging.getLogger(__name__)

TEST_RE = compile(r".*/(unit|test|tests|mochitest|testing|jsapi-tests|reftests|reftest"
                  r"|crashtests|crashtest|googletest|gtest|gtests|imptests)(/|$)")

tmp_dir = Path(mkdtemp(prefix="mozdep_repo_"))
hg_bin = find_executable("hg.exe") or find_executable("hg")


class RepoError(Exception):
    pass


class RemoveRepoTmpdir(CleanUp):
    @staticmethod
    def at_exit():
        global tmp_dir
        if tmp_dir.exists():
            logger.info("Removing temporary directory at `%s` (may take a long time)", tmp_dir)
            rmtree(tmp_dir)


def clone_repo(dst: Path = tmp_dir, src: Path or str = "https://hg.mozilla.org/mozilla-unified", quiet=True) -> Path:
    global hg_bin
    if hg_bin is None:
        raise RepoError("Unable to find `hg` binary in $PATH")
    if quiet:
        cmd = [str(hg_bin), "clone", "--quiet", "--uncompressed", str(src), str(dst)]
        logger.debug("Running command `%s`", " ".join(cmd))
        result = run(cmd, check=False, stdout=DEVNULL, stderr=PIPE)
    else:
        cmd = [str(hg_bin), "clone", "--noninteractive", "--color", "always", "--time", "--uncompressed",
               str(src), str(dst)]
        logger.debug("Running command `%s`", " ".join(cmd))
        result = run(cmd, check=False)
    if result.returncode != 0:
        logger.error("Command `%s` failed: %s", " ".join(cmd), result.stderr.decode("utf-8"))
        raise RepoError(f"Cloning repo from `{str(src)}` to `{str(dst)}` failed")
    return dst


def update_repo(repo: Path = tmp_dir):
    global hg_bin
    if hg_bin is None:
        raise RepoError("Unable to find `hg` binary in $PATH")
    cmd = [str(hg_bin), "pull", "--update"]
    logger.debug("Running command `%s` in `%s`", " ".join(cmd), str(repo))
    result = run(cmd, check=False, stdout=DEVNULL, stderr=DEVNULL, cwd=str(repo))
    if result.returncode != 0:
        logger.error("Command `%s` failed: %s", " ".join(cmd), result.stderr.decode("utf-8"))
        raise RepoError(f"Updating repo in `{str(repo)}` failed")


def get_mozilla_component(path: Path, tree: Path) -> str or None:
    cmd = [str(tree / "mach"), "file-info", "bugzilla-component", str(path)]
    cmd_output = run(cmd, check=False, stdout=PIPE, stderr=DEVNULL).stdout
    if len(cmd_output) == 0:
        return None
    else:
        return cmd_output.decode("utf-8").split("\n")[0]


def is_test_path(p: str):
    return TEST_RE.match(p) is not None


def guess_repo_path(override: Path or None = None) -> Path or None:
    home_dir = Path(expanduser('~'))
    # TODO: Poll for more guesses
    guesses = [
        home_dir / "mozilla-unified",
        home_dir / "dev" / "mozilla-unified",
        home_dir / "src" / "mozilla-unified",
        Path("../mozilla-unified"),
        Path("../../mozilla-unified"),
        home_dir / "mozilla-central",
        home_dir / "dev" / "mozilla-central",
        home_dir / "src" / "mozilla-central",
        Path("../mozilla-central"),
        Path("../../mozilla-central"),
    ]
    if override is not None:
        guesses = [override]
    for guess in guesses:
        if (guess / "mach").is_file():
            return guess.resolve()
    return None


class HgRepo(object):

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.__source_stamp = None

    def is_repo(self):
        return (self.path / ".hg").is_dir()

    def update(self):
        logger.info("Updating mercurial repo in `%s`", str(self.path))
        update_repo(self.path)

    def find(self, glob: str = "*", relative: bool = False, start: Path = None) -> Iterator[Path]:
        start = start or self.path
        matches = filter(lambda p: p.parents[1] != ".hg", start.rglob(glob))
        for path in matches:
            if relative:
                yield path.relative_to(self.path)
            else:
                yield path

    def run_hg(self, args: List[str], stdout=PIPE, stderr=PIPE):
        global hg_bin
        if hg_bin is None:
            raise RepoError("Unable to find `hg` binary in $PATH")
        cmd = [str(hg_bin)] + args
        logger.debug("Running command `%s` in `%s`", " ".join(cmd), str(self.path))
        cmd_result = run(cmd, cwd=str(self.path), check=False, stdout=stdout, stderr=stderr)
        return cmd_result

    def is_clean(self):
        status_result = self.run_hg(["status"])
        if status_result.returncode != 0:
            logger.error(f"Failed to run `hg status` on {self.path}: %s",
                         repr(status_result.stderr.decode("utf-8")))
            raise RepoError("Error running `hg status`")
        return len(status_result.stdout) == 0

    def cleanup(self, *, purge=True, revert=True):
        if purge:
            purge_result = self.run_hg(["purge"], stdout=DEVNULL, stderr=PIPE)
            if purge_result.returncode != 0:
                logger.error(f"Unable to purge dirty files from {self.path}: %s",
                             repr(purge_result.stderr.decode("utf-8")))
                logger.warning(f"Do you have the `purge` mercurial extension enabled?")
        if revert:
            revert_result = self.run_hg(["revert", "--all"], stdout=DEVNULL, stderr=PIPE)
            if revert_result.returncode != 0:
                logger.error(f"Failed to run `hg revert` on {self.path}: %s",
                             repr(revert_result.stderr.decode("utf-8")))
                raise RepoError("Error running `hg revert`")

    @property
    def source_stamp(self) -> str:
        global hg_bin
        if self.__source_stamp is None:
            cmd = [str(hg_bin), "id", "-r", "tip", "-T", "{rev}:{node}"]
            cmd_output = run(cmd, cwd=str(self.path), check=True, stdout=PIPE, stderr=DEVNULL).stdout
            if len(cmd_output) == 0:
                self.__source_stamp = None
            else:
                self.__source_stamp = cmd_output.decode("utf-8").strip("\n")
        return self.__source_stamp

    @staticmethod
    def is_test_path(path: Path) -> bool:
        return is_test_path(str(path))
