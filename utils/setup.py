# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from setuptools import setup, find_packages

PACKAGE_NAME = "mozdep"
PACKAGE_VERSION = "0.0.0a3"

INSTALL_REQUIRES = [
    "coloredlogs",
    "ipython",
    "networkx",
    "PyYAML",
    "requests",
    "semantic_version",
    "toml"
]

TESTS_REQUIRE = [
    "coverage",
    "pytest",
    "pytest-bdd"
]


SETUP_REQUIRES = [
    "pytest-runner"
]

DEV_REQUIRES = [
    "coverage",
    "pycodestyle",
    "pytest",
    "pytest-bdd",
    "pytest-codestyle",
    "pytest-runner"
]

setup(
    name=PACKAGE_NAME,
    version=PACKAGE_VERSION,
    description="Dependency Management for Mozilla Central",
    classifiers=[
        "Environment :: Console",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Natural Language :: English",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: Microsoft :: Windows :: Windows 7",
        "Operating System :: Microsoft :: Windows :: Windows 8",
        "Operating System :: Microsoft :: Windows :: Windows 8.1",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing"
    ],
    keywords=["mozilla", "firefox", "product management", "security", "security assurance"],
    author="Christiane Ruetten",
    author_email="cr@mozilla.com",
    url="https://github.com/mozilla/mozilla-depends",
    download_url="https://github.com/mozilla/mozilla-depends/archive/latest.tar.gz",
    license="MPL2",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,  # See MANIFEST.in
    zip_safe=True,
    use_2to3=False,
    install_requires=INSTALL_REQUIRES,
    tests_require=TESTS_REQUIRE,
    setup_requires=SETUP_REQUIRES,
    extras_require={"dev": DEV_REQUIRES},  # For `pip install -e .[dev]`
    entry_points={
        "console_scripts": [
            "mozdep = mozdep.main:main"
        ]
    }
)