""" Tree view for `AbstractTreeModel` with context menu and mouse wheel expand/collapse.
"""

from __future__ import annotations
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph import AbstractTreeItem, AbstractTreeModel, AbstractTreeMimeData


class TreeView(QTreeView):

    selectionWasChanged = Signal()
    wasRefreshed = Signal()

    _window_decoration_offset: QPoint = None

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
        self.customContextMenuRequested.connect(self._onCustomContextMenuRequested)

        # persistent view state
        self._view_state: dict[str, dict] = {}

        # actions
        self._initActions()
    
    def _initActions(self) -> None:

        self._refreshAction = QAction(
            text = 'Refresh',
            icon = qta.icon('msc.refresh'),
            iconVisibleInMenu=True,
            toolTip = 'Refresh UI',
            shortcut=QKeySequence.StandardKey.Refresh,
            triggered = lambda checked: self.refresh()
        )

        self._selectAllAction = QAction(
            text = 'Select All',
            toolTip = 'Select all',
            shortcut=QKeySequence.StandardKey.SelectAll,
            triggered = lambda checked: self.selectAll()
        )

        self._clearSelectionAction = QAction(
            text = 'Clear Selection',
            toolTip = 'Clear selection',
            triggered = lambda checked: self.clearSelection()
        )

        self._removeSelectedAction = QAction(
            text = 'Remove',
            toolTip = 'Remove selected',
            triggered = lambda checked: self.removeSelectedItems()
        )

        self._expandAllAction = QAction(
            text = 'Expand All',
            toolTip = 'Expand all',
            triggered = lambda checked: self.expandAll()
        )

        self._collapseAllAction = QAction(
            text = 'Collapse All',
            toolTip = 'Collapse all',
            triggered = lambda checked: self.collapseAll()
        )

        self._resizeAllColumnsToContentsAction = QAction(
            text = 'Resize Columns to Contents',
            toolTip = 'Resize all columns to contents',
            triggered = lambda checked: self.resizeAllColumnsToContents()
        )

        self._showAllAction = QAction(
            text = 'Show All',
            toolTip = 'Expand all and resize all columns to contents',
            triggered = lambda checked: self.showAll()
        )
    
    def refresh(self) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        self.storeViewState()
        model.reset()
        self.restoreViewState()
        self.wasRefreshed.emit()
    
    def forgetViewState(self) -> None:
        self._view_state = {}
    
    def storeViewState(self, items: list[AbstractTreeItem] = None) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        if items is None:
            items = list(model.rootItem().subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        
        item: AbstractTreeItem
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

    def restoreViewState(self, items: list[AbstractTreeItem] = None) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        if not self._view_state:
            return
        if items is None:
            items = list(model.rootItem().subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        to_be_selected: QItemSelection = QItemSelection()
        to_be_deselected: QItemSelection = QItemSelection()
        
        item: AbstractTreeItem
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
        
        if to_be_selected.count():
            self.selectionModel().select(to_be_selected, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if to_be_deselected.count():
            self.selectionModel().select(to_be_deselected, QItemSelectionModel.SelectionFlag.Deselect | QItemSelectionModel.SelectionFlag.Rows)
    
    @Slot(QItemSelection, QItemSelection)
    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        QTreeView.selectionChanged(self, selected, deselected)
        self.selectionWasChanged.emit()

    def selectedItems(self) -> list[AbstractTreeItem]:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        # get unique items from indexes
        items: list[AbstractTreeItem] = []
        
        index: QModelIndex
        for index in indexes:
            item: AbstractTreeItem = model.itemFromIndex(index)
            if item not in items:
                items.append(item)
        
        return items
    
    def setSelectedItems(self, items: list[AbstractTreeItem]):
        model: AbstractTreeModel = self.model()
        if not model:
            return
        self.selectionModel().clearSelection()
        selection: QItemSelection = QItemSelection()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        
        item: AbstractTreeItem
        for item in items:
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            selection.merge(QItemSelection(index, index), flags)
        
        if selection.count():
            self.selectionModel().select(selection, flags)
    
    def removeSelectedItems(self, ask: bool = True) -> None:
        items: list[AbstractTreeItem] = self.selectedItems()
        if not items:
            return
        if len(items) == 1:
            text = f'Remove {items[0].path}?'
        else:
            text = 'Remove selected?'
        self.removeItems(items, ask, text)
    
    def removeItems(self, items: list[AbstractTreeItem], ask: bool = True, text: str = None) -> None:
        if not items:
            return
        model: AbstractTreeModel = self.model()
        if not model:
            return
        if ask:
            parent_widget: QWidget = self
            title = 'Remove'
            if text is None:
                if len(items) == 1:
                    text = f'Remove {items[0].path}?'
                else:
                    text = f'Remove {len(items)} items?'
            answer = QMessageBox.question(parent_widget, title, text, 
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                defaultButton=QMessageBox.StandardButton.No
            )
            if answer!= QMessageBox.StandardButton.Yes:
                return
        model.removeItems(items)
    
    @Slot(QPoint)
    def _onCustomContextMenuRequested(self, point: QPoint) -> None:
        index: QModelIndex = self.indexAt(point)
        menu: QMenu = self.customContextMenu(index)
        if menu:
            menu.exec(self.viewport().mapToGlobal(point))
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: AbstractTreeModel = self.model()
        menu = QMenu(self)
        
        # selection
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu._selectionSeparatorAction = menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # expand/collapse
        menu._expandSeparatorAction = menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # refresh
        menu._refreshSeparatorAction = menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    @staticmethod
    def _getWindowDecorationOffset():
        window = QWidget()
        window.show()
        frame: QRect = window.frameGeometry()
        geo: QRect = window.geometry()
        window.close()
        TreeView._window_decoration_offset = QPoint(frame.x() - geo.x(), frame.y() - geo.y())
    
    def expandAll(self) -> None:
        QTreeView.expandAll(self)
        # store current expanded depth
        model: AbstractTreeModel = self.model()
        if model:
            self._expanded_depth = model.depth()
    
    def collapseAll(self) -> None:
        QTreeView.collapseAll(self)
        self._expanded_depth = 0
    
    def expandToDepth(self, depth: int) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        depth = max(0, min(depth, model.depth()))
        if depth == 0:
            self.collapseAll()
            return
        QTreeView.expandToDepth(self, depth - 1)
        self._expanded_depth = depth
    
    def resizeAllColumnsToContents(self) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        for col in range(model.columnCount()):
            self.resizeColumnToContents(col)
    
    def showAll(self) -> None:
        self.expandAll()
        self.resizeAllColumnsToContents()
    
    def eventFilter(self, obj: QObject, event: QEvent) -> None:
        if event.type() == QEvent.Type.Wheel:
            # mouse wheel with modifier key pressed --> expand/collapse tree
            modifiers: Qt.KeyboardModifier = event.modifiers()
            if Qt.KeyboardModifier.ControlModifier in modifiers \
            or Qt.KeyboardModifier.AltModifier in modifiers \
            or Qt.KeyboardModifier.MetaModifier in modifiers:
                self.mouseWheelEvent(event)
                return True
        return QTreeView.eventFilter(self, obj, event)
    
    def mouseWheelEvent(self, event: QWheelEvent) -> None:
        delta: int = event.angleDelta().y()
        depth = getattr(self, '_expanded_depth', 0)
        if delta > 0:
            self.expandToDepth(depth + 1)
        elif delta < 0:
            self.expandToDepth(depth - 1)
    
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
        data: AbstractTreeMimeData = event.mimeData()

        # gather all items being dragged (includes descendents in subtrees)
        dragged_items: list[AbstractTreeItem] = []
        src_item: AbstractTreeItem
        for src_item in data.src_items:
            subtree_items = list(src_item.subtree_depth_first())
            item: AbstractTreeItem
            for item in subtree_items:
                if item not in dragged_items:
                    dragged_items.append(item)
        
        # keep track of full list of dragged subtrees in mime data
        data._dragged_items = dragged_items

        # store view state of all dragged items in the items themselves
        self.storeViewState(dragged_items)
        for item in dragged_items:
            item._view_state = self._view_state[item.path]

        QTreeView.dragEnterEvent(self, event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        data: AbstractTreeMimeData = event.mimeData()
        if not isinstance(data, AbstractTreeMimeData):
            event.ignore()
            return

        src_model: AbstractTreeModel = data.src_model
        src_items: list[AbstractTreeItem] = data.src_items
        dst_model: AbstractTreeModel = self.model()
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
        dst_parent_item: AbstractTreeItem = dst_model.itemFromIndex(dst_parent_index)
        
        # store drop locaiton in mime data
        data.dst_model = dst_model
        data.dst_parent_item = dst_parent_item
        data.dst_row = dst_row

        # handle drop event
        QTreeView.dropEvent(self, event)

        # update view state of dragged items and all their descendents as specified in the mime data
        # only updated wether items are expanded, selection should be handled already in drag-n-drop
        dragged_items: list[AbstractTreeItem] = getattr(data, '_dragged_items', [])
        item: AbstractTreeItem
        for item in dragged_items:
            index: QModelIndex = dst_model.indexFromItem(item)
            if not index.isValid():
                continue
            item_view_state = getattr(item, '_view_state', None)
            if item_view_state is None:
                continue
            is_expanded = item_view_state['expanded']
            self.setExpanded(index, is_expanded)
            # assume selection is already handled in drag-n-drop
    
    # def dropMimeData(self, index: QModelIndex, data: QMimeData, action: Qt.DropAction) -> bool:
    #     print('dropMimeData...')
    #     return False
    
    # def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
    #     print('canDropMimeData...')
    #     return True


def test_live():
    import faulthandler
    faulthandler.enable()
    
    class MyTreeItem(AbstractTreeItem):

        def __init__(self, name: str = '', parent: AbstractTreeItem = None, sibling_index: int = -1):
            super().__init__(parent, sibling_index)
            self._name = name
        
        @property
        def name(self) -> str:
            return self._name

    root = MyTreeItem('r')
    a = MyTreeItem('a', parent=root)
    b = MyTreeItem('b')
    c = MyTreeItem('c')
    d = MyTreeItem('d')
    e = MyTreeItem('e', parent=b)
    f = MyTreeItem('f', parent=e)
    root.append_child(b)
    root.insert_child(1, c)
    root.children[1].append_child(d)
    print(root)

    app = QApplication()

    model = AbstractTreeModel()
    model.setRootItem(root)

    view = TreeView()
    view.setModel(model)
    view.show()
    view.resize(800, 1000)
    view.showAll()
    view.move(100, 50)
    view.raise_()

    app.exec()
    print(root)


if __name__ == '__main__':
    test_live()
