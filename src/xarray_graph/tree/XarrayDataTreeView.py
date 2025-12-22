""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- open 1d or 2d array in table? editable? slice selection for 3d or higher dim?
- combine items (e.g., concatenate, merge)
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph import xarray_utils
from xarray_graph.tree import TreeView, XarrayDataTreeItem, XarrayDataTreeModel, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeView(TreeView):

    finishedEditingAttrs = Signal()

    _copied_key_value_map = {}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # icons
        self._group_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')
        self._unknown_icon: QIcon = qta.icon('fa6s.question')
        self._cut_icon = qta.icon('mdi.content-cut')
        self._copy_icon = qta.icon('mdi.content-copy')
        self._paste_icon = qta.icon('mdi.content-paste')

        # actions
        self._showDataVarsAction = QAction(
            text = 'Show Variables',
            icon = self._data_var_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide data_vars in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showCoordsAction = QAction(
            text = 'Show Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide inherited coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showDetailsColumnAction = QAction(
            text = 'Show Details Column',
            icon = qta.icon('fa6s.info'),
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show details column in the tree view. Uncheck to hide column.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._highlightSharedDataAction = QAction(
            text = 'Highlight Shared Data',
            icon = qta.icon('mdi6.format-color-highlight'),
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Highlight shared data arrays.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showDebugInfoAction = QAction(
            text = 'Show Data IDs (For Debugging)',
            icon = qta.icon('ph.bug-thin'),
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show IDs of underlying data arrays.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )
    
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
    
    def appendNewChildGroup(self, parent_item: XarrayDataTreeItem) -> None:
        if not parent_item.is_group:
            return
        model: XarrayDataTreeModel = self.model()
        row: int = len(parent_item.children)
        count: int = 1
        parent_index: QModelIndex = model.indexFromItem(parent_item)
        model.insertRows(row, count, parent_index)
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: XarrayDataTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: XarrayDataTreeItem = model.itemFromIndex(index)
        if item.is_group:
            icon: QIcon = self._group_icon
        elif item.is_data_var:
            icon: QIcon = self._data_var_icon
        elif item.is_coord:
            icon: QIcon = self._coord_icon
        else:
            # should never happen
            icon: QIcon = self._unknown_icon
        menu.addAction(QAction(f'{item.path}:', parent=menu, icon=icon, iconVisibleInMenu=True, enabled=False)) # just a label
        menu.addAction(QAction('Info', parent=menu, triggered=lambda checked, item=item: self._popupInfo(item)))
        menu.addAction(QAction('Attrs', parent=menu, triggered=lambda checked, item=item: self._editAttrs(item)))
        if item.is_variable:
            menu.addAction(QAction('Data', parent=menu, enabled=False))
        elif item.is_group:
            subtree_menu = QMenu('Subtree', parent=menu)
            subtree_menu.addAction(QAction('Rename Dimensions', parent=menu, triggered=lambda checked, item=item: self._renameDimensions(item)))
            subtree_menu.addAction(QAction('Rename Variables', parent=menu, triggered=lambda checked, item=item: self._renameVariables(item)))
            menu.addMenu(subtree_menu)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = self.hasCopy()
        menu.addSeparator()
        menu.addAction(QAction('Cut', parent=menu, icon=self._cut_icon, iconVisibleInMenu=True, triggered=lambda checked: self.cutSelection(), enabled=has_selection))
        menu.addAction(QAction('Copy', parent=menu, icon=self._copy_icon, iconVisibleInMenu=True, triggered=lambda checked: self.copySelection(), enabled=has_selection))
        menu.addAction(QAction('Paste', parent=menu, icon=self._paste_icon, iconVisibleInMenu=True, triggered=lambda checked, parent_item=item: self.pasteCopy(parent_item), enabled=has_copy))
        
        # remove item(s)
        menu.addSeparator()
        menu.addAction(QAction('Remove', parent=menu, triggered=lambda checked: self.removeSelectedItems(), enabled=has_selection))

        # combine items
        if has_selection and len(self.selectedIndexes()) > 1:
            menu.addSeparator()
            combine_menu = QMenu('Combine')
            combine_menu.addAction(QAction('Merge', parent=menu, triggered=lambda checked: self._mergeSelection(), enabled=False))
            combine_menu.addAction(QAction('Concatenate', parent=menu, triggered=lambda checked: self._concatenateSelectedGroups()))
            menu.addMenu(combine_menu)
        
        # insert new group
        if item.is_group:
            menu.addSeparator()
            menu.addAction(QAction('New Child Group', parent=menu, icon=self._group_icon, iconVisibleInMenu=True, triggered=lambda checked, parent_item=item: self.appendNewChildGroup(parent_item), enabled=has_selection))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # visible types
        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showInheritedCoordsAction)
        menu.addAction(self._showDetailsColumnAction)
        menu.addAction(self._highlightSharedDataAction)
        menu.addAction(self._showDebugInfoAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
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
        attrs_copy: dict = item.data.attrs.copy()

        model = KeyValueTreeModel()
        model.setKeyValueMap(attrs_copy)

        view = KeyValueTreeView()
        view.setAlternatingRowColors(True)
        view.setModel(model)
        view.showAll()

        dlg = QDialog(self)
        dlg.resize(max(self.width(), 800), self.height())
        # if self.window_decoration_offset is None:
        #     self._get_window_decoration_offset()
        # dlg.move(self.mapToGlobal(self.window_decoration_offset))
        dlg.move(self.mapToGlobal(QPoint(0, 0)))
        dlg.setWindowTitle(item.path)
        
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumSize(QSize(400, 400))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        attrs: dict = model.keyValueMap()
        item.data.attrs = attrs
        
        self.finishedEditingAttrs.emit()
    
    def _renameDimensions(self, root_item: XarrayDataTreeItem) -> None:
        model: XarrayDataTreeModel = self.model()
        if not model:
            return
        if not root_item.is_group:
            root_item = root_item.parent
        root_group: xr.DataTree = root_item.data
        root_group: xr.DataTree = xarray_utils._branch_root(root_group)
        while root_item.parent and root_item.data is not root_group:
            root_item = root_item.parent
        
        dims: list[str] = []
        for group in root_group.subtree:
            for dim in list(group.dims):
                if dim not in dims:
                    dims.append(dim)
        
        dim_lineedits: dict[str, QLineEdit] = {}
        for dim in dims:
            dim_lineedits[dim] = QLineEdit()
            dim_lineedits[dim].setPlaceholderText(dim)
        
        dlg = QDialog(self)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setWindowTitle('Rename Dimensions')
        vbox = QVBoxLayout(dlg)
        for dim in dims:
            vbox.addWidget(dim_lineedits[dim])
        
        buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        vbox.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        renamed_dims = {}
        for dim in dims:
            new_dim = dim_lineedits[dim].text().strip()
            if new_dim and new_dim != dim:
                renamed_dims[dim] = new_dim
        if not renamed_dims:
            return
        
        # rename in copy of branch root subtree
        root_path = root_group.path
        n_root_path = len(root_path)
        for group in root_group.subtree:
            group_renamed_dims = {dim: new_dim for dim, new_dim in renamed_dims.items() if dim in list(group.dims)}
            if not group_renamed_dims:
                continue
            old_dataset: xr.Dataset = group.to_dataset()
            new_dataset: xr.Dataset = old_dataset.rename_dims(group_renamed_dims)
            # rename index coords
            coord_renames = {name: group_renamed_dims[name] for name in list(new_dataset.coords) if name in group_renamed_dims}
            if coord_renames:
                new_dataset = new_dataset.assign_coords({new_name: new_dataset.coords[old_name] for old_name, new_name in coord_renames.items()}).drop_vars(list(coord_renames))
                coords: dict[str, xr.DataArray] = {}
                for name in old_dataset.coords:
                    if name in coord_renames:
                        name = coord_renames[name]
                    coords[name] = new_dataset.coords[name]
                new_dataset = xr.Dataset(
                    data_vars=new_dataset.data_vars,
                    coords=coords,
                    attrs=new_dataset.attrs
                )
            if group is root_group:
                new_root_group = xr.DataTree(dataset=new_dataset)
            else:
                rel_path = group.path[n_root_path:].lstrip('/')
                new_root_group[rel_path] = xr.DataTree(dataset=new_dataset)

        # insert renamed copy of branch into datatree
        dt: xr.DataTree = model.datatree()
        if root_group is dt:
            self.setDatatree(new_root_group)
        else:
            dt[root_path] = new_root_group
            self.refresh()
    
    def _renameVariables(self, root_item: XarrayDataTreeItem) -> None:
        model: XarrayDataTreeModel = self.model()
        if not model:
            return
        if not root_item.is_group:
            root_item = root_item.parent
        root_group: xr.DataTree = root_item.data
        
        var_names: list[str] = []
        for group in root_group.subtree:
            for name in group.variables:
                if name not in var_names:
                    var_names.append(name)
        
        lineedits: dict[str, QLineEdit] = {}
        for name in var_names:
            lineedits[name] = QLineEdit()
            lineedits[name].setPlaceholderText(name)
        
        dlg = QDialog(self)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setWindowTitle('Rename Variables')
        vbox = QVBoxLayout(dlg)
        for name in var_names:
            vbox.addWidget(lineedits[name])
        
        buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        vbox.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        var_renames = {}
        for name in var_names:
            new_name = lineedits[name].text().strip()
            if new_name and new_name != name:
                var_renames[name] = new_name
        if not var_renames:
            return
        
        # rename in copy of branch root subtree
        root_path = root_group.path
        n_root_path = len(root_path)
        for group in root_group.subtree:
            group_var_renames = {old_name: new_name for old_name, new_name in var_renames.items() if old_name in list(group.data_vars)}
            if not group_var_renames:
                continue
            old_dataset: xr.Dataset = group.to_dataset()
            new_dataset: xr.Dataset = old_dataset.rename_vars(group_var_renames)
            if group is root_group:
                new_root_group = xr.DataTree(dataset=new_dataset)
            else:
                rel_path = group.path[n_root_path:].lstrip('/')
                new_root_group[rel_path] = xr.DataTree(dataset=new_dataset)

        # insert renamed copy of branch into datatree
        dt: xr.DataTree = model.datatree()
        if root_group is dt:
            self.setDatatree(new_root_group)
        else:
            dt[root_path] = new_root_group
            self.refresh()
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items: list[XarrayDataTreeItem] = self.selectedItems()
        if not items:
            return
        # only copy the branch roots (this already includes the descendents)
        items = XarrayDataTreeModel._branchRootItemsOnly(items)
        # copy the values in each branch root subtree
        copied_key_value_map: dict[str, xr.DataTree | xr.DataArray] = {}
        for item in items:
            key = xarray_utils.unique_name(item.name, list(copied_key_value_map.keys()))
            value: xr.DataTree | xr.DataArray = item.data
            if isinstance(value, xr.DataTree):
                copied_value: xr.DataTree = value.copy(inherit=True, deep=True)
                copied_value.orphan()
            elif isinstance(value, xr.DataArray):
                copied_value: xr.DataArray = value.copy(deep=True)
            else:
                continue
            copied_key_value_map[key] = copied_value
        XarrayDataTreeView._copied_key_value_map = copied_key_value_map
    
    def pasteCopy(self, parent_item: XarrayDataTreeItem = None, row: int = -1) -> None:
        model: XarrayDataTreeModel = self.model()
        if not model:
            return
        copied_key_value_map = XarrayDataTreeView._copied_key_value_map
        if not copied_key_value_map:
            return
        
        if parent_item is None:
            items = self.selectedItems()
            if not items:
                return
            parent_item = items[0]
            if not parent_item.is_group or len(items) > 1:
                parent_widget: QWidget = self
                title = 'Invalid Paste'
                text = f'Must select a single group item in which to paste.'
                QMessageBox.warning(parent_widget, title, text)
                return
        
        # paste items
        name_item_map: dict[str, XarrayDataTreeItem] = {}
        key: str
        value: xr.DataTree | xr.DataArray
        for key, value in copied_key_value_map.items():
            item = XarrayDataTreeItem(value.copy(deep=True))
            model._updateItemSubtree(item)
            name_item_map[key] = item
        if row == -1:
            row = len(parent_item.children)
        
        self.storeViewState()
        model.insertItems(name_item_map, row, parent_item)
        self.reset() # in case copied arrays bring coords with them
        self.restoreViewState()
    
    def hasCopy(self) -> bool:
        if XarrayDataTreeView._copied_key_value_map:
            return True
        return False
    
    def _mergeSelection(self) -> None:
        pass # TODO
    
    def _concatenateSelectedGroups(self, dim: str = None) -> None:
        model: XarrayDataTreeModel = self.model()
        if not model:
            return
        items: list[XarrayDataTreeItem] = [item for item in self.selectedItems() if item.is_group]
        if not items or len(items) < 2:
            return
        if dim is None:
            title = 'Concatenate'
            label = 'Concatenate along dim:'
            dim, ok = QInputDialog.getText(self, title, label)
            if not ok:
                return
            dim = dim.strip()
            if not dim:
                return
        datasets: list[xr.Dataset] = [item.data.to_dataset() for item in items]
        concatenated_dataset: xr.Dataset = xr.concat(datasets, dim)
        parent_item: XarrayDataTreeItem = items[0].parent
        parent_group: xr.DataTree = parent_item.data
        name = xarray_utils.unique_name('Concat', list(parent_group.keys()))
        parent_group[name] = concatenated_dataset
        self.refresh()
    
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
    model.setSharedDataHighlighted(True)
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
    view.resize(800, 700)
    view.showAll()
    view.move(50, 50)
    view.raise_()

    dt2 = dt.copy(deep=True)

    model2 = XarrayDataTreeModel()
    model2.setDataVarsVisible(True)
    model2.setCoordsVisible(True)
    model2.setInheritedCoordsVisible(True)
    model2.setDetailsColumnVisible(True)
    model2.setSharedDataHighlighted(True)
    model2.setDatatree(dt2)

    view2 = XarrayDataTreeView()
    view2.setModel(model2)
    view2.show()
    view2.resize(800, 700)
    view2.showAll()
    view2.move(900, 50)
    view2.raise_()

    app.exec()

    # print(dt)
    # print(dt2)


if __name__ == '__main__':
    test_live()
