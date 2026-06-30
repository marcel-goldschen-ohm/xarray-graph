# xarray-graph
PyQt/PySide UIs for visualizing and manipulating Xarray DataTrees.

![GitHub Tag](https://img.shields.io/github/v/tag/marcel-goldschen-ohm/xarray-graph?cacheSeconds=1)
![build-test](https://github.com/marcel-goldschen-ohm/xarray-graph/actions/workflows/build-test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/marcel-goldschen-ohm/xarray-graph?include_prereleases&cacheSeconds=1)
![publish](https://github.com/marcel-goldschen-ohm/xarray-graph/actions/workflows/publish.yml/badge.svg)

:construction: YouTube videos for tree and graph apps

## Contents
- [Install](#install)
    - [Install with uv](#install-with-uv-recommended) &larr; Recommended!
    - [Install with pip](#install-with-pip)
- Apps
    - [XarrayDataTreeViewer](#xarraydatatreeviewer): Tree UI for an Xarray DataTree.
    - [XarrayGraph](#xarraygraph): Graph/Iterate/Fit/Analyze (x,y) slices of DataArrays in an Xarray DataTree.
- [Using Xarray DataTree model/view components in your own app](#using-xarray-datatree-modelview-components-in-your-own-app)
- [Support](#support)

## Install
To simply use the apps, I recommend following the instructions for [installing with uv](#install-with-uv-recommended).

Requires a PyQt package. Should work with PySide6 (the official Python Qt binding), PyQt6, or PyQt5 via the [QtPy](https://github.com/spyder-ide/qtpy) abstraction layer. *Note: PySide6>=6.2.2 for Apple silicon support, and PySide6!=6.9.1 due to a [bug](https://github.com/pyqtgraph/pyqtgraph/issues/3328) that is incompatible with pyqtgraph.*

## Install with uv (recommended)
1. Install the python package manager [uv](https://github.com/astral-sh/uv).
2. Download the [xarray-graph GitHub repository](https://github.com/marcel-goldschen-ohm/xarray-graph). *I suggest downloading the latest release version*.
3. In the downloaded repo directory, run the following commands (e.g., in a Terminal or shell):
```shell
uv sync
uv pip install "PySide6>=6.2.2,!=6.9.1"
```

[&uarr; top](#xarray-graph)

## Install with pip
Ignore if you [installed with uv](#install-with-uv-recommended).

Install a PyQt package:
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

[&uarr; top](#xarray-graph)

## XarrayDataTreeViewer
Tree UI for an Xarray DataTree.

**Launch the app** *(If you installed with uv, run in the xarray-graph directory. If you installed with pip, omit `uv run`.)*:
```shell
uv run xarray-tree
```

:construction: YouTube video

[&uarr; top](#xarray-graph)

## XarrayGraph
Graph/Iterate/Fit/Analyze (x,y) slices of DataArrays in an Xarray DataTree.

**Launch the app** *(If you installed with uv, run in the xarray-graph directory. If you installed with pip, omit `uv run`.)*:
```shell
uv run xarray-graph
```

:construction: YouTube video

[&uarr; top](#xarray-graph)

## Using Xarray DataTree model/view components in your own app
```python
import xarray as xr
from xarray_graph.tree import XarrayDataTreeModel, XarrayDataTreeView

dt = xr.DataTree(...)

model = XarrayDataTreeModel()
model.setDatatree(dt)

view = XarrayDataTreeView()
view.setModel(model)

# place view widget in your app as desired
```

[&uarr; top](#xarray-graph)

## Support
This is all done in my free time. If you find it useful, why not buy me a cup of coffee? Cheers!

<a href="https://www.buymeacoffee.com/marcel.goldschen.ohm" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

[&uarr; top](#xarray-graph)