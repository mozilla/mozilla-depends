# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from logging import getLogger
from pathlib import Path
from typing import List

from . import basedetector
from . import mozyaml
from . import python
from . import retirejs
from . import rust
from . import thirdpartyalert
from . import thirdpartypaths
from ..knowledgegraph import KnowledgeGraph

logger = getLogger(__name__)


def __subclasses_of(cls):
    sub_classes = cls.__subclasses__()
    sub_sub_classes = []
    for sub_cls in sub_classes:
        sub_sub_classes += __subclasses_of(sub_cls)
    return sub_classes + sub_sub_classes


__all__ = ["run", "run_all", "all_detectors"]

# Keep a record of all DependencyDetector subclasses
all_detectors = dict([(detector.name(), detector) for detector in __subclasses_of(basedetector.DependencyDetector)])
# all_detector_names = sorted(list(all_detectors.keys()))


def run(detector: str, tree: Path, graph: KnowledgeGraph) -> bool:
    global logger

    try:
        current_detector = all_detectors[detector](tree, graph)
    except KeyError:
        logger.critical(f"Unknown detector `{detector}`")
        raise Exception("まさか！")

    logger.debug(f"Running `{detector}` .setup()")
    if not current_detector.setup():
        logger.error(f"Detector `{detector}` .setup() failed")
        return False

    logger.debug(f"Running `{detector}` .run()")
    current_detector.run()
    logger.debug(f"Running `{detector}` .teardown()")
    current_detector.teardown()
    logger.debug(f"Detector `{detector}` finished")

    return True


def run_all(tree: Path, graph: KnowledgeGraph, *, choice: List[str] or None = None) -> bool:

    sorted_detectors = list(all_detectors.values())
    sorted_detectors.sort(key=lambda x: x.priority(), reverse=True)
    sorted_detector_names = [d.name() for d in sorted_detectors]

    if choice is None or len(choice) == 0:
        choice = sorted_detector_names
    for detector_name in choice:
        if detector_name not in sorted_detector_names:
            logger.error(f"Ignoring unknown detector {detector_name}")

    ret = True
    for detector in sorted_detectors:
        if detector.name() not in choice:
            logger.warning(f"Not running detector {detector.name()}")
            continue
        ret = run(detector.name(), tree, graph)
        if not ret:
            logger.critical(f"Detector `{detector.name}` failed. Aborting")
            break

    return ret
