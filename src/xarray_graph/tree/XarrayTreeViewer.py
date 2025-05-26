""" Tree viewer with a XarrayTreeView and Info/Attrs tabs for selected items.
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from pyqt_ext.tree import AbstractTreeItem, KeyValueTreeItem, KeyValueTreeModel, KeyValueTreeView
from xarray_graph.tree import XarrayTreeModel, XarrayTreeView


class XarrayTreeViewer(QSplitter):

    def __init__(self, parent: QObject = None) -> None:
        QSplitter.__init__(self, Qt.Orientation.Vertical, parent)

        self._data_view = XarrayTreeView()
        self._data_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        model = XarrayTreeModel()
        model.setDetailsColumnVisible(False)
        self._data_view.setModel(model)

        self._info_view = QTextEdit()
        self._info_view.setReadOnly(True)

        self._attrs_view = KeyValueTreeView()
        self._attrs_view.setAlternatingRowColors(True)
        self._attrs_view.setModel(KeyValueTreeModel())

        self.metadata_tabs = QTabWidget()
        self.metadata_tabs.addTab(self._info_view, "Info")
        self.metadata_tabs.addTab(self._attrs_view, "Attrs")

        self.addWidget(self._data_view)
        self.addWidget(self.metadata_tabs)

        self._data_view.selectionWasChanged.connect(self._on_selection_changed)
        self._data_view.sigFinishedEditingAttrs.connect(self._on_selection_changed)
    
    def view(self) -> XarrayTreeView:
        return self._data_view
    
    def _on_selection_changed(self) -> None:
        selected_items = self._data_view.selectedItems()
        model: XarrayTreeModel = self._data_view.model()
        dt: DataTree = model.dataTree()
        if (model is None) or (dt is None) or len(selected_items) > 1:
            # clear tabs
            self._info_view.clear()
            self._attrs_view.setModel(None)
            return
        
        # single selected item
        if len(selected_items) == 0:
            item: AbstractTreeItem = self._data_view.model().root()
        elif len(selected_items) == 1:
            item: AbstractTreeItem = selected_items[0]

        path: str = model.pathFromItem(item)
        obj: DataTree | xr.DataArray = dt[path]
        if isinstance(obj, xr.DataTree):
            text = str(obj.dataset)
            attrs = obj.attrs
        elif isinstance(obj, xr.DataArray):
            text = str(obj)
            attrs = obj.attrs
        else:
            text = ''
            attrs = None
        
        self._info_view.setPlainText(text)
        if self._attrs_view.model() is None:
            self._attrs_view.setModel(KeyValueTreeModel())
        self._attrs_view.model().setRoot(KeyValueTreeItem(None, attrs))


def test_live():
    import numpy as np
    from xarray_graph.tree import XarrayDndTreeModel
    app = QApplication()

    raw_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, 100) * 1e-9, {'units': 'A'}),
            'voltage': (['series', 'sweep', 'time'], np.random.rand(3, 10, 100) * 10000, {'units': 'V'}),
        },
        coords={
            'time': ('time', np.arange(100) * 0.01, {'units': 's'}),
        },
    )
    # print('-----\n raw_ds', raw_ds)

    baselined_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, 100) * 1e-9, {'units': 'A'}),
        },
    )
    # print('-----\n baselined_ds', baselined_ds)

    # scaled_ds = xr.Dataset(
    #     data_vars={
    #         'current': (['series', 'sweep', 'time'], np.random.rand(1, 2, 100) * 1e-9, {'units': 'A'}),
    #     },
    #     coords={
    #         'series': ('series', [1]),
    #         'sweep': ('sweep', [5,8]),
    #     },
    # )
    # print('-----\n scaled_ds', scaled_ds)
    
    dt = xr.DataTree(name='root')
    dt['raw'] = raw_ds
    dt['raw/baselined'] = baselined_ds
    # dt['raw/baselined/scaled'] = scaled_ds
    # print('-----\n', root_node.to_datatree())
    
    viewer = XarrayTreeViewer()
    view = viewer.view()
    model = XarrayDndTreeModel(dt=dt)
    view.setModel(model)
    viewer.show()
    viewer.resize(QSize(400, 600))
    viewer.setSizes([300, 300])
    view.expandAll()
    view.resizeAllColumnsToContents()

    app.exec()


if __name__ == '__main__':
    test_live()