# mozilla-depends

## Requirements
* _Node_ v9 or later
* `npm` available in `$PATH`
* `pipenv` with python 3.7

## Installation


* ```hg clone --uncompressed https://hg.mozilla.org/mozilla-unified```
* ```git clone git@github.com:mozilla/mozilla-depends.git```
* ```cd mozilla-depends/utils/```
* ```pipenv install -e .[dev]```
* ```npm install .```

## Usage

```mozdep``` *must* be run from the _utils_ directory for finding retire binary.
It tries to be smart about finding the local mozilla-central tree.
If it is not smart enough, pass it ```--tree```.

* ```pipenv run pytest -v```
* ```pipenv run mozdep --tree ../../mozilla-unified/ --debug detect -c /tmp/out.csv```
