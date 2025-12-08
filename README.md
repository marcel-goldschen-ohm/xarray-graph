# xarray-graph
PyQt/PySide UIs for visualizing and manipulating Xarray DataTrees.

![GitHub Tag](https://img.shields.io/github/v/tag/marcel-goldschen-ohm/xarray-graph?cacheSeconds=1)
![build-test](https://github.com/marcel-goldschen-ohm/xarray-graph/actions/workflows/build-test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/marcel-goldschen-ohm/xarray-graph?include_prereleases&cacheSeconds=1)
![publish](https://github.com/marcel-goldschen-ohm/xarray-graph/actions/workflows/publish.yml/badge.svg)

# :construction: Under construction! Check back soon.

- YouTube video(s)?

## Contents
- [Tree GUI for Xarray DataTree](#tree-gui-for-xarray-datatree)
- [Using DataTree model/view components in your own app](#using-datatree-modelview-components-in-your-own-app)
- [Graph (x,y) slices of a Xarray DataTree](#graph-xy-slices-of-a-xarray-datatree)
- [Install](#install)
- [Run](#run)
- [Support](#support)

## Tree GUI for Xarray Datatree
A graphical user interface for visualizing and manipulating Xarray DataTrees.

- :construction: YouTube video?

Launch the tree GUI by running the command:
```shell
xarray-tree
```

[&uarr; top](#xarray-graph)

## Using DataTree model/view components in your own app
```python
import xarray as xr
from xarray_graph import XarrayDataTreeModel, XarrayDataTreeView

dt = xr.DataTree(...)

model = XarrayDataTreeModel()
model.setDataVarsVisible(True)
model.setCoordsVisible(False)
model.setInheritedCoordsVisible(False)
model.setDetailsColumnVisible(True)
model.setDatatree(dt)

view = XarrayDataTreeView()
view.setModel(model)
```

[&uarr; top](#xarray-graph)

## Graph (x,y) slices of a Xarray Datatree
A graphical user interface for visualizing (x,y) slices (i.e., signal waveforms) of selected Xarray DataArrays in a DataTree.

- :construction: YouTube video?

Launch the graph GUI by running the command:
```shell
xarray-graph
```

[&uarr; top](#xarray-graph)

## Install
If you are unfamiliar with Python environments, I suggest following the instructions at the end of this section involving the python package manager [uv](https://github.com/astral-sh/uv).

Requires a PyQt package. Should work with PySide6 (the official Python Qt binding), PyQt6, or PyQt5 via the [QtPy](https://github.com/spyder-ide/qtpy) abstraction layer. *Note: PySide6>=6.2.2 for Apple silicon support, and PySide6!=6.9.1 due to a [bug](https://github.com/pyqtgraph/pyqtgraph/issues/3328) that is incompatible with pyqtgraph.*
```shell
pip install "PySide6>=6.2.2,!=6.9.1"
```
Install latest release version:
```shell
pip install --upgrade xarray-graph
```
Or install latest development version:
```shell
pip install --upgrade xarray-graph@git+https://github.com/marcel-goldschen-ohm/xarray-graph
```
The above should be all you need, but if necessary you can install the exact same environment as in the repo:
1. Install the python package manager [uv](https://github.com/astral-sh/uv).
2. Download this repo *(I suggest downloading the latest release version)*.
3. In the downloaded repo directory, run the following commands:
```shell
uv sync
uv pip install "PySide6>=6.2.2,!=6.9.1"
```
Note that if you install with [uv](https://github.com/astral-sh/uv), the commands for launching the GUIs will need to be run within the downloaded repo directory and also preceeded by `uv run`. For example, to launch the tree GUI:
```shell
uv run xarray-tree
```

[&uarr; top](#xarray-graph)

## Run
Launch the tree GUI:
```shell
xarray-tree
```

Launch the graph GUI:
```shell
xarray-graph
```

[&uarr; top](#xarray-graph)

## Support
This is all done in my free time. If you find it useful, why not buy me a cup of coffee? Cheers!

<a href="https://www.buymeacoffee.com/marcel.goldschen.ohm" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

[&uarr; top](#xarray-graph)