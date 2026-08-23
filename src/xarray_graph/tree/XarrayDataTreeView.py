""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- slice dims for 3d or higher dim array in editable table?
- merge items?
"""
from __future__ import annotations

import numpy as np
import xarray as xr
from qtpy.QtCore import Qt, QModelIndex, QPoint, QSize
from qtpy.QtGui import QIcon, QKeySequence, QKeyEvent
from qtpy.QtWidgets import QWidget, QMenu, QDialog, QTextEdit
from xarray_graph.tree.TreeView import TreeView
from xarray_graph.tree.XarrayDataTreeItem import XarrayDataTreeItem
from xarray_graph.tree.XarrayDataTreeModel import XarrayDataTreeModel


class XarrayDataTreeView(TreeView):

    # finishedEditingAttrs = Signal(XarrayDataTreeItem)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # icons
        import qtawesome as qta
        self._node_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')
        self._index_coord_icon: QIcon = qta.icon('ph.asterisk-thin')
        self._unknown_icon: QIcon = qta.icon('fa6s.question')

        # self._info_shortcut = QShortcut(QKeySequence.StandardKey.Italic, self)
        # self._info_shortcut.activated.connect(lambda: self.infoDialog())

        # actions
        from qtpy.QtGui import QAction  # type: ignore
        self._showDataVarsAction = QAction(
            text = 'Show Variables',
            icon = self._data_var_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide data_vars in the tree view.'
        )
        self._showDataVarsAction.triggered.connect(lambda checked: self._updateModelFromViewOptions())

        self._showCoordsAction = QAction(
            text = 'Show Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide coords in the tree view.'
        )
        self._showCoordsAction.triggered.connect(lambda checked: self._updateModelFromViewOptions())

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide inherited coords in the tree view.'
        )
        self._showInheritedCoordsAction.triggered.connect(lambda checked: self._updateModelFromViewOptions())

        self._showInfoColumnsAction = QAction(
            text = 'Show Dimensions && Units',
            icon = qta.icon('fa6s.info'),
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show dimensions and units columns in the tree view. Uncheck to hide columns.'
        )
        self._showInfoColumnsAction.triggered.connect(lambda checked: self._updateModelFromViewOptions())
    
    def setModel(self, model: XarrayDataTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        super().setModel(model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        
        self._showDataVarsAction.blockSignals(True)
        self._showDataVarsAction.setChecked(model.isDataVarsVisible())
        self._showDataVarsAction.blockSignals(False)
        
        self._showCoordsAction.blockSignals(True)
        self._showCoordsAction.setChecked(model.isCoordsVisible())
        self._showCoordsAction.blockSignals(False)
        
        self._showInheritedCoordsAction.blockSignals(True)
        self._showInheritedCoordsAction.setChecked(model.isInheritedCoordsVisible())
        self._showInheritedCoordsAction.blockSignals(False)
        
        self._showInfoColumnsAction.blockSignals(True)
        self._showInfoColumnsAction.setChecked(model.isInfoColumnsVisible())
        self._showInfoColumnsAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        
        self.storeViewState()
        model.setDataVarsVisible(self._showDataVarsAction.isChecked())
        model.setCoordsVisible(self._showCoordsAction.isChecked())
        model.setInheritedCoordsVisible(self._showInheritedCoordsAction.isChecked())
        model.setInfoColumnsVisible(self._showInfoColumnsAction.isChecked())
        self.restoreViewState()
    
    def treeData(self) -> xr.DataTree:
        model = self.model()
        assert isinstance(model, XarrayDataTreeModel)
        return model.treeData()
    
    def setTreeData(self, data: xr.DataTree) -> None:
        model = self.model()
        if model is None:
            model = XarrayDataTreeModel()
            model.setTreeData(data)
            self.setModel(model)
        elif isinstance(model, XarrayDataTreeModel):
            self.storeViewState()
            model.setTreeData(data)
            self.restoreViewState()
    
    def isDataVarsVisible(self) -> bool:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        return model.isDataVarsVisible()
    
    def setDataVarsVisible(self, visible: bool) -> None:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        model.setDataVarsVisible(visible)
        from qtpy.QtCore import QSignalBlocker
        with QSignalBlocker(self._showDataVarsAction):
            self._showDataVarsAction.setChecked(visible)
    
    def isCoordsVisible(self) -> bool:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        return model.isCoordsVisible()
    
    def setCoordsVisible(self, visible: bool) -> None:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        model.setCoordsVisible(visible)
        from qtpy.QtCore import QSignalBlocker
        with QSignalBlocker(self._showCoordsAction):
            self._showCoordsAction.setChecked(visible)
    
    def isInheritedCoordsVisible(self) -> bool:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        return model.isInheritedCoordsVisible()
    
    def setInheritedCoordsVisible(self, visible: bool) -> None:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        model.setInheritedCoordsVisible(visible)
        from qtpy.QtCore import QSignalBlocker
        with QSignalBlocker(self._showInheritedCoordsAction):
            self._showInheritedCoordsAction.setChecked(visible)
    
    def isInfoColumnsVisible(self) -> bool:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        return model.isInfoColumnsVisible()
    
    def setInfoColumnsVisible(self, visible: bool) -> None:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')
        model.setInfoColumnsVisible(visible)
        from qtpy.QtCore import QSignalBlocker
        with QSignalBlocker(self._showInfoColumnsAction):
            self._showInfoColumnsAction.setChecked(visible)

    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            raise TypeError(f'Model is not a XarrayDataTreeModel: {type(model)}')

        menu = QMenu(self)

        # item that was clicked on
        item = model.itemFromIndex(index)
        assert isinstance(item, XarrayDataTreeItem)
        if item.isNode():
            icon: QIcon = self._node_icon
        elif item.isDataVar():
            icon: QIcon = self._data_var_icon
        elif item.isCoord():
            icon: QIcon = self._coord_icon
        else:
            # should never happen
            icon: QIcon = self._unknown_icon
        
        from qtpy.QtGui import QAction  # type: ignore
        from qtpy.QtWidgets import QAbstractItemView
        
        # disabled action acts as a label for the item that was right-clicked on
        menu.addAction(QAction(
            text=f'{item.path()}:',
            parent=menu,
            icon=icon,
            iconVisibleInMenu=True,
            enabled=False
        ))

        # item-specific actions
        action = QAction(
            text='Info',
            parent=menu,
            shortcut=QKeySequence('Ctrl+I'),
            shortcutVisibleInContextMenu=True
        )
        action.triggered.connect(lambda checked, item=item: self.infoDialog(item))
        menu.addAction(action)

        if not item.isInheritedCoord():
            action = QAction(
                text='Attrs',
                parent=menu
            )
            action.triggered.connect(lambda checked, item=item: self.attrsDialog(item))
            menu.addAction(action)

            if item.isVariable():
                values = item.data().values
                assert isinstance(values, np.ndarray)
                ndim = values.squeeze().ndim
                action = QAction(
                    text='Data',
                    parent=menu,
                    enabled=item.isCoord() or (item.isDataVar() and ndim == 1)
                )
                action.triggered.connect(lambda checked, item=item: self.dataDialog(item))
                menu.addAction(action)

            if item.isNode():
                action = QAction(
                    text='Rename Dimensions',
                    parent=menu
                )
                action.triggered.connect(lambda checked, item=item: self.renameDimensions(item))
                menu.addAction(action)

                action = QAction(
                    text='New Child Node',
                    parent=menu
                )
                action.triggered.connect(lambda checked, parent_item=item: self.insertNewChildNode(parent_item))
                menu.addAction(action)

                action = QAction(
                    text='New Data Variable',
                    parent=menu
                )
                action.triggered.connect(lambda checked, parent_item=item: self.insertNewDataVar(parent_item))
                menu.addAction(action)

                action = QAction(
                    text='New Coordinate',
                    parent=menu
                )
                action.triggered.connect(lambda checked, parent_item=item: self.insertNewCoord(parent_item))
                menu.addAction(action)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        self._clearSelectionAction.setEnabled(has_selection)
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = self.hasCopy()
        self._cutSelectionAction.setEnabled(has_selection)
        self._copySelectionAction.setEnabled(has_selection)
        self._pasteAction.setEnabled(has_copy)
        menu.addSeparator()
        menu.addAction(self._cutSelectionAction)
        menu.addAction(self._copySelectionAction)
        menu.addAction(self._pasteAction)

        # remove item(s)
        self._removeSelectedAction.setEnabled(has_selection)
        menu.addSeparator()
        menu.addAction(self._removeSelectedAction)
        
        # combine items
        has_multi_selection: bool = has_selection and len(self.selectedIndexes()) > 1
        is_multi_nodes_selected: bool = has_multi_selection and len([item for item in self.selectedItems() if isinstance(item, XarrayDataTreeItem) and item.isNode()]) > 1
        menu.addSeparator()

        action = QAction(
            text='Merge Selected Nodes (TODO)',
            parent=menu,
            enabled=False #is_multi_nodes_selected
        )
        action.triggered.connect(lambda checked: self.mergeSelectedNodes())
        menu.addAction(action)

        action = QAction(
            text='Concatenate Selected Nodes',
            parent=menu,
            enabled=is_multi_nodes_selected
        )
        action.triggered.connect(lambda checked: self.concatenateSelectedNodes())
        menu.addAction(action)

        action = QAction(
            text='Insert New Root Node',
            parent=menu
        )
        action.triggered.connect(lambda checked: self.insertNewRootNode())
        menu.addAction(action)
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._viewAllAction)

        # options
        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showInheritedCoordsAction)
        menu.addAction(self._showInfoColumnsAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def infoDialog(self, items: XarrayDataTreeItem | list[XarrayDataTreeItem] = None, font_size: int = None) -> None:
        if isinstance(items, XarrayDataTreeItem):
            item = items
            data = item.data()
            title = item.path()
        elif items is None:
            items_ = self.selectedItems()
            if not items_:
                return
            # ensure items are in tree order
            from xarray_graph.tree.AbstractTreeItem import AbstractTreeItem
            items_ = AbstractTreeItem.orderedItems(items_)
            data = [item.data() for item in items_ if isinstance(item, XarrayDataTreeItem)]
            title = 'Selected'
        elif len(items) == 1:
            item = items[0]
            data = item.data()
            title = item.path()
        else:
            data = [item.data() for item in items]
            title = None
        infoDialog(data, parent=self, size=self._dialogSizeHint(), pos=QPoint(0, 0), title=title, font_size=font_size)
        
    def attrsDialog(self, item: XarrayDataTreeItem) -> None:
        data = item.data()
        title = item.path()
        status = attrsDialog(data, parent=self, size=self._dialogSizeHint(), pos=QPoint(0, 0), title=title)
        if status != QDialog.DialogCode.Accepted:
            return
        # self.finishedEditingAttrs.emit(item)
        self.refresh()
        
    def dataDialog(self, item: XarrayDataTreeItem) -> None:
        if not item.isVariable():
            return
        values = item.data().values
        assert isinstance(values, np.ndarray)
        values = values.squeeze()

        from xarray_graph.table.ArrayTableModel import ArrayTableModel
        from xarray_graph.table.ArrayTableView import ArrayTableView
        model: ArrayTableModel = ArrayTableModel(values)
        view: ArrayTableView = ArrayTableView()
        view.setModel(model)

        from qtpy.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

        dlg = makeDialog(self, size=self._dialogSizeHint(), pos=QPoint(0, 0), title=item.name())
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        status = dlg.exec()
        if status != QDialog.DialogCode.Accepted:
            return
        
        item.data().data[:] = values
        self.refresh()
    
    def insertNewChildNode(self, parent_item: XarrayDataTreeItem, row: int = None) -> None:
        if not parent_item.isNode():
            return
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        if row is None or row == -1:
            row = len(parent_item.children)
        new_node = xr.DataTree()
        new_node_item = XarrayDataTreeItem(new_node)
        model.insertItems([new_node_item], row, parent_item)
    
    def insertNewDataVar(self, parent_item: XarrayDataTreeItem, row: int = None) -> None:
        if not parent_item.isNode():
            return
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        if row is None or row == -1:
            row = len(parent_item.children)
        shape = tuple(parent_item._node.sizes.values())
        dims = tuple(parent_item._node.dims)
        data = np.zeros(shape)
        from xarray_graph.utils.utils import unique_name
        name = unique_name('variable', list(parent_item._node.keys()))
        new_var = xr.DataArray(data, name=name, dims=dims)
        dt = model.treeData()
        path = parent_item._node.path.rstrip('/') + '/' + name
        dt[path] = new_var
        self.refresh()
    
    def insertNewCoord(self, parent_item: XarrayDataTreeItem, row: int = None, dim: str = None) -> None:
        if not parent_item.isNode():
            return
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        if row is None or row == -1:
            row = len(parent_item.children)
        if (dim is None) or (dim not in parent_item._node.dims):
            from qtpy.QtWidgets import QInputDialog
            dims: list[str] = [str(dim) for dim in parent_item.node().dims]
            dim, ok = QInputDialog.getItem(self, 'Select Dimension', 'Select dimension for new coordinate:', dims, editable=False)
            if not ok:
                return
        if dim in parent_item._node.coords:
            model.popupWarningDialog(f'Coordinate for dimension "{dim}" already exists.')
            return
        size = parent_item._node.sizes[dim]
        data = np.arange(size)
        new_coord = xr.DataArray(data, name=dim, dims=(dim,))
        dt = model.treeData()
        path = parent_item._node.path
        dt[path].dataset = dt[path].to_dataset().assign_coords({dim: new_coord})
        self.refresh()

    def insertNewRootNode(self) -> None:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        dt: xr.DataTree = model.treeData()
        root_name = dt.name or 'old root'
        new_dt = xr.DataTree()
        new_dt[root_name] = dt
        model.setTreeData(new_dt)
    
    def renameDimensions(self, item: XarrayDataTreeItem) -> None:
        if not item.isNode():
            assert isinstance(item.parent, XarrayDataTreeItem)
            item = item.parent
        node = item.data()
        assert isinstance(node, xr.DataTree)

        from qtpy.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QDialogButtonBox
        
        dim_lineedits: dict[str, QLineEdit] = {}
        for dim in node.dims:
            dim = str(dim)
            dim_lineedits[dim] = QLineEdit()
            dim_lineedits[dim].setPlaceholderText(dim)
        
        dlg = QDialog(self)
        # dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setWindowTitle('Rename Dimensions')
        vbox = QVBoxLayout(dlg)
        for lineedit in dim_lineedits.values():
            vbox.addWidget(lineedit)
        
        buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        vbox.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        dim_renames = {}
        for dim, lineedit in dim_lineedits.items():
            new_dim = lineedit.text().strip()
            if new_dim and new_dim != dim:
                dim_renames[dim] = new_dim
        if not dim_renames:
            return
        from xarray_graph.utils.xarray_utils import rename_dims
        rename_dims(node, dim_renames)
        self.refresh()
    
    def mergeSelectedNodes(self) -> None:
        pass # TODO
    
    def concatenateSelectedNodes(self, dim: str = None) -> None:
        model = self.model()
        if not isinstance(model, XarrayDataTreeModel):
            return
        items: list[XarrayDataTreeItem] = [item for item in self.selectedItems() if isinstance(item, XarrayDataTreeItem) and item.isNode()]
        if not items or len(items) < 2:
            return
        if dim is None:
            from qtpy.QtWidgets import QInputDialog
            title = 'Concatenate'
            label = 'Concatenate along dim:'
            dim, ok = QInputDialog.getText(self, title, label)
            if not ok:
                return
            dim = dim.strip()
            if not dim:
                return
        try:
            datasets: list[xr.Dataset] = [item._node.to_dataset() for item in items]
            concatenated_dataset: xr.Dataset = xr.concat(datasets, dim)
            parent_item = items[0].parent
            assert isinstance(parent_item, XarrayDataTreeItem)
            parent_node: xr.DataTree = parent_item.node()
            from xarray_graph.utils.utils import unique_name
            name = unique_name('Concat', list(parent_node.keys()))
            parent_node[name] = concatenated_dataset
            self.refresh()
        except Exception as err:
            model.popupWarningDialog(str(err))
    
    def keyPressEvent(self, event: QKeyEvent):
        if (event.key() == Qt.Key.Key_I) and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            items = self.selectedItems()
            if not items:
                model = self.model()
                if isinstance(model, XarrayDataTreeModel):
                    items = [model.rootItem()]
            if len(items) == 1:
                item = items[0]
                assert isinstance(item, XarrayDataTreeItem)
                data = item.data()
                title = item.path()
                infoDialog(data, parent=self, size=self._dialogSizeHint(), pos=QPoint(0, 0), title=title)
            else:
                # ensure items are in tree order
                from xarray_graph.tree.AbstractTreeItem import AbstractTreeItem
                items = AbstractTreeItem.orderedItems(items)
                data = [item.data() for item in items if isinstance(item, XarrayDataTreeItem)]
                title = 'Selected'
                infoDialog(data, parent=self, size=self._dialogSizeHint(), pos=QPoint(0, 0), title=title)
            return
        return super().keyPressEvent(event)
    
    def _dialogSizeHint(self) -> QSize:
        size = self.size()
        hmin = QDialog().sizeHint().height()
        if size.height() > hmin:
            size.setHeight(max(hmin, size.height() - 100))
        return size


def makeDialog(parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None) -> QDialog:
    dlg = QDialog(parent)
    if size is not None:
        dlg.resize(size)
    if pos is not None:
        if parent:
            dlg.move(parent.mapToGlobal(pos))
        else:
            dlg.move(pos)
    if title is not None:
        dlg.setWindowTitle(title)
    return dlg


def infoDialog(data: xr.DataTree | xr.DataArray | list[xr.DataTree | xr.DataArray], parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None, font_size: int = None) -> int:
    from qtpy.QtWidgets import QVBoxLayout
    from qtpy.QtCore import QTimer
    text_edit = infoTextEdit(data, font_size=font_size)
    dlg = makeDialog(parent, size, pos, title)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(text_edit)
    QTimer.singleShot(100, lambda: text_edit.verticalScrollBar().setValue(0))
    return dlg.exec()


def infoTextEdit(data: xr.DataTree | xr.DataArray | list[xr.DataTree | xr.DataArray], text_edit_to_update: QTextEdit = None, font_size: int = None) -> QTextEdit:
    text_edit = text_edit_to_update
    if not isinstance(text_edit, QTextEdit):
        text_edit = QTextEdit()
        from qtpy.QtGui import QFontDatabase
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        if font_size is None:
            # font_size = QFont().pointSize()
            font_size = QFontDatabase.systemFont(QFontDatabase.SystemFont.SmallestReadableFont).pointSize() + 2
        font.setPointSize(font_size)
        text_edit.setFont(font)
    else:
        text_edit.clear()
        if font_size is not None:
            font = text_edit.font()
            font.setPointSize(font_size)
            text_edit.setFont(font)

    if isinstance(data, (xr.DataTree, xr.Dataset, xr.DataArray)):
        text_edit.setPlainText(str(data))
    elif isinstance(data, (list, tuple)):
        sep = False
        for obj in data:
            if sep:
                # TODO: check if this works on Windows (see https://stackoverflow.com/questions/76710833/how-do-i-add-a-full-width-horizontal-line-in-qtextedit)
                text_edit.insertHtml('<br><hr><br>')
            else:
                sep = True
            text_edit.insertPlainText(str(obj))

            # tc = self.result_text_box.textCursor()
            # # move the cursor to the end of the document
            # tc.movePosition(tc.End)
            # # insert an arbitrary QTextBlock that will inherit the previous format
            # tc.insertBlock()
            # # get the block format
            # fmt = tc.blockFormat()
            # # remove the horizontal ruler property from the block
            # fmt.clearProperty(fmt.BlockTrailingHorizontalRulerWidth)
            # # set (not merge!) the block format
            # tc.setBlockFormat(fmt)
            # # eventually, apply the cursor so that editing actually starts at the end
            # self.result_text_box.setTextCursor(tc)
    
    text_edit.setReadOnly(True)
    return text_edit


def attrsDialog(data: xr.DataTree | xr.Dataset | xr.DataArray, parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None) -> int:
    from copy import deepcopy
    attrs_copy: dict = deepcopy(data.attrs)

    from xarray_graph.tree.KeyValueTreeView import KeyValueTreeView
    view = KeyValueTreeView()
    view.setAlternatingRowColors(True)
    view.setTreeData(attrs_copy)
    view.viewAll()

    from qtpy.QtWidgets import QVBoxLayout, QDialogButtonBox, QDialog

    dlg = makeDialog(parent, size, pos, title)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)

    btns = QDialogButtonBox()
    btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)
    
    status = dlg.exec()
    if status == QDialog.DialogCode.Accepted:
        data.attrs = attrs_copy
    return status


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child/grandchild/greatgrandchild'] = xr.DataTree()
    dt['child/grandchild/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['child/grandchild/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm/rasm2'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    print(dt)

    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setInfoColumnsVisible(True)
    model.setTreeData(dt)

    view = XarrayDataTreeView()
    view.setModel(model)
    view.show()
    view.resize(800, 1000)
    view.viewAll()
    view.move(50, 50)
    view.raise_()

    dt2 = dt.copy(deep=True)

    model2 = XarrayDataTreeModel()
    model2.setDataVarsVisible(True)
    model2.setCoordsVisible(True)
    model2.setInheritedCoordsVisible(True)
    model2.setInfoColumnsVisible(True)
    model2.setTreeData(dt2)

    view2 = XarrayDataTreeView()
    view2.setModel(model2)
    view2.show()
    view2.resize(800, 1000)
    view2.viewAll()
    view2.move(900, 50)
    view2.raise_()

    app.exec()

    print(dt)
    # print(dt2)


if __name__ == '__main__':
    test_live()
