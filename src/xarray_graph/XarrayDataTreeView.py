""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- restore state of dragged items in dropEvent
- rename dimensions
"""

from __future__ import annotations
from typing import Callable
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
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

        # These menu action (text, function(path), type) tuples will be used to populate each item's context menu.
        # If {item} is in the text, it will be replaced by the item's tree path.
        # If text includes '/', create a submenu (nested submenus are NOT supported).
        # '---' without any function is treated as a separator.
        # The callback function should take the item's datatree path as its sole argument.
        # If type is not None, only include this action for items of that type.
        self._itemContextMenuFunctions: list[tuple[str, Callable[[str]]]] = [
            ('{item}/Info', lambda path, self=self: self.popupInfo(path), None),
            ('{item}/Attrs', lambda path, self=self: self.editAttrs(path), None),
            ('{item}/---', None, None),
            ('{item}/Rename Dimensions', None, None),
            ('{item}/---', None, None),
            ('{item}/Remove', lambda path, self=self: self.removePath(path), None),
            ('---', None, None), # to separate this stuff from the rest of the default context menu
        ]

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

        # context menu for item that was clicked on
        if index.isValid() and len(self._itemContextMenuFunctions) > 0:
            dt: xr.DataTree = model.datatree()
            path: str = model.pathFromIndex(index)
            label = self.truncateLabel(path)
            submenus: dict[str, QMenu] = {}
            for key, func, item_type in self._itemContextMenuFunctions:
                if item_type is not None:
                    obj = dt[path]
                    if not isinstance(obj, item_type):
                        continue
                
                submenu_name = ''
                if '/' in key:
                    submenu_name, key = key.split('/')
                if '{item}' in submenu_name:
                    submenu_name = submenu_name.replace('{item}', label)
                if '{item}' in key:
                    key = key.replace('{item}', label)
                item_menu = menu
                if submenu_name:
                    if submenu_name not in submenus:
                        submenus[submenu_name] = menu.addMenu(submenu_name)
                    item_menu = submenus[submenu_name]
                
                if key == '---' and func is None:
                    item_menu.addSeparator()
                elif func:
                    item_menu.addAction(key, lambda path=path, func=func: func(path))
                else:
                    action = item_menu.addAction(key)
                    action.setEnabled(False)
        
        menu.addAction('Expand All', self.expandAll)
        menu.addAction('Collapse All', self.collapseAll)
        if model.columnCount() > 1:
            menu.addAction('Resize Columns to Contents', self.resizeAllColumnsToContents)
            menu.addAction('Show All', self.showAll)
        
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction('Select All', self.selectAll)
            menu.addAction('Select None', self.clearSelection)
        
        if len(self.selectedPaths()) > 1:
            menu.addSeparator()
            menu.addAction('Remove Selected', self.removeSelectedPaths)

        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showDetailsColumnAction)
        menu.addSeparator()
        menu.addAction('Refresh', self.refresh)
        
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
        
        attrs = kvmodel.root().value
        obj.attrs = attrs
        
        self.finishedEditingAttrs.emit()
    
    def eventFilter(self, obj: QObject, event: QEvent) -> None:
        if event.type() == QEvent.Type.Wheel:
            # modifiers: Qt.KeyboardModifier = event.modifiers()
            # if Qt.KeyboardModifier.ControlModifier in modifiers \
            # or Qt.KeyboardModifier.AltModifier in modifiers \
            # or Qt.KeyboardModifier.MetaModifier in modifiers:
            #     self.mouseWheelEvent(event)
            #     return True
            self.mouseWheelEvent(event)
            return True
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
            state = getattr(self, self.STATE_KEY, {})
            dragged_paths: list[str] = mime_data.paths
            for dragged_path in dragged_paths:
                for path in state:
                    if dragged_path.startswith(path) and path not in mime_data.view_state:
                        mime_data.view_state[path] = state[path]
        QTreeView.dragEnterEvent(self, event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        mime_data = event.mimeData()
        QTreeView.dropEvent(self, event)
        if isinstance(mime_data, XarrayDataTreeMimeData):
            # update state of dragged items as specified in the MIME data
            mime_data.view_state
            mime_data.drop_path_map
            # TODO...
        self.restoreState()


def test_live():
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child1/twice air'] = dt['child1/air'] * 2
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.tutorial.load_dataset('tiny')
    dt['child3/grandchild2'] = xr.tutorial.load_dataset('rasm')
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
