# xarray-graph
PyQt/PySide UI for visualizing and manipulating Xarray DataTrees.

![GitHub Tag](https://img.shields.io/github/v/tag/marcel-goldschen-ohm/xarray-graph?cacheSeconds=1)
![build-test](https://github.com/marcel-goldschen-ohm/xarray-graph/actions/workflows/build-test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/marcel-goldschen-ohm/xarray-graph?include_prereleases&cacheSeconds=1)
![publish](https://github.com/marcel-goldschen-ohm/xarray-graph/actions/workflows/publish.yml/badge.svg)

## Primary components (apps)
1. [Tree model/view for Xarray DataTree](#tree-modelview-for-xarray-datatree)
2. [Graphing (x,y) slices of a Xarray DataTree](#graphing-xy-slices-of-a-xarray-datatree)

## Contents
- [Install](#install)
- [Run](#run)
- [Documentation](#documentation)

## Install
Requires a PyQt package. Should work with PySide6 (the official Python Qt binding), PyQt6, or PyQt5 via the [QtPy](https://github.com/spyder-ide/qtpy) abstraction layer. *Note: PySide6>=6.2.2 for Apple silicon support, and PySide6!=6.9.1 due to a [bug](https://github.com/pyqtgraph/pyqtgraph/issues/3328) that is incompatible with pyqtgraph.*
```shell
pip install "PySide6>=6.2.2,!=6.9.1"
```
<!-- Install latest release version:
```shell
pip install xarray-graph
```
Or i-->
Install latest development version:
```shell
pip install --upgrade xarray-graph@git+https://github.com/marcel-goldschen-ohm/xarray-graph
```
The above should be all you need, but if necessary you can install the exact same environment as in the repo:
1. Install the python package manager [uv](https://github.com/astral-sh/uv).
2. Download this repo.
3. In the downloaded repo directory, run the following commands:
```shell
uv sync
uv pip install "PySide6>=6.2.2,!=6.9.1"
```

## Run
Launch the GUI:
```shell
xarray-graph
```

## Support
This is all done in my free time. If you find it useful, why not buy me a cup of coffee? Cheers!

<a href="https://www.buymeacoffee.com/marcel.goldschen.ohm" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

## Documentation
:construction:

### Tree model/view for Xarray Datatree
:construction:

### Graphing (x,y) slices of a Xarray Datatree
:construction:
