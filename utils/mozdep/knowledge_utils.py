# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from pathlib import Path
from typing import List

from .knowledgegraph import Ns, KnowledgeGraph, Subject, Entity

logger = logging.getLogger(__name__)


def learn_dependency(g: KnowledgeGraph, *,
                     name: str,
                     version: str = "_unknown",
                     version_type: str = "_generic",
                     detector_name: str,
                     language: str,
                     upstream_version: str or None = None,
                     top_path: Path or None = None,
                     top_dependency: Subject or None = None,
                     tree_path: Path or None = None,
                     repository_url: str or None = None,
                     files: List[Path] or None = None,
                     vulnerabilities: list or None = None) -> Subject:

    if top_path is not None:
        rel_top_path = top_path.relative_to(tree_path)
    else:
        rel_top_path = None

    logger.debug(f"Learning about f{language} dependency {name}@{version}")

    # Get existing library node or create one
    try:
        lv = g.V(name).In(Ns().fx.mc.lib.name).Has(Ns().language.name, language).All()[0]
    except IndexError:
        lv = g.new_subject()
        lv.add(Ns().fx.mc.lib.name, name)
        lv.add(Ns().language.name, language)
    if repository_url is not None:
        lv.add(Ns().gh.repo.url, repository_url)
    if upstream_version is not None:
        lv.add(Ns().gh.repo.version, upstream_version)

    try:
        dv = g.V(name).In(Ns().fx.mc.lib.dep.name).Has(Ns().version.spec, version)\
              .Has(Ns().language.name, language).All()[0]
    except IndexError:
        dv = g.new_subject()
        dv.add(Ns().fx.mc.lib.dep.name, name)
        dv.add(Ns().fx.mc.lib, lv)
        dv.add(Ns().language.name, language)
        dv.add(Ns().fx.mc.detector.name, detector_name)
        dv.add(Ns().version.spec, version)
        dv.add(Ns().version.type, version_type)
        if rel_top_path is not None:
            dv.add(Ns().fx.mc.dir.path, str(rel_top_path))
        if top_dependency is not None:
            dv.add(Ns().fx.mc.file.top_dependency, top_dependency)

        # TODO: Consumers should take the following two from lib node
        if repository_url is not None:
            dv.add(Ns().gh.repo.url, repository_url)
        if upstream_version is not None:
            dv.add(Ns().gh.repo.version, upstream_version)

    if files is not None:
        learn_file_set(g, files=files, tree_path=tree_path, belongs_to=dv)

    if vulnerabilities is not None:
        for vulnerability in vulnerabilities:
            learn_vulnerability(g, **vulnerability)

    return dv


def learn_file_set(g: KnowledgeGraph, *,
                   files: List[Path],
                   tree_path: Path,
                   belongs_to: Subject) -> Subject:

    # Create file references
    for f in files:
        rel_path = str(f.relative_to(tree_path))
        logger.debug(f"Adding file reference `%s`", rel_path)
        fv = g.new_subject()
        fv.add(Ns().fx.mc.file.path, rel_path)
        fv.add(Ns().fx.mc.file.part_of, belongs_to)

    return belongs_to


def learn_vulnerability(g: KnowledgeGraph, *,
                        vulnerability_identifier: str,
                        database: str,
                        info_links: list,
                        affects: list,
                        title: str or None = None,
                        description: str or None = None,
                        weakness_identifier: str or None = None,
                        severity: str or None = None) -> Subject:
    try:
        vv = g.V(vulnerability_identifier).In(Ns().vuln.id).All()[0]
        logger.debug("Updating existing vulnerability node for %s", vulnerability_identifier)
    except IndexError:
        logger.debug("Creating new vulnerability node for %s", vulnerability_identifier)
        vv = g.new_subject()
        vv.add(Ns().vuln.id, vulnerability_identifier)
        vv.add(Ns().vuln.database, database)
    if title is not None:
        vv.add(Ns().vuln.title, title)
    if description is not None:
        vv.add(Ns().vuln.description, description)
    if weakness_identifier is not None:
        vv.add(Ns().vuln.weakness_id, weakness_identifier)
    if severity is not None:
        vv.add(Ns().vuln.severity, severity)
    vv.add(Ns().vuln.info_link, ";".join(info_links))
    for dep in affects:
        vv.add(Ns().vuln.affects, dep)

    return vv


def recall_dependencies(g: KnowledgeGraph, *, language: str, name: str, version: str) -> List[Entity]:
    return list(g.V(name).In(Ns().fx.mc.lib.dep.name).Has(Ns().version.spec, version)
                .Has(Ns().language.name, language).All())


def enumerate_dependencies(g: KnowledgeGraph):
    for d in g.V().In(Ns().fx.mc.lib.dep.name).All():
        # dependency_name = d.
        yield d
