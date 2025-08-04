""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- global rename of variables throughout the entire branch or tree?
"""

from __future__ import annotations
from typing import Callable
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.xarray_utils import *
from xarray_graph import XarrayDataTreeModel, XarrayDataTreeMimeData
from pyqt_ext.tree import KeyValueTreeItem, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeView(QTreeView):

    selectionWasChanged = Signal()
    finishedEditingAttrs = Signal()

    STATE_KEY = '_state_'

    def __init__(self, parent: QObject = None) -> None:
        QTreeView.__init__(self, parent)

        # general settings
        sizePolicy = self.sizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(sizePolicy)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        # self.setAlternatingRowColors(True)

        # selection
        # self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # drag-n-drop
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
            checked = True,
            toolTip = 'Show coords in the tree view. Uncheck to hide them.',
            triggered = self._updateModelFromViewOptions
        )

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            icon = qta.icon('ph.list-numbers-thin'),
            checkable = True,
            checked = False,
            toolTip = 'Show inherited coords in the tree view. Uncheck to hide them.',
            triggered = self._updateModelFromViewOptions
        )

        # optional details column
        self._showDetailsColumnAction = QAction(
            text = 'Show Details Column',
            checkable = True,
            checked = True,
            toolTip = 'Show details column in the tree view. Uncheck to hide column.',
            triggered = self._updateModelFromViewOptions
        )
    
    def refresh(self) -> None:
        self.storeState()
        self.model().reset()
        self.restoreState()
    
    def model(self) -> XarrayDataTreeModel:
        model: XarrayDataTreeModel = super().model()
        return model
    
    def setModel(self, model: XarrayDataTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        QTreeView.setModel(self, model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model: XarrayDataTreeModel = self.model()
        if model is None:
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
        
        self._showDetailsColumnAction.blockSignals(True)
        self._showDetailsColumnAction.setChecked(model.isDetailsColumnVisible())
        self._showDetailsColumnAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        
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
            self.setModel(XarrayDataTreeModel(datatree), updateViewOptionsFromModel=False)
        else:
            self.model().setDatatree(datatree)
        self.restoreState()
    
    def storeState(self) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree = model.datatree()
        if dt is None:
            return
        
        state = getattr(self, self.STATE_KEY, {})
        selected: list[QModelIndex] = self.selectionModel().selectedIndexes()
        node: xr.DataTree
        for node in dt.subtree:
            if node is dt:
                continue
            paths: list[str] = [node.path]
            for name in model.visibleRowNames(node):
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
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree = model.datatree()
        if dt is None:
            return
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
            for name in model.visibleRowNames(node):
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

    def selectedPaths(self) -> list[str]:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return []
        indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        paths: list[str] = []
        for index in indexes:
            path: str = model.pathFromIndex(index)
            if path not in paths:
                paths.append(path)
        return paths
    
    def setSelectedPaths(self, paths: list[str]):
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        self.selectionModel().clearSelection()
        selection: QItemSelection = QItemSelection()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for path in paths:
            index: QModelIndex = model.indexFromPath(path)
            if not index.isValid():
                continue
            selection.merge(QItemSelection(index, index), flags)
        if selection.count():
            self.selectionModel().select(selection, flags)
    
    def removePath(self, path: str, ask: bool = True) -> None:
        if ask:
            answer = QMessageBox.question(self, 'Remove', f'Remove {path}?', 
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                defaultButton=QMessageBox.StandardButton.No
            )
            if answer!= QMessageBox.StandardButton.Yes:
                return
        self.model().removePaths([path])
    
    def removeSelectedPaths(self, ask: bool = True) -> None:
        paths: list[str] = self.selectedPaths()
        if not paths:
            return
        if ask:
            answer = QMessageBox.question(self, 'Remove', f'Remove selected?', 
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                defaultButton=QMessageBox.StandardButton.No
            )
            if answer!= QMessageBox.StandardButton.Yes:
                return
        self.model().removePaths(paths)
    
    def renameDimensions(self, path: str = None) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree = model.datatree()
        if dt is None:
            return
        node: xr.DataTree | xr.DataArray = dt[path]
        if isinstance(node, xr.DataArray):
            path = model.parentPath(path)
            node: xr.DataTree = dt[path]
        
        dims = []
        subnode: xr.DataTree
        for subnode in node.subtree:
            for dim in subnode.dims:
                if dim not in dims:
                    dims.append(dim)
        if not dims:
            QMessageBox.warning(self, 'Rename Dimensions', f'No dimensions found in subtree at {path}.')
            return
        
        dim_editors: dict[str, QLineEdit] = {dim: QLineEdit(dim) for dim in dims}

        dlg = QDialog(self)
        dlg.setWindowTitle('Rename Dimensions')
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        form = QFormLayout(dlg)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for dim, editor in dim_editors.items():
            form.addRow(f'{dim} ->', editor)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        self.storeState()
        self.model().beginResetModel()
        # print(node)
        subnode: xr.DataTree
        for subnode in node.subtree:
            old_dims = list(subnode.dims)
            new_dims = [dim_editors[dim].text() if dim in dim_editors else dim for dim in old_dims]
            dim_map = {old: new for old, new in zip(old_dims, new_dims) if old != new}
            if dim_map:
                subnode.dataset = subnode.to_dataset().rename(dim_map)
        # print(node)
        self.model().endResetModel()
        self.restoreState()
    
    def copySelection(self) -> None:
        """ Copy selected items.
        """
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree = model.datatree()
        if dt is None:
            return
        
        paths: list[str] = self.selectedPaths()
        root_paths: list[str] = []
        for path in paths:
            ok = True
            for check_path in paths:
                if check_path == path:
                    continue
                if path.startswith(check_path):
                    # path is a descendant of check_path
                    ok = False
                    break
            if ok:
                root_paths.append(path)
        
        self._copied_nodes: list[xr.DataTree] = []
        self._copied_vars: list[xr.DataArray] = []
        self._copied_coords: list[xr.DataArray] = []
        for path in root_paths:
            obj: xr.DataTree | xr.DataArray = dt[path]
            copied_obj = obj.copy(deep=True)
            if isinstance(obj, xr.DataTree) and obj.parent is not None:
                # copy inherited coords
                inherited_coords_copy = {name: obj.parent.coords[name].copy(deep=True) for name in obj._inherited_coords_set()}
                if inherited_coords_copy:
                    copied_obj.dataset = copied_obj.to_dataset().assign_coords(inherited_coords_copy)
                self._copied_nodes.append(copied_obj)
            elif isinstance(obj, xr.DataArray):
                parent_path: str = model.parentPath(path)
                parent_node: xr.DataTree = dt[parent_path]
                if obj.name in parent_node.data_vars:
                    self._copied_vars.append(copied_obj)
                elif obj.name in parent_node.coords:
                    self._copied_coords.append(copied_obj)
    
    def pasteCopiedItems(self, parent_path: str = None) -> None:
        if parent_path is None:
            selected_paths = self.selectedPaths()
            if selected_paths:
                parent_path = selected_paths[0]
            else:
                parent_path = '/'

        copied_nodes: list[xr.DataTree] = getattr(self, '_copied_nodes', [])
        copied_vars: list[xr.DataTree] = getattr(self, '_copied_vars', [])
        copied_coords: list[xr.DataTree] = getattr(self, '_copied_coords', [])
        
        dt: xr.DataTree = self.datatree()
        parent: xr.DataTree | xr.DataArray = dt[parent_path]
        if isinstance(parent, xr.DataArray):
            parent_path = self.model().parentPath(parent_path)
            parent = dt[parent_path]
        parent_keys = list(parent.data_vars) + list(parent.coords) + list(parent.children)
        
        self.storeState()
        self.model().beginResetModel()
        for node in copied_nodes:
            node.name = XarrayDataTreeModel.uniqueName(node.name or '?', parent_keys)
            parent_keys += node.name
        if copied_nodes:
            children = {name: child for name, child in parent.children.items()}
            for node in copied_nodes:
                children[node.name] = node
            parent.children = children
        vars = {}
        for var in copied_vars:
            var.name = XarrayDataTreeModel.uniqueName(var.name or '?', parent_keys)
            vars[var.name] = var
            parent_keys += var.name
        if vars:
            parent.dataset = parent.to_dataset().assign(vars)
        coords = {coord.name: coord for coord in copied_coords}
        if coords:
            parent.dataset = parent.to_dataset().assign_coords(coords)
        self.model().endResetModel()
        self.restoreState()
    
    @Slot(QPoint)
    def onCustomContextMenuRequested(self, point: QPoint) -> None:
        index: QModelIndex = self.indexAt(point)
        menu: QMenu | None = self.customContextMenu(index)
        if menu is not None:
            menu.exec(self.viewport().mapToGlobal(point))
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu | None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        
        menu = QMenu(self)

        n_selected_items = len(self.selectedPaths())

        copied_nodes: list[xr.DataTree] = getattr(self, '_copied_nodes', [])
        copied_vars: list[xr.DataTree] = getattr(self, '_copied_vars', [])
        copied_coords: list[xr.DataTree] = getattr(self, '_copied_coords', [])
        n_copied_items = len(copied_nodes) + len(copied_vars) + len(copied_coords)

        # context menu for item that was clicked on
        path: str = model.pathFromIndex(index)
        dt: xr.DataTree = model.datatree()
        obj: xr.DataTree | xr.DataArray = dt[path]
        menu.addAction(f'{path}:').setEnabled(False)  # just a label, not clickable
        
        menu.addAction('Info', lambda path=path: self.popupInfo(path))
        menu.addAction('Attrs', lambda path=path: self.editAttrs(path))
        menu.addAction('Rename Dimensions', lambda path=path: self.renameDimensions(path)).setEnabled(isinstance(obj, xr.DataTree))
        
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction('Select All', self.selectAll)
            menu.addAction('Select None', self.clearSelection)
        
        menu.addSeparator()
        menu.addAction('Copy', self.copySelection).setEnabled(n_selected_items > 0)
        menu.addAction('Paste', lambda path=path: self.pasteCopiedItems(path)).setEnabled(n_copied_items > 0)
        
        # canRemove = index.isValid()
        # if canRemove:
        #     dt: xr.DataTree = model.datatree()
        #     obj = dt[path]
        #     if isinstance(obj, xr.DataArray):
        #         parentPath = model.parentPath(path)
        #         parent_node: xr.DataTree = dt[parentPath]
        #         canRemove = obj.name not in parent_node._inherited_coords_set()
        
        menu.addSeparator()
        # menu.addAction('Remove', lambda path=path: self.removePath(path)).setEnabled(canRemove)
        menu.addAction('Remove', self.removeSelectedPaths).setEnabled(n_selected_items > 0)
        
        menu.addSeparator()
        menu.addAction('Expand All', self.expandAll)
        menu.addAction('Collapse All', self.collapseAll)
        if model.columnCount() > 1:
            menu.addAction('Resize Columns to Contents', self.resizeAllColumnsToContents)
            menu.addAction('Show All', self.showAll)

        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showInheritedCoordsAction)
        menu.addAction(self._showDetailsColumnAction)
        menu.addSeparator()
        menu.addAction('Refresh UI', self.refresh)
        
        return menu
    
    def truncateLabel(self, label: str, max_length: int = 50) -> str:
        """ Truncate long strings from the beginning.
        
        e.g., '...<end of label>'
        This preserves the final part of any tree paths used as labels.
        """
        if len(label) <= max_length:
            return label
        return '...' + label[-(max_length - 3):]
    
    def expandAll(self) -> None:
        QTreeView.expandAll(self)
        # store current expanded depth
        self._expanded_depth_ = self.model().maxDepth()
    
    def collapseAll(self) -> None:
        QTreeView.collapseAll(self)
        self._expanded_depth_ = 0
    
    def expandToDepth(self, depth: int) -> None:
        depth = max(0, min(depth, self.model().maxDepth()))
        if depth == 0:
            self.collapseAll()
            return
        QTreeView.expandToDepth(self, depth - 1)
        self._expanded_depth_ = depth
    
    def resizeAllColumnsToContents(self) -> None:
        for col in range(self.model().columnCount()):
            self.resizeColumnToContents(col)
    
    def showAll(self) -> None:
        self.expandAll()
        self.resizeAllColumnsToContents()
    
    def popupInfo(self, path: str) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree | None = model.datatree()
        if dt is None:
            return
        obj = dt[path]
        text = str(obj)
        
        textEdit = QTextEdit()
        textEdit.setPlainText(text)
        textEdit.setReadOnly(True)

        dlg = QDialog(self)
        dlg.setWindowTitle(path)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(textEdit)
        dlg.exec()
    
    def editAttrs(self, path: str) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            return
        dt: xr.DataTree = model.datatree()
        if dt is None:
            return
        obj: xr.DataTree | xr.DataArray = dt[path]
        attrs = obj.attrs.copy()
        
        root = KeyValueTreeItem(attrs)
        kvmodel = KeyValueTreeModel(root)
        view = KeyValueTreeView()
        view.setAlternatingRowColors(True)
        view.setModel(kvmodel)
        view.expandAll()
        view.resizeAllColumnsToContents()

        dlg = QDialog(self)
        dlg.setWindowTitle(path)
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
        
        root: KeyValueTreeItem = kvmodel.rootItem()
        attrs: dict = root.value()
        obj.attrs = attrs
        
        self.finishedEditingAttrs.emit()
    
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
        depth = getattr(self, '_expanded_depth_', 0)
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
                self.pasteCopiedItems()
                return
        return super().keyPressEvent(event)
    
    def setDragAndDropEnabled(self, enabled: bool) -> None:
        if enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.viewport().setAcceptDrops(enabled)
        self.setDropIndicatorShown(enabled)
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        self.storeState()
        mime_data = event.mimeData()
        if isinstance(mime_data, XarrayDataTreeMimeData) and mime_data.model is self.model():
            # Store the current state of the dragged paths and all their descendent paths in the MIME data.
            # We only want to do this for the model where the drag was initiated (i.e., mime_data.model).
            # We'll use this stored state in the dropEvent to restore the view of the dropped items.
            state: dict[str, dict] = getattr(self, self.STATE_KEY, {})
            dragged_paths: list[str] = mime_data.paths
            for dragged_path in dragged_paths:
                for path in state:
                    if path.startswith(dragged_path) and path not in mime_data.src_view_state:
                        mime_data.src_view_state[path] = state[path]
            # import json
            # print('src_view_state')
            # print(json.dumps(mime_data.src_view_state, indent=2))
        QTreeView.dragEnterEvent(self, event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        mime_data = event.mimeData()
        QTreeView.dropEvent(self, event)
        if isinstance(mime_data, XarrayDataTreeMimeData):
            # update state of dragged items and all their descendents as specified in the MIME data
            # import json
            # print('dst_view_state')
            # print(json.dumps(mime_data.dst_view_state, indent=2))
            state = getattr(self, self.STATE_KEY, {})
            for path, path_state in mime_data.dst_view_state.items():
                state[path] = path_state
            setattr(self, self.STATE_KEY, state)
        self.restoreState()


def test_live():
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child1/twice air'] = dt['child1/air'] * 2
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.tutorial.load_dataset('tiny')
    dt['child3/grandchild2'] = xr.tutorial.load_dataset('rasm')
    dt['child1/child2'] = xr.tutorial.load_dataset('air_temperature_gradient')
    dt['child4'] = xr.tutorial.load_dataset('air_temperature_gradient')
    print(dt)

    app = QApplication()
    model = XarrayDataTreeModel(dt)
    view = XarrayDataTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 600))
    view.showAll()
    app.exec()
    print(dt)


if __name__ == '__main__':
    test_live()
