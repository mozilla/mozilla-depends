#!/usr/bin/env python3
# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import coloredlogs
import logging
from os.path import split
import pkg_resources
from pathlib import Path
import sys
from time import gmtime

from . import cleanup
from . import command
from .repo_utils import guess_repo_path, clone_repo, HgRepo

# Initialize coloredlogs
logging.Formatter.converter = gmtime
logger = logging.getLogger(__name__)
coloredlogs.DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s"
coloredlogs.install(level="INFO")

tmp_dir = None
module_dir = None


def parse_args(argv=None):
    """
    Argument parsing. Parses from sys.argv if argv is None.
    :param argv: argument vector to parse
    :return: parsed arguments
    """
    if argv is None:
        argv = sys.argv[1:]

    pkg_version = pkg_resources.require("mozdep")[0].version

    # Set up the parent parser with shared arguments
    parser = argparse.ArgumentParser(prog="mozdep")
    parser.add_argument("--version", action="version", version="%(prog)s " + pkg_version)
    parser.add_argument("-d", "--debug",
                        help="enable debug",
                        action="store_true")
    parser.add_argument("-r", "--repo",
                        help="path to mozilla-central/unified mercurial repo",
                        type=Path,
                        action="store")
    parser.add_argument("-c", "--clone",
                        help="clone mozilla-unified repo if required",
                        action="store_true")
    parser.add_argument("--cleanup",
                        help="purge and revert the mercurial repo if required",
                        action="store_true")
    parser.add_argument("-u", "--update",
                        help="pull update from upstream mercurial repo",
                        action="store_true")

    # Set up subparsers, one for each subcommand
    subparsers = parser.add_subparsers(help="Subcommand", dest="command")
    for command_name in command.all_commands:
        command_class = command.all_commands[command_name]
        sub_parser = subparsers.add_parser(command_name, help=command_class.help)
        command_class.setup_args(sub_parser)

    return parser.parse_args(argv)


# This is the entry point used in setup.py
def main(argv=None):
    global logger, tmp_dir, module_dir

    module_dir = split(__file__)[0]
    cleanup.init()

    # Check if we were run by "python -m mozdep".
    # Correct for argparse not handling it well.
    if argv and len(argv) > 1 and "__main__" in argv[0]:
        argv = argv[1:]
    args = parse_args(argv)

    if args.debug:
        coloredlogs.install(level='DEBUG')

    logger.debug("Command arguments: %s" % args)

    if args.repo is None:
        logger.info("No repo path given, looking for likely candidate...")
        repo_path = guess_repo_path()
        if repo_path is None:
            logger.critical("Unable to detect mozilla-unified repo. Please specify --repo path")
            return 20
    else:
        repo_path = args.repo.resolve()
        if not repo_path.is_dir():
            if args.clone:
                logger.info("Cloning mozilla-unified repo to `%s`. This will take a long time...", repo_path)
                try:
                    clone_repo(repo_path, quiet=False)
                except KeyboardInterrupt:
                    logger.critical("\nUser interrupt. Quitting...")
                    return 10
            else:
                logger.critical("No mozilla-unified mercurial repo at `%s`. Would you like to --clone one there?",
                                repo_path)
                return 21

    hg = HgRepo(repo_path)
    if not hg.is_repo():
        logger.critical("Not a mercurial repo at `%s`", hg.path)
        return 22

    logger.info("Using mercurial repo at `%s`", str(hg.path))
    if not hg.is_clean():
        if args.cleanup:
            logger.warning("Purging and reverting dirty repo as requested")
            hg.cleanup()
        else:
            logger.critical("Mercurial repo is dirty. Want a --cleanup?")
            return 23
    else:
        logger.info("Repo is clean")

    if args.update:
        logger.info("Updating repo as requested")
        hg.update()

    args.repo = hg.path

    # Execute the specified command
    try:
        result = command.run(args, tmp_dir)

    except KeyboardInterrupt:
        logger.critical("\nUser interrupt. Quitting...")
        result = 10

    if not hg.is_clean():
        logger.info("Reverting changes to repo")
        hg.cleanup()

    return result


if __name__ == "__main__":
    sys.exit(main(sys.argv))
