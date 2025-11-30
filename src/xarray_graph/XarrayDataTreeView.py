""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- store/restore state
- store/restore state of dragged items in dragEnterEvent() and dropEvent()
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
from xarray_graph import xarray_utils, XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeMimeData
# from pyqt_ext.tree import KeyValueTreeItem, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeView(QTreeView):

    selectionWasChanged = Signal()
    finishedEditingAttrs = Signal()
    wasRefreshed = Signal()

    # for store/restore view state
    STATE_KEY = '_state'

    window_decoration_offset: QPoint = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # general settings
        sizePolicy = self.sizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(sizePolicy)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.setUniformRowHeights(True)
        self.setSortingEnabled(False)

        # selection
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # drag-n-drop
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragAndDropEnabled(True)

        # context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        # optionally show vars and coords
        self._showDataVarsAction = QAction(
            text = 'Show Variables',
            icon = qta.icon('ph.cube-thin'),
            checkable = True,
            checked = True,
            toolTip = 'Show data_vars in the tree view. Uncheck to hide them.',
            triggered = self._updateModelFromViewOptions
        )

        self._showCoordsAction = QAction(
            text = 'Show Coordinates',
            icon = qta.icon('ph.list-numbers-thin'),
            checkable = True,
            checked = False,
            toolTip = 'Show coords in the tree view. Uncheck to hide them.',
            triggered = self._updateModelFromViewOptions
        )

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            icon = qta.icon('ph.list-numbers-thin'),
            checkable = True,
            checked = True,
            toolTip = 'Show inherited coords in the tree view. Uncheck to hide them.',
            triggered = self._updateModelFromViewOptions
        )

        # optional details column
        self._showDetailsColumnAction = QAction(
            text = 'Show Details Column',
            icon = qta.icon('ph.info'),
            checkable = True,
            checked = False,
            toolTip = 'Show details column in the tree view. Uncheck to hide column.',
            triggered = self._updateModelFromViewOptions
        )
    
    def refresh(self) -> None:
        self.storeState()
        self.model().reset()
        self.restoreState()
        self.wasRefreshed.emit()
    
    def model(self) -> XarrayDataTreeModel:
        model: XarrayDataTreeModel = super().model()
        return model
    
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

    def _updateModelFromViewOptions(self):
        model: XarrayDataTreeModel = self.model()
        
        self.storeState()
        model.setDataVarsVisible(self._showDataVarsAction.isChecked())
        model.setCoordsVisible(self._showCoordsAction.isChecked())
        model.setInheritedCoordsVisible(self._showInheritedCoordsAction.isChecked())
        model.setDetailsColumnVisible(self._showDetailsColumnAction.isChecked())
        self.restoreState()
    
    def datatree(self) -> xr.DataTree:
        return self.model().datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self.storeState()
        if self.model() is None:
            self.setModel(XarrayDataTreeModel(datatree=datatree), updateViewOptionsFromModel=False)
        else:
            self.model().setDatatree(datatree)
        self.restoreState()
    
    def storeState(self) -> None:
        return
        model: XarrayDataTreeModel = self.model()
        dt: xr.DataTree = model.datatree()
        
        state = getattr(self, self.STATE_KEY, {})
        selected: list[QModelIndex] = self.selectionModel().selectedIndexes()
        node: xr.DataTree
        for node in dt.subtree:
            if node is dt:
                continue
            paths: list[str] = [node.path]
            for name in model._rowNames(node):
                path: str = f'{node.path}/{name}'
                if isinstance(dt[path], xr.DataTree):
                    # already handled in outer loop over nodes
                    continue
                paths.append(path)
            for path in paths:
                index: QModelIndex = model.indexFromPath(path)
                if not index.isValid():
                    continue
                state[path] = {
                    'expanded': self.isExpanded(index),
                    'selected': index in selected
                }
        setattr(self, self.STATE_KEY, state)

    def restoreState(self) -> None:
        return
        model: XarrayDataTreeModel = self.model()
        dt: xr.DataTree = model.datatree()
        state = getattr(self, self.STATE_KEY, {})
        if not state:
            return

        self.selectionModel().clearSelection()
        selection: QItemSelection = QItemSelection()
        node: xr.DataTree
        for node in dt.subtree:
            if node is dt:
                continue
            paths: list[str] = [node.path]
            for name in model._rowNames(node):
                path: str = f'{node.path}/{name}'
                if isinstance(dt[path], xr.DataTree):
                    # already handled in outer loop over nodes
                    continue
                paths.append(path)
            for path in paths:
                if path not in state:
                    continue
                index: QModelIndex = model.indexFromPath(path)
                if not index.isValid():
                    continue
                item_state: dict = state[path]
                isExpanded = item_state.get('expanded', False)
                self.setExpanded(index, isExpanded)
                isSelected = item_state.get('selected', False)
                if isSelected:
                    selection.merge(QItemSelection(index, index), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if selection.count():
            self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    
    @Slot(QItemSelection, QItemSelection)
    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        QTreeView.selectionChanged(self, selected, deselected)
        self.selectionWasChanged.emit()

    def selectedItems(self) -> list[XarrayDataTreeItem]:
        model: XarrayDataTreeModel = self.model()
        indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        items: list[XarrayDataTreeItem] = [model.itemFromIndex(index) for index in indexes]
        return items
    
    def setSelectedItems(self, items: list[XarrayDataTreeItem]):
        model: XarrayDataTreeModel = self.model()
        self.selectionModel().clearSelection()
        selection: QItemSelection = QItemSelection()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        item: XarrayDataTreeItem
        for item in items:
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            selection.merge(QItemSelection(index, index), flags)
        if selection.count():
            self.selectionModel().select(selection, flags)
    
    def removeSelectedItems(self, ask: bool = True) -> None:
        items: list[XarrayDataTreeItem] = self.selectedItems()
        if not items:
            return
        if ask:
            answer = QMessageBox.question(self, 'Remove', f'Remove selected?', 
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                defaultButton=QMessageBox.StandardButton.No
            )
            if answer!= QMessageBox.StandardButton.Yes:
                return
        model: XarrayDataTreeModel = self.model()
        model.removeItems(items)
    
    def removeItem(self, item: XarrayDataTreeItem, ask: bool = True) -> None:
        if ask:
            answer = QMessageBox.question(self, 'Remove', f'Remove {item.path}?', 
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                defaultButton=QMessageBox.StandardButton.No
            )
            if answer!= QMessageBox.StandardButton.Yes:
                return
        model: XarrayDataTreeModel = self.model()
        model.removeItems([item])
    
    def appendNewNode(self, parent_item: XarrayDataTreeItem, name: str = None) -> None:
        if not parent_item.is_node:
            return
        if name is None:
            parent: QWidget = self
            title: str = 'New DataTree Group'
            label: str = 'Group Name'
            name, ok = QInputDialog.getText(parent, title, label)
            if not ok:
                return
        if '/' in name:
            parent: QWidget = self
            title: str = 'Invalid Name'
            text = f'"{name}" is an invalid DataTree path key which cannot contain path seaprators "/".'
            QMessageBox.warning(parent, title, text)
            return
        parent_node: xr.DataTree = parent_item.data
        if name in list(parent_node.keys()):
            parent: QWidget = self
            title: str = 'Existing Name'
            text = f'"{name}" already exists in parent DataTree.'
            QMessageBox.warning(self, title, text)
            return
        new_node = xr.DataTree()
        new_item = XarrayDataTreeItem(new_node)
        row = len(parent_item.children)
        self.model().insertItems({name: new_item}, parent_item, row)
    
    @Slot(QPoint)
    def onCustomContextMenuRequested(self, point: QPoint) -> None:
        index: QModelIndex = self.indexAt(point)
        menu: QMenu = self.customContextMenu(index)
        menu.exec(self.viewport().mapToGlobal(point))
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: XarrayDataTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: XarrayDataTreeItem = model.itemFromIndex(index)
        menu.addAction(f'{item.path}:').setEnabled(False)  # just a label, not clickable
        menu.addAction('Info', lambda item=item: self._popupInfo(item))
        if item.is_data_var or item.is_coord:
            # TODO
            menu.addAction('Data').setEnabled(False) #, lambda item=item: self._viewData(item))
        menu.addAction('Attrs', lambda item=item: self._editAttrs(item))
        
        # selection
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction('Select All', self.selectAll)
            menu.addAction('Select None', self.clearSelection)
        
        # TODO: cut/copy/paste
        has_selection = self.selectionModel().hasSelection()
        has_copy = False # TODO
        menu.addSeparator()
        menu.addAction('Cut', self.cutSelection).setEnabled(has_selection)
        menu.addAction('Copy', self.copySelection).setEnabled(has_selection)
        menu.addAction('Paste', lambda item=item: self.pasteCopy(item)).setEnabled(has_copy)
        
        # remove item(s)
        menu.addSeparator()
        menu.addAction('Remove', self.removeSelectedItems).setEnabled(has_selection)
        
        # insert new node
        if item.is_node:
            menu.addSeparator()
            menu.addAction('Add New Child DataTree', lambda parent_item=item: self.appendNewNode(parent_item))

        # TODO: rename things
        menu.addSeparator()
        menu.addAction('Rename Variables').setEnabled(False)
        menu.addAction('Rename Dimensions').setEnabled(False)
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction('Expand All', self.expandAll)
        menu.addAction('Collapse All', self.collapseAll)
        if model.columnCount() > 1:
            menu.addAction('Resize Columns to Contents', self.resizeAllColumnsToContents)
            menu.addAction('Show All', self.showAll)

        # visible types
        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showInheritedCoordsAction)
        menu.addAction(self._showDetailsColumnAction)

        # refresh
        menu.addSeparator()
        menu.addAction('Refresh', self.refresh)
        
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
    
    @staticmethod
    def _get_window_decoration_offset():
        window = QWidget()
        window.show()
        frame: QRect = window.frameGeometry()
        geo: QRect = window.geometry()
        window.close()
        XarrayDataTreeView.window_decoration_offset = QPoint(frame.x() - geo.x(), frame.y() - geo.y())
    
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
    
    def expandAll(self) -> None:
        QTreeView.expandAll(self)
        # store current expanded depth
        self._expanded_depth = self.model().depth()
    
    def collapseAll(self) -> None:
        QTreeView.collapseAll(self)
        self._expanded_depth = 0
    
    def expandToDepth(self, depth: int) -> None:
        depth = max(0, min(depth, self.model().depth()))
        if depth == 0:
            self.collapseAll()
            return
        QTreeView.expandToDepth(self, depth - 1)
        self._expanded_depth = depth
    
    def resizeAllColumnsToContents(self) -> None:
        for col in range(self.model().columnCount()):
            self.resizeColumnToContents(col)
    
    def showAll(self) -> None:
        self.expandAll()
        self.resizeAllColumnsToContents()
    
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
    
    # def truncateLabel(self, label: str, max_length: int = 50) -> str:
    #     """ Truncate long strings from the beginning.
        
    #     e.g., '...<end of label>'
    #     This preserves the final part of any tree paths used as labels.
    #     """
    #     if len(label) <= max_length:
    #         return label
    #     return '...' + label[-(max_length - 3):]
    
    def eventFilter(self, obj: QObject, event: QEvent) -> None:
        if event.type() == QEvent.Type.Wheel:
            modifiers: Qt.KeyboardModifier = event.modifiers()
            if Qt.KeyboardModifier.ControlModifier in modifiers \
            or Qt.KeyboardModifier.AltModifier in modifiers \
            or Qt.KeyboardModifier.MetaModifier in modifiers:
                self.mouseWheelEvent(event)
                return True
        # elif event.type() == QEvent.Type.KeyPress:
        #     event: QKeyEvent = event
        #     modifiers: Qt.KeyboardModifier = event.modifiers()
        #     if Qt.KeyboardModifier.ControlModifier in modifiers:
        #         if event.key() == Qt.Key.Key_C:
        #             self.copySelection()
        #             return True
        #         elif event.key() == Qt.Key.Key_V:
        #             self.pasteCopiedItems()
        #             return True
        # elif event.type() == QEvent.Type.FocusIn:
        #     print('FocusIn')
        #     # self.showDropIndicator(True)
        # elif event.type() == QEvent.Type.FocusOut:
        #     print('FocusOut')
        #     # self.showDropIndicator(False)
        return QTreeView.eventFilter(self, obj, event)
    
    def mouseWheelEvent(self, event: QWheelEvent) -> None:
        delta: int = event.angleDelta().y()
        depth = getattr(self, '_expanded_depth', 0)
        if delta > 0:
            self.expandToDepth(depth + 1)
        elif delta < 0:
            self.expandToDepth(depth - 1)
    
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
    
    def setDragAndDropEnabled(self, enabled: bool) -> None:
        if enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.viewport().setAcceptDrops(enabled)
        self.setDropIndicatorShown(enabled)
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        print('dragEnterEvent...')
        # self.storeState()
        # mime_data = event.mimeData()
        # if isinstance(mime_data, XarrayDataTreeMimeData) and mime_data.model is self.model():
        #     # Store the current state of the dragged paths and all their descendent paths in the MIME data.
        #     # We only want to do this for the model where the drag was initiated (i.e., mime_data.model).
        #     # We'll use this stored state in the dropEvent to restore the view of the dropped items.
        #     state: dict[str, dict] = getattr(self, self.STATE_KEY, {})
        #     dragged_paths: list[str] = mime_data.paths
        #     for dragged_path in dragged_paths:
        #         for path in state:
        #             if path.startswith(dragged_path) and path not in mime_data.src_view_state:
        #                 mime_data.src_view_state[path] = state[path]
        #     # import json
        #     # print('src_view_state')
        #     # print(json.dumps(mime_data.src_view_state, indent=2))
        QTreeView.dragEnterEvent(self, event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        print('dropEvent...')
        data: XarrayDataTreeMimeData = event.mimeData()
        if not isinstance(data, XarrayDataTreeMimeData):
            event.ignore()
            return

        src_model: XarrayDataTreeModel = data.src_model
        src_items: list[XarrayDataTreeItem] = data.src_items
        dst_model: XarrayDataTreeModel = self.model()
        if not src_model or not src_items or not dst_model:
            event.ignore()
            return
        
        # set dst_row and dst_parent_index based on drop position
        dst_index: QModelIndex = self.indexAt(event.pos())
        dst_row = dst_index.row()
        drop_pos = self.dropIndicatorPosition()
        if drop_pos == QAbstractItemView.DropIndicatorPosition.OnViewport:
            dst_parent_index = QModelIndex()
            dst_row = dst_model.rowCount(dst_parent_index)
        elif drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            dst_parent_index = dst_index
            dst_row = dst_model.rowCount(dst_parent_index)
        elif drop_pos == QAbstractItemView.DropIndicatorPosition.AboveItem:
            dst_parent_index: QModelIndex = dst_model.parent(dst_index)
        elif drop_pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
            dst_parent_index: QModelIndex = dst_model.parent(dst_index)
            dst_row += 1
        dst_parent_item: XarrayDataTreeItem = dst_model.itemFromIndex(dst_parent_index)
        
        # store drop locaiton in mime data
        data.dst_model = dst_model
        data.dst_parent_item = dst_parent_item
        data.dst_row = dst_row

        # handle drop event
        QTreeView.dropEvent(self, event)

        # TODO: update view state of dragged items and all their descendents as specified in the mime data
        # state = getattr(self, self.STATE_KEY, {})
        # for path, path_state in mime_data.dst_view_state.items():
        #     state[path] = path_state
        # setattr(self, self.STATE_KEY, state)
        # self.restoreState()
    
    # def dropMimeData(self, index: QModelIndex, data: QMimeData, action: Qt.DropAction) -> bool:
    #     print('dropMimeData...')
    #     return False
    
    # def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
    #     print('canDropMimeData...')
    #     return True


def test_live():
    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inhertis'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['child3/rasm'] = xr.tutorial.load_dataset('rasm')
    # dt['child1/air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    # print(dt)

    app = QApplication()
    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(False)
    model.setDatatree(dt)
    view = XarrayDataTreeView()
    view.setModel(model)
    view.show()
    view.resize(800, 800)
    view.showAll()
    app.exec()
    # print(dt)


if __name__ == '__main__':
    test_live()
