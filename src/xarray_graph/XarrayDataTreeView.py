""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- edit attrs in key-value tree ui
- open 1d or 2d array in table? editable? slice selection for 3d or higher dim?
- global rename of variables throughout the entire branch or tree?
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph import xarray_utils, TreeView, XarrayDataTreeType, XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeMimeData
# from pyqt_ext.tree import KeyValueTreeItem, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeView(TreeView):

    finishedEditingAttrs = Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._initActions()
    
    def setModel(self, model: XarrayDataTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        super().setModel(model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model: XarrayDataTreeModel = self.model()
        
        self._showDataVarsAction.blockSignals(True)
        self._showDataVarsAction.setChecked(model.isDataVarsVisible())
        self._showDataVarsAction.blockSignals(False)
        
        self._showCoordsAction.blockSignals(True)
        self._showCoordsAction.setChecked(model.isCoordsVisible())
        self._showCoordsAction.blockSignals(False)
        
        self._showInheritedCoordsAction.blockSignals(True)
        self._showInheritedCoordsAction.setChecked(model.isInheritedCoordsVisible())
        self._showInheritedCoordsAction.blockSignals(False)
        
        self._showDetailsColumnAction.blockSignals(True)
        self._showDetailsColumnAction.setChecked(model.isDetailsColumnVisible())
        self._showDetailsColumnAction.blockSignals(False)
        
        self._highlightSharedDataAction.blockSignals(True)
        self._highlightSharedDataAction.setChecked(model.isSharedDataHighlighted())
        self._highlightSharedDataAction.blockSignals(False)
        
        self._showDebugInfoAction.blockSignals(True)
        self._showDebugInfoAction.setChecked(model.isDebugInfoVisible())
        self._showDebugInfoAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model: XarrayDataTreeModel = self.model()
        self.storeViewState()
        model.setDataVarsVisible(self._showDataVarsAction.isChecked())
        model.setCoordsVisible(self._showCoordsAction.isChecked())
        model.setInheritedCoordsVisible(self._showInheritedCoordsAction.isChecked())
        model.setDetailsColumnVisible(self._showDetailsColumnAction.isChecked())
        model.setSharedDataHighlighted(self._highlightSharedDataAction.isChecked())
        model.setDebugInfoVisible(self._showDebugInfoAction.isChecked())
        self.restoreViewState()
    
    def refresh(self) -> None:
        model: XarrayDataTreeModel = self.model()
        self.storeViewState()
        model.reset()
        self.restoreViewState()
        self.wasRefreshed.emit()
    
    def datatree(self) -> xr.DataTree:
        model: XarrayDataTreeModel = self.model()
        return model.datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            model = XarrayDataTreeModel()
            model.setDatatree(datatree)
            self.setModel(model)
        else:
            self.storeViewState()
            model.setDatatree(datatree)
            self.restoreViewState()
    
    def forgetViewState(self) -> None:
        self._view_state = {}
    
    def storeViewState(self, items: list[XarrayDataTreeItem] = None) -> None:
        model: XarrayDataTreeModel = self.model()
        if items is None:
            items = list(model._root_item.subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        item: XarrayDataTreeItem
        for item in items:
            if item.is_root:
                continue
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            self._view_state[item.path] = {
                'expanded': self.isExpanded(index),
                'selected': index in selected_indexes
            }

    def restoreViewState(self, items: list[XarrayDataTreeItem] = None) -> None:
        model: XarrayDataTreeModel = self.model()
        if not self._view_state:
            return
        if items is None:
            items = list(model._root_item.subtree_depth_first())
        # self.selectionModel().clearSelection()
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        to_be_selected: QItemSelection = QItemSelection()
        to_be_deselected: QItemSelection = QItemSelection()
        item: XarrayDataTreeItem
        for item in items:
            if item.is_root:
                continue
            item_view_state: dict = self._view_state.get(item.path, None)
            if item_view_state is None:
                continue
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            is_expanded = item_view_state.get('expanded', False)
            self.setExpanded(index, is_expanded)
            is_selected = item_view_state.get('selected', False)
            if is_selected and index not in selected_indexes:
                to_be_selected.merge(QItemSelection(index, index), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            elif not is_selected and index in selected_indexes:
                to_be_deselected.merge(QItemSelection(index, index), QItemSelectionModel.SelectionFlag.Deselect | QItemSelectionModel.SelectionFlag.Rows)
        #     if is_selected:
        #         selection.merge(QItemSelection(index, index), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        # if selection.count():
        #     self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if to_be_selected.count():
            self.selectionModel().select(to_be_selected, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if to_be_deselected.count():
            self.selectionModel().select(to_be_deselected, QItemSelectionModel.SelectionFlag.Deselect | QItemSelectionModel.SelectionFlag.Rows)
    
    def appendNewChildGroup(self, parent_item: XarrayDataTreeItem) -> None:
        if not parent_item.is_group:
            return
        model: XarrayDataTreeModel = self.model()
        row: int = len(parent_item.children)
        count: int = 1
        parent_index: QModelIndex = model.indexFromItem(parent_item)
        model.insertRows(row, count, parent_index)
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        menu = super().customContextMenu(index)

        # item that was clicked on
        model: XarrayDataTreeModel = self.model()
        item: XarrayDataTreeItem = model.itemFromIndex(index)
        before: QAction = menu.actions()[0]
        action = QAction(f'{item.path}:')
        menu.insertAction(before, action)
        action.setEnabled(False) # just a label
        menu.insertAction(before, QAction('Info', triggered=lambda checked, item=item: self._popupInfo(item)))
        menu.insertAction(before, QAction('Attrs', triggered=lambda checked, item=item: self._editAttrs(item)))
        if item.is_variable:
            menu.insertAction(before, QAction('Data'))
        elif item.is_group:
            subtree_menu = QMenu('Subtree')
            subtree_menu.addAction('Rename Dimensions').setEnabled(False)
            subtree_menu.addAction('Rename Variables').setEnabled(False)
            menu.insertMenu(before, subtree_menu)
        
        # TODO: cut/copy/paste
        has_selection = self.selectionModel().hasSelection()
        has_copy = False # TODO
        before: QAction = menu._expandSeparatorAction
        menu.insertSeparator(before)
        for action, enabled in [
            (QAction('Cut', triggered=lambda checked: self.cutSelection()), has_selection),
            (QAction('Copy', triggered=lambda checked: self.copySelection()), has_selection),
            (QAction('Paste', triggered=lambda checked, parent_item=item: self.pasteCopy(parent_item)), has_copy),
        ]:
            menu.insertAction(before, action)
            action.setEnabled(enabled)
        
        # remove item(s)
        before: QAction = menu._expandSeparatorAction
        menu.insertSeparator(before)
        action = QAction('Remove', triggered=lambda checked: self.removeSelectedItems())
        menu.insertAction(before, action)
        action.setEnabled(has_selection)

        # merge/concatenate/...
        # TODO
        
        # insert new group
        if item.is_group:
            before: QAction = menu._expandSeparatorAction
            action = QAction('New Child Group', triggered=lambda checked, parent_item=item: self.appendNewChildGroup(parent_item))
            menu.insertSeparator(before)
            menu.insertAction(before, action)

        # visible types
        actions = [
            self._showDataVarsAction,
            self._showCoordsAction,
            self._showInheritedCoordsAction,
            self._showDetailsColumnAction,
            self._highlightSharedDataAction,
            self._showDebugInfoAction,
        ]
        before: QAction = menu._refreshSeparatorAction
        menu.insertSeparator(before)
        for action in actions:
            menu.insertAction(before, action)
        
        return menu
    
    def _popupInfo(self, item: XarrayDataTreeItem) -> None:
        info = str(item.data)
        
        textEdit = QTextEdit()
        textEdit.setPlainText(info)
        textEdit.setReadOnly(True)

        dlg = QDialog(self)
        dlg.resize(max(self.width(), 800), self.height())
        # if self.window_decoration_offset is None:
        #     self._get_window_decoration_offset()
        # dlg.move(self.mapToGlobal(self.window_decoration_offset))
        dlg.move(self.mapToGlobal(QPoint(0, 0)))
        dlg.setWindowTitle(item.path)
        
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(textEdit)

        dlg.exec()
    
    def _editAttrs(self, item: XarrayDataTreeItem) -> None:
        attrs: dict = item.data.attrs.copy()
        
        # TODO
        # root = KeyValueTreeItem(attrs)
        # kvmodel = KeyValueTreeModel(root)
        # view = KeyValueTreeView()
        # view.setAlternatingRowColors(True)
        # view.setModel(kvmodel)
        # view.expandAll()
        # view.resizeAllColumnsToContents()

        # dlg = QDialog(self)
        # dlg.setWindowTitle(path)
        # layout = QVBoxLayout(dlg)
        # layout.setContentsMargins(0, 0, 0, 0)
        # layout.addWidget(view)

        # btns = QDialogButtonBox()
        # btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        # btns.accepted.connect(dlg.accept)
        # btns.rejected.connect(dlg.reject)
        # layout.addWidget(btns)
        
        # dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        # dlg.setMinimumSize(QSize(400, 400))
        # if dlg.exec() != QDialog.DialogCode.Accepted:
        #     return
        
        # root: KeyValueTreeItem = kvmodel.rootItem()
        # attrs: dict = root.value()
        # obj.attrs = attrs
        
        # self.finishedEditingAttrs.emit()
    
    def cutSelection(self) -> None:
        pass # TODO
    
    def copySelection(self) -> None:
        """ Copy selected items.
        """
        model: XarrayDataTreeModel = self.model()
        dt: xr.DataTree = model.datatree()
        
        # TODO
        # paths: list[str] = self.selectedPaths()
        # root_paths: list[str] = []
        # for path in paths:
        #     ok = True
        #     for check_path in paths:
        #         if check_path == path:
        #             continue
        #         if path.startswith(check_path):
        #             # path is a descendant of check_path
        #             ok = False
        #             break
        #     if ok:
        #         root_paths.append(path)
        
        # self._copied_nodes: list[xr.DataTree] = []
        # self._copied_vars: list[xr.DataArray] = []
        # self._copied_coords: list[xr.DataArray] = []
        # for path in root_paths:
        #     obj: xr.DataTree | xr.DataArray = dt[path]
        #     copied_obj = obj.copy(deep=True)
        #     if isinstance(obj, xr.DataTree) and obj.parent is not None:
        #         # copy inherited coords
        #         copied_obj.orphan()
        #         for name in obj._inherited_coords_set():
        #             coord = obj.coords[name]
        #             copied_obj.coords[name] = xr.DataArray(data=coord.data.copy(), dims=coord.dims, attrs=deepcopy(coord.attrs))
        #         self._copied_nodes.append(copied_obj)
        #     elif isinstance(obj, xr.DataArray):
        #         parent_path: str = model.parentPath(path)
        #         parent_node: xr.DataTree = dt[parent_path]
        #         if obj.name in parent_node.data_vars:
        #             self._copied_vars.append(copied_obj)
        #         elif obj.name in parent_node.coords:
        #             if obj.name in parent_node._inherited_coords_set():
        #                 # copy inherited coord
        #                 copied_obj = xr.DataArray(data=copied_obj.data.copy(), name=copied_obj.name, dims=copied_obj.dims, attrs=deepcopy(copied_obj.attrs))
        #             self._copied_coords.append(copied_obj)
    
    def pasteCopy(self, parent_item: XarrayDataTreeItem = None, row: int = -1) -> None:
        if parent_path is None:
            selected_paths = self.selectedPaths()
            if selected_paths:
                parent_path = selected_paths[0]
            else:
                parent_path = '/'

        # TODO
        # copied_nodes: list[xr.DataTree] = getattr(self, '_copied_nodes', [])
        # copied_vars: list[xr.DataTree] = getattr(self, '_copied_vars', [])
        # copied_coords: list[xr.DataTree] = getattr(self, '_copied_coords', [])
        
        # dt: xr.DataTree = self.datatree()
        # parent: xr.DataTree | xr.DataArray = dt[parent_path]
        # if isinstance(parent, xr.DataArray):
        #     parent_path = self.model().parentPath(parent_path)
        #     parent = dt[parent_path]
        # parent_keys = list(parent.data_vars) + list(parent.coords) + list(parent.children)
        
        # self.storeState()
        # self.model().beginResetModel()
        # for node in copied_nodes:
        #     node.name = XarrayDataTreeModel.uniqueName(node.name or '?', parent_keys)
        #     parent_keys += node.name
        # if copied_nodes:
        #     children = {name: child for name, child in parent.children.items()}
        #     for node in copied_nodes:
        #         children[node.name] = node
        #     parent.children = children
        # vars = {}
        # for var in copied_vars:
        #     var.name = XarrayDataTreeModel.uniqueName(var.name or '?', parent_keys)
        #     vars[var.name] = var
        #     parent_keys += var.name
        # if vars:
        #     parent.dataset = parent.to_dataset().assign(vars)
        # coords = {coord.name: coord for coord in copied_coords}
        # if coords:
        #     parent.dataset = parent.to_dataset().assign_coords(coords)
        # self.model().endResetModel()
        # self.restoreState()
    
    # def renameDimensions(self, path: str = None) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if model is None:
    #         return
    #     dt: xr.DataTree = model.datatree()
    #     if dt is None:
    #         return
    #     node: xr.DataTree | xr.DataArray = dt[path]
    #     if isinstance(node, xr.DataArray):
    #         path = model.parentPath(path)
    #         node: xr.DataTree = dt[path]
        
    #     dims = []
    #     subnode: xr.DataTree
    #     for subnode in node.subtree:
    #         for dim in subnode.dims:
    #             if dim not in dims:
    #                 dims.append(dim)
    #     if not dims:
    #         QMessageBox.warning(self, 'Rename Dimensions', f'No dimensions found in subtree at {path}.')
    #         return
        
    #     dim_editors: dict[str, QLineEdit] = {dim: QLineEdit(dim) for dim in dims}

    #     dlg = QDialog(self)
    #     dlg.setWindowTitle('Rename Dimensions')
    #     dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    #     form = QFormLayout(dlg)
    #     form.setContentsMargins(0, 0, 0, 0)
    #     form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    #     form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    #     for dim, editor in dim_editors.items():
    #         form.addRow(f'{dim} ->', editor)

    #     btns = QDialogButtonBox()
    #     btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
    #     btns.accepted.connect(dlg.accept)
    #     btns.rejected.connect(dlg.reject)
    #     form.addRow(btns)
    #     if dlg.exec() != QDialog.DialogCode.Accepted:
    #         return
        
    #     self.storeState()
    #     self.model().beginResetModel()
    #     # print(node)
    #     subnode: xr.DataTree
    #     for subnode in node.subtree:
    #         old_dims = list(subnode.dims)
    #         new_dims = [dim_editors[dim].text() if dim in dim_editors else dim for dim in old_dims]
    #         dim_map = {old: new for old, new in zip(old_dims, new_dims) if old != new}
    #         if dim_map:
    #             subnode.dataset = subnode.to_dataset().rename(dim_map)
    #     # print(node)
    #     self.model().endResetModel()
    #     self.restoreState()
    
    def _initActions(self) -> None:

        # optionally show vars and coords
        self._showDataVarsAction = QAction(
            text = 'Show Variables',
            # icon = self._data_var_icon,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide data_vars in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showCoordsAction = QAction(
            text = 'Show Coordinates',
            # icon = self._coord_icon,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            # icon = self._coord_icon,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide inherited coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        # optional details column
        self._showDetailsColumnAction = QAction(
            text = 'Show Details Column',
            # icon = qta.icon('ph.info'),
            checkable = True,
            checked = False,
            toolTip = 'Show details column in the tree view. Uncheck to hide column.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        # optionally highlight shared data arrays
        self._highlightSharedDataAction = QAction(
            text = 'Highlight Shared Data',
            # icon = qta.icon('ph.info'),
            checkable = True,
            checked = False,
            toolTip = 'Highlight shared data arrays.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        # optionally show data array IDs (for debugging)
        self._showDebugInfoAction = QAction(
            text = 'Show Data IDs (For Debugging)',
            # icon = qta.icon('ph.info'),
            checkable = True,
            checked = False,
            toolTip = 'Show IDs of underlying data arrays.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )
    
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_C:
            modifiers: Qt.KeyboardModifier = event.modifiers()
            if Qt.KeyboardModifier.ControlModifier in modifiers:
                # copy
                self.copySelection()
                return
        elif event.key() == Qt.Key.Key_V:
            modifiers: Qt.KeyboardModifier = event.modifiers()
            if Qt.KeyboardModifier.ControlModifier in modifiers:
                # paste
                self.pasteCopy()
                return
        return super().keyPressEvent(event)


def test_live():
    import numpy as np
    from xarray_graph import XarrayDataTreeDebugView

    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    # dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    # dt['child3/grandchild1/tiny'] = xr.tutorial.load_dataset('tiny')
    # dt['child3/rasm'] = xr.tutorial.load_dataset('rasm')
    # dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')

    app = QApplication()

    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setDatatree(dt)

    # parent_item = model._root_item.children[0]
    # half_air = dt['air_temperature/air'] / 2
    # data_var_item = XarrayDataTreeItem(half_air, XarrayDataTreeType.DATA_VAR)
    # model.insertItems({'half air': data_var_item}, 0, parent_item)

    # parent_item = model._root_item.children[0]
    # twice_lat = xr.DataArray(data=dt['air_temperature/lat'].values * 2, dims=('twice lat',))
    # coord_item = XarrayDataTreeItem(twice_lat, XarrayDataTreeType.COORD)
    # model.insertItems({'twice lat': coord_item}, 0, parent_item)

    # dt['air_temperature/inherits/laty'] = xr.DataArray(np.arange(25), dims=('twice lat',))
    # dt['air_temperature/inherits/again/laty'] = xr.DataArray(np.arange(25), dims=('twice lat',))
    # dt['air_temperature/laty'] = xr.DataArray(np.arange(25), dims=('twice lat',))
    # model.reset()

    view = XarrayDataTreeView()
    view.setModel(model)
    view.show()
    view.resize(800, 1000)
    view.showAll()
    view.move(100, 50)
    view.raise_()

    # debug_view = XarrayDataTreeDebugView()
    # debug_view.setDatatree(dt)
    # debug_view.show()
    # debug_view.resize(800, 800)
    # debug_view.move(900, 100)
    # debug_view.raise_()

    app.exec()
    # print(dt)


if __name__ == '__main__':
    test_live()
