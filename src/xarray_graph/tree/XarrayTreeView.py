""" Tree view of a XarrayTreeModel with context menu and mouse wheel expand/collapse.
"""

from __future__ import annotations
from typing import Callable
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from pyqt_ext.tree import AbstractTreeItem, TreeView, KeyValueTreeItem, KeyValueTreeModel, KeyValueTreeView
from xarray_graph.tree import XarrayTreeModel


class XarrayTreeView(TreeView):

    sigFinishedEditingAttrs = Signal()

    def __init__(self, parent: QObject = None) -> None:
        TreeView.__init__(self, parent)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # optionally show vars and coords
        self._showVarsAction = QAction('Show Variables')
        self._showVarsAction.setCheckable(True)
        self._showVarsAction.setChecked(True)
        self._showVarsAction.triggered.connect(self.refresh)

        self._showCoordsAction = QAction('Show Coordinates')
        self._showCoordsAction.setCheckable(True)
        self._showCoordsAction.setChecked(True)
        self._showCoordsAction.triggered.connect(self.refresh)

        # optional details column
        self._showDetailsColumnAction = QAction('Show Details Column')
        self._showDetailsColumnAction.setCheckable(True)
        self._showDetailsColumnAction.setChecked(False)
        self._showDetailsColumnAction.triggered.connect(self.refresh)

        # these will appear in the item's context menu
        self._itemContextMenuFunctions: list[tuple[str, Callable[[AbstractTreeItem]]]] = [
            ('Info', lambda item, self=self: self.popupItemInfo(item)),
            ('Attrs', lambda item, self=self: self.editItemAttrs(item)),
            ('Separator', None),
            ('Remove', lambda item, self=self: self.askToRemoveItem(item)),
        ]
    
    def setDataTree(self, dt: xr.DataTree):
        show_vars = self._showVarsAction.isChecked()
        show_coords = self._showCoordsAction.isChecked()
        show_details = self._showDetailsColumnAction.isChecked()
        model: XarrayTreeModel = self.model()
        if model is None:
            model = XarrayTreeModel()
            TreeView.setModel(self, model)
        self.storeState()
        model.setDataTree(dt, include_vars=show_vars, include_coords=show_coords)
        model.setDetailsColumnVisible(show_details)
        self.restoreState()
    
    def refresh(self):
        model: XarrayTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree | None = model.dataTree()
        if dt is None:
            return
        self.setDataTree(dt)
    
    def setModel(self, model: XarrayTreeModel):
        TreeView.setModel(self, model)
        self.refresh()
    
    def contextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        menu: QMenu = TreeView.contextMenu(self, index)

        menu.addSeparator()
        menu.addAction(self._showVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showDetailsColumnAction)
        menu.addSeparator()
        menu.addAction('Refresh', self.refresh)

        return menu
    
    def popupItemInfo(self, item: AbstractTreeItem):
        model: XarrayTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree | None = model.dataTree()
        if dt is None:
            return
        path: str = model.pathFromItem(item)
        obj = dt[path]
        text = str(obj)
        
        textEdit = QTextEdit()
        textEdit.setPlainText(text)
        textEdit.setReadOnly(True)

        dlg = QDialog(self)
        dlg.setWindowTitle(item.path)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(textEdit)
        dlg.exec()
    
    def editItemAttrs(self, item: AbstractTreeItem):
        model: XarrayTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree | None = model.dataTree()
        if dt is None:
            return
        path: str = model.pathFromItem(item)
        obj = dt[path]
        attrs = obj.attrs.copy()
        
        root = KeyValueTreeItem('/', attrs)
        kvmodel = KeyValueTreeModel(root)
        view = KeyValueTreeView()
        view.setModel(kvmodel)
        view.expandAll()
        view.resizeAllColumnsToContents()

        dlg = QDialog(self)
        dlg.setWindowTitle(item.path)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setMinimumSize(QSize(400, 400))
        if dlg.exec() != QDialog.Accepted:
            return
        
        attrs = kvmodel.root().value
        obj.attrs = attrs
        
        self.sigFinishedEditingAttrs.emit()
    
    def isVariablesVisible(self) -> bool:
        return self._showVarsAction.isChecked()
    
    def setVariablesVisible(self, visible: bool):
        self._showVarsAction.setChecked(visible)
        self.refresh()
    
    def isCoordinatesVisible(self) -> bool:
        return self._showCoordsAction.isChecked()
    
    def setCoordinatesVisible(self, visible: bool):
        self._showCoordsAction.setChecked(visible)
        self.refresh()


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

    model = XarrayDndTreeModel(dt=dt)
    view = XarrayTreeView()
    view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    view.setModel(model)
    view.show()
    view.resize(QSize(600, 600))
    view.expandAll()
    view.resizeAllColumnsToContents()

    app.exec()
    print(dt)
    print(dt.children)


if __name__ == '__main__':
    test_live()
