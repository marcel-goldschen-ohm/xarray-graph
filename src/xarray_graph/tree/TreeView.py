""" Qt tree view for `AbstractTreeModel` with context menu and mouse wheel expand/collapse.
"""
from __future__ import annotations

from typing import Type, Self, cast
from qtpy.QtCore import Signal, Slot  # type: ignore (pylance does not recognize some of qtpy's type aliases)
from qtpy.QtCore import Qt, QModelIndex, QItemSelection, QObject, QEvent, QPoint
from qtpy.QtGui import QKeyEvent, QWheelEvent, QDragEnterEvent, QDropEvent
from qtpy.QtWidgets import QTreeView
from xarray_graph.tree.AbstractTreeItem import AbstractTreeItem
from xarray_graph.tree.AbstractTreeModel import AbstractTreeModel

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from qtpy.QtWidgets import QMenu


class TreeView[TreeModel: AbstractTreeModel, TreeItem: AbstractTreeItem](QTreeView):
    """ Qt tree view for `AbstractTreeModel` with context menu and mouse wheel expand/collapse.

    Works out-of-the-box with any `AbstractTreeModel` and `AbstractTreeItem` implementation. Override the following methods to customize behavior:
    - setModel() - to connect model signals to view slots and update view options based on model properties
    - customContextMenu() - to provide a context menu for tree items. By default, the context menu includes actions for selecting, cutting/copying/pasting, removing, expanding/collapsing, and refreshing tree items.
    - eventFilter() - to customize event handling such as mouse wheel events for expanding/collapsing tree items. By default, mouse wheel with a modifier key pressed will expand/collapse tree items.
    - keyPressEvent() - to customize keyboard shortcuts. By default, supports shortcuts for selecting all, cutting/copying/pasting, removing, and refreshing tree items.
    """

    selectionWasChanged = Signal()
    wasRefreshed = Signal()

    # global list of copied items
    # check item type when pasting to ensure only items of the same type are pasted into a parent item
    _copied_items = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # general settings
        from qtpy.QtWidgets import QSizePolicy, QAbstractScrollArea
        sizePolicy = self.sizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        sizePolicy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(sizePolicy)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.setUniformRowHeights(True)
        self.setSortingEnabled(False)

        # selection
        from qtpy.QtWidgets import QAbstractItemView
        # self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # drag-n-drop
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragAndDropEnabled(True)

        # context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._onCustomContextMenuRequested)

        # Each item's view state (e.g. whether item is expanded, selected) will be stored in the item itself in a dict attribute called '_view_state' when the item is dragged or when storeViewState() is called. This allows the view state to be preserved when items are moved within the tree or between different tree views via drag-n-drop, or when the view is refreshed. Item view states are additionally stored in a single dict keyed on the item paths (note, for trees with non-unique item paths this will not work for all items). This allows view state to be preserved when the view is refreshed even if the items themselves are recreated (e.g., from data) such that the item view state attribute is lost.
        self._view_state: dict[str, dict] = {}

        # actions
        from qtpy.QtGui import QAction  # type: ignore (pylance does not recognize some of qtpy's type aliases)
        from qtpy.QtGui import QKeySequence
        import qtawesome as qta
        self._refreshAction = QAction(
            text='Refresh',
            icon=qta.icon('msc.refresh'),
            iconVisibleInMenu=True,
            toolTip='Refresh UI',
            shortcut=QKeySequence(QKeySequence.StandardKey.Refresh),
            shortcutVisibleInContextMenu=True
        )
        self._refreshAction.triggered.connect(lambda checked: self.refresh())

        self._selectAllAction = QAction(
            text='Select All',
            toolTip='Select all',
            shortcut=QKeySequence(QKeySequence.StandardKey.SelectAll),
            shortcutVisibleInContextMenu=True
        )
        self._selectAllAction.triggered.connect(lambda checked: self.selectAll())

        self._clearSelectionAction = QAction(
            text='Clear Selection',
            toolTip='Clear selection'
        )
        self._clearSelectionAction.triggered.connect(lambda checked: self.clearSelection())

        self._removeSelectedAction = QAction(
            text='Remove Selection',
            toolTip='Remove selected',
            shortcut=QKeySequence(QKeySequence.StandardKey.Delete),
            shortcutVisibleInContextMenu=True
        )
        self._removeSelectedAction.triggered.connect(lambda checked: self.removeSelectedItems())

        self._cutSelectionAction = QAction(
            text='Cut',
            icon=qta.icon('mdi.content-cut'),
            iconVisibleInMenu=True,
            toolTip='Cut selection',
            shortcut=QKeySequence(QKeySequence.StandardKey.Cut),
            shortcutVisibleInContextMenu=True
        )
        self._cutSelectionAction.triggered.connect(lambda checked: self.cutSelection())

        self._copySelectionAction = QAction(
            text='Copy',
            icon=qta.icon('mdi.content-copy'),
            iconVisibleInMenu=True,
            toolTip='Copy selection',
            shortcut=QKeySequence(QKeySequence.StandardKey.Copy),
            shortcutVisibleInContextMenu=True
        )
        self._copySelectionAction.triggered.connect(lambda checked: self.copySelection())

        self._pasteAction = QAction(
            text='Paste',
            icon=qta.icon('mdi.content-paste'),
            iconVisibleInMenu=True,
            toolTip='Paste copy',
            shortcut=QKeySequence(QKeySequence.StandardKey.Paste),
            shortcutVisibleInContextMenu=True
        )
        self._pasteAction.triggered.connect(lambda checked: self.pasteCopy())

        self._expandAllAction = QAction(
            text='Expand All',
            toolTip='Expand all'
        )
        self._expandAllAction.triggered.connect(lambda checked: self.expandAll())

        self._collapseAllAction = QAction(
            text='Collapse All',
            toolTip='Collapse all'
        )
        self._collapseAllAction.triggered.connect(lambda checked: self.collapseAll())

        self._resizeAllColumnsToContentsAction = QAction(
            text='Resize Columns to Contents',
            toolTip='Resize all columns to contents'
        )
        self._resizeAllColumnsToContentsAction.triggered.connect(lambda checked: self.resizeAllColumnsToContents())

        self._viewAllAction = QAction(
            text='View All',
            # icon=qta.icon('mdi6.arrow-expand-all'),
            # iconVisibleInMenu=True,
            toolTip='Expand all and resize all columns to contents',
            shortcut=QKeySequence('Ctrl+F'),
            shortcutVisibleInContextMenu=True
        )
        self._viewAllAction.triggered.connect(lambda checked: self.viewAll())
    
    def model(self) -> TreeModel:
        return cast(TreeModel, super().model())

    def setModel(self, model: TreeModel) -> None:
        super().setModel(model)
        model.refreshRequested.connect(self.refresh)
    
    def refresh(self) -> None:
        model = self.model()
        self.storeViewState()
        model.reset()
        self.restoreViewState()
        self.wasRefreshed.emit()
    
    def forgetViewState(self) -> None:
        self._view_state = {}
        model = self.model()
        root = cast(TreeItem, model.rootItem())
        for item in root.subtree_depth_first():
            item.setViewState({})
    
    def storeViewState(self, items: list[TreeItem] = None) -> None:
        model = self.model()
        if items is None:
            root = cast(TreeItem, model.rootItem())
            items = list(root.subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        for item in items:
            if item.isRoot():
                continue
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            view_state = item.viewState()
            view_state['expanded'] = self.isExpanded(index)
            view_state['selected'] = index in selected_indexes
            self._view_state[item.path()] = view_state

    def restoreViewState(self, items: list[TreeItem] = None) -> None:
        model = self.model()
        if items is None:
            root = cast(TreeItem, model.rootItem())
            items = list(root.subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        from qtpy.QtCore import QItemSelection, QItemSelectionModel
        to_be_selected: QItemSelection = QItemSelection()
        to_be_deselected: QItemSelection = QItemSelection()
        for item in items:
            if item.isRoot():
                continue
            view_state = item.viewState()
            if not view_state:
                try:
                    view_state: dict = self._view_state[item.path()]
                except KeyError:
                    continue
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            is_expanded = view_state.get('expanded', False)
            self.setExpanded(index, is_expanded)
            is_selected = view_state.get('selected', False)
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

    def selectedItems(self, ordered=False) -> list[TreeItem]:
        model = self.model()
        indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        # get unique items from indexes
        items: list[TreeItem] = []
        for index in indexes:
            item = model.itemFromIndex(index)
            if item not in items:
                items.append(item)
        if ordered:
            # return items in depth-first order
            ordered_items: list[TreeItem] = []
            root = cast(TreeItem, model.rootItem())
            for item in root.subtree_depth_first():
                if item in items:
                    ordered_items.append(item)
            items = ordered_items
        return items
    
    def setSelectedItems(self, items: list[TreeItem]):
        model = self.model()
        self.selectionModel().clearSelection()
        from qtpy.QtCore import QItemSelection, QItemSelectionModel
        selection: QItemSelection = QItemSelection()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        
        for item in items:
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            selection.merge(QItemSelection(index, index), flags)
        
        if selection.count():
            self.selectionModel().select(selection, flags)
    
    def removeSelectedItems(self, ask: bool = True) -> None:
        items: list[TreeItem] = self.selectedItems()
        if not items:
            return
        if len(items) == 1:
            text = f'Remove {items[0].path()}?'
        else:
            text = 'Remove selected?'
        self.removeItems(items, ask, text)
    
    def removeItems(self, items: list[TreeItem], ask: bool = True, text: str = None) -> None:
        if not items:
            return
        model = self.model()
        if ask:
            parent_widget = self
            title = 'Remove'
            if text is None:
                if len(items) == 1:
                    text = f'Remove {items[0].path()}?'
                else:
                    text = f'Remove {len(items)} items?'
            from qtpy.QtWidgets import QMessageBox
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
            pos = self.viewport().mapToGlobal(point)
            menu.exec(pos)
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        """ Example context menu.
        
        Override in a derived class with the specific actions you want.
        """
        model = self.model()

        from qtpy.QtWidgets import QMenu
        menu = QMenu(self)

        # item that was clicked on
        # item: TreeItem = model.itemFromIndex(index)
        # Add item-specific actions here if desired
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        self._clearSelectionAction.setEnabled(has_selection)
        from qtpy.QtWidgets import QAbstractItemView
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
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._viewAllAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items: list[TreeItem] = self.selectedItems()
        if not items:
            return
        # only copy the branch roots (this includes the descendents)
        model = self.model()
        items = model._branchRootItemsOnly(items)
        if not items:
            return
        all_items: list[TreeItem] = items[0].allItemsAndTheirDescendents(items)
        self.storeViewState(all_items)
        TreeView._copied_items = [item.copy() for item in items]
        for item in TreeView._copied_items:
            print(f'Copied item: {item.name()} with view state: {item.viewState()}')
    
    def pasteCopy(self, parent_item: TreeItem = None, row: int = None) -> None:
        if not self.hasCopy():
            return
        model = self.model()
        try:
            if parent_item is None:
                selected_items = self.selectedItems()
                if selected_items:
                    parent_item = selected_items[0]
                else:
                    parent_item = cast(TreeItem, model.rootItem())
            if row is None or row == -1:
                if parent_item is None:
                    return
                row = len(parent_item.children)
            items: list[TreeItem] = [cast(TreeItem, item).copy() for item in TreeView._copied_items if isinstance(item, type(parent_item))]
            for item in items:
                print(f'Pasting item: {item.name()} with view state: {item.viewState()}')
            if not items:
                # in case attempt to paste items of a different type than the parent item
                return
            model.insertItems(items, row, parent_item)
            # update view state of pasted items and all their descendents as specified in the copied items
            all_items: list[TreeItem] = items[0].allItemsAndTheirDescendents(items)
            self.restoreViewState(all_items)
        except Exception as err:
            from qtpy.QtWidgets import QApplication, QMessageBox
            focus_widget = QApplication.focusWidget()
            QMessageBox.warning(focus_widget, 'Error', f'Error pasting items: {err}')
    
    def hasCopy(self) -> bool:
        return len(TreeView._copied_items) > 0
    
    def expandAll(self) -> None:
        QTreeView.expandAll(self)
        # store current expanded depth
        model = self.model()
        self._expanded_depth = model.depth()
    
    def collapseAll(self) -> None:
        QTreeView.collapseAll(self)
        self._expanded_depth = 0
    
    def expandToDepth(self, depth: int) -> None:
        model = self.model()
        depth = max(0, min(depth, model.depth()))
        if depth == 0:
            self.collapseAll()
            return
        QTreeView.expandToDepth(self, depth - 1)
        self._expanded_depth = depth
    
    def resizeAllColumnsToContents(self) -> None:
        model = self.model()
        for col in range(model.columnCount()):
            self.resizeColumnToContents(col)
    
    def viewAll(self) -> None:
        self.expandAll()
        self.resizeAllColumnsToContents()
    
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            # mouse wheel with modifier key pressed --> expand/collapse tree
            event = cast(QWheelEvent, event)
            modifiers: Qt.KeyboardModifier = event.modifiers()
            if Qt.KeyboardModifier.ControlModifier in modifiers \
            or Qt.KeyboardModifier.AltModifier in modifiers \
            or Qt.KeyboardModifier.MetaModifier in modifiers:
                self.mouseWheelEvent(event)
                return True
        # process the event normally
        return QTreeView.eventFilter(self, obj, event)
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        from qtpy.QtCore import Qt
        from qtpy.QtGui import QKeySequence

        if event.key() in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            self.removeSelectedItems()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Cut):
            self.cutSelection()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.copySelection()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.pasteCopy()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Refresh):
            self.refresh()
            event.accept()
            return

        modifiers = event.modifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.viewAll()
            event.accept()
            return

        # process the event normally
        return super().keyPressEvent(event)
    
    def mouseWheelEvent(self, event: QWheelEvent) -> None:
        # expand/collapse tree based on mouse wheel direction
        # !! this is handled in eventFilter() where a modifier key is also required to trigger this event
        delta: int = event.angleDelta().y()
        depth = getattr(self, '_expanded_depth', 0)
        if delta > 0:
            self.expandToDepth(depth + 1)
        elif delta < 0:
            self.expandToDepth(depth - 1)
    
    def setDragAndDropEnabled(self, enabled: bool) -> None:
        from qtpy.QtWidgets import QAbstractItemView
        if enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.viewport().setAcceptDrops(enabled)
        self.setDropIndicatorShown(enabled)
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        from xarray_graph.tree.AbstractTreeModel import TreeMimeData

        mime_data = event.mimeData()
        if isinstance(mime_data, TreeMimeData):
            mime_data = cast(TreeMimeData[TreeModel, TreeItem], mime_data)
            # handle drag enter event for tree items
            if not hasattr(mime_data, '_dragged_items'):
                # gather all items being dragged (includes descendents in subtrees)
                # !!! Only do this at the start of the drag, do not repeat on subsequent dragEnterEvents such as when dragging between views.
                dragged_items: list[TreeItem] = []
                for src_item in mime_data.src_items:
                    for item in src_item.subtree_depth_first():
                        if item not in dragged_items:
                            dragged_items.append(item)
                
                # keep track of full list of dragged items (plus their descendents) in mime data
                setattr(mime_data, '_dragged_items', dragged_items)

                # store view state of all dragged items in the items themselves
                self.storeViewState(dragged_items)

        # alsways call the base class implementation to ensure the drag works properly
        QTreeView.dragEnterEvent(self, event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        from xarray_graph.tree.AbstractTreeModel import TreeMimeData

        mime_data = event.mimeData()
        if not isinstance(mime_data, TreeMimeData):
            event.ignore()
            return

        mime_data = cast(TreeMimeData[TreeModel, TreeItem], mime_data)
        src_model: TreeModel = mime_data.src_model
        src_items: list[TreeItem] = mime_data.src_items
        dst_model = self.model()
        if not src_model or not src_items or not isinstance(dst_model, AbstractTreeModel):
            event.ignore()
            return
        
        # set dst_row and dst_parent_index based on drop position
        dst_index: QModelIndex = self.indexAt(event.pos())
        dst_row = dst_index.row()
        drop_pos = self.dropIndicatorPosition()
        from qtpy.QtWidgets import QAbstractItemView
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
        dst_parent_item: TreeItem = dst_model.itemFromIndex(dst_parent_index)
        
        # store drop location in mime data
        mime_data.dst_model = dst_model
        mime_data.dst_parent_item = dst_parent_item
        mime_data.dst_row = dst_row

        # handle drop event
        QTreeView.dropEvent(self, event)
        
        # update view state of dragged items and all their descendents as specified in the mime data
        # only update wether items are expanded, selection should be handled already in drag-n-drop
        dragged_items: list[TreeItem] = getattr(mime_data, '_dragged_items', [])
        for item in dragged_items:
            index: QModelIndex = dst_model.indexFromItem(item)
            if not index.isValid():
                continue
            view_state: dict = item.viewState()
            is_expanded = view_state['expanded'] # should be defined
            self.setExpanded(index, is_expanded)
            # assume selection is already handled in drag-n-drop
    
    # def dropMimeData(self, index: QModelIndex, data: QMimeData, action: Qt.DropAction) -> bool:
    #     print('dropMimeData...')
    #     return False
    
    # def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
    #     print('canDropMimeData...')
    #     return True


def test_live():
    from qtpy.QtWidgets import QApplication
    
    class MyTreeItem(AbstractTreeItem):

        def __init__(self, data: str = '', parent: Self | None = None, sibling_index: int = -1):
            super().__init__(parent, sibling_index)
            self.data = data
        
        def name(self) -> str:
            return self.data

        def setName(self, name: str) -> None:
            self.data = name
    
    app = QApplication()

    for i in range(2):
        root = MyTreeItem(f'r{i}')
        a = MyTreeItem(f'a{i}', parent=root)
        b = MyTreeItem(f'b{i}')
        c = MyTreeItem(f'c{i}')
        d = MyTreeItem(f'd{i}')
        e = MyTreeItem(f'e{i}', parent=b)
        f = MyTreeItem(f'f{i}', parent=e)
        ff = MyTreeItem(f'ff{i}', parent=e)
        fff = MyTreeItem(f'fff{i}', parent=e)
        g = MyTreeItem(f'g{i}', parent=d)
        root.appendChild(b)
        root.insertChild(1, c)
        root.children[1].appendChild(d)

        model = AbstractTreeModel[MyTreeItem](root)
        view = TreeView[AbstractTreeModel, MyTreeItem]()
        view.setModel(model)
        view.show()
        view.resize(800, 1000)
        view.viewAll()
        view.move(50 + i * 850, 50)
        view.raise_()

    app.exec()


if __name__ == '__main__':
    test_live()
