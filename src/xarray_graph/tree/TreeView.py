""" Qt tree view for `AbstractTreeModel` with context menu and mouse wheel expand/collapse.
"""

from __future__ import annotations
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import AbstractTreeItem, AbstractTreeModel, TreeMimeData


class TreeView(QTreeView):
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
    _copied_items: list[AbstractTreeItem] = []

    # _window_decoration_offset: QPoint = None

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
        # self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # drag-n-drop
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragAndDropEnabled(True)

        # context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._onCustomContextMenuRequested)

        # Each item's view state (e.g. whether item is expanded, selected) will be stored in the item itself in a dict attribute called '_view_state' when the item is dragged or when storeViewState() is called. This allows the view state to be preserved when items are moved within the tree or between different tree views via drag-n-drop, or when the view is refreshed. Item view states are additionally stored in a single dict keyed on the item paths. This allows view state to be preserved when the view is refreshed even if the items themselves are recreated (e.g., from data) such that the item view state attribute is lost.
        self._view_state: dict[str, dict] = {}

        # actions
        self._refreshAction = QAction(
            text='Refresh',
            icon=qta.icon('msc.refresh'),
            iconVisibleInMenu=True,
            toolTip='Refresh UI',
            shortcut=QKeySequence.StandardKey.Refresh,
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.refresh()
        )

        self._selectAllAction = QAction(
            text='Select All',
            toolTip='Select all',
            shortcut=QKeySequence.StandardKey.SelectAll,
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.selectAll()
        )

        self._clearSelectionAction = QAction(
            text='Clear Selection',
            toolTip='Clear selection',
            triggered=lambda checked: self.clearSelection()
        )

        self._removeSelectedAction = QAction(
            text='Remove Selection',
            toolTip='Remove selected',
            shortcut=QKeySequence.StandardKey.Delete,
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.removeSelectedItems()
        )

        self._cutSelectionAction = QAction(
            text='Cut',
            icon=qta.icon('mdi.content-cut'),
            iconVisibleInMenu=True,
            toolTip='Cut selection',
            shortcut=QKeySequence.StandardKey.Cut,
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.cutSelection()
        )

        self._copySelectionAction = QAction(
            text='Copy',
            icon=qta.icon('mdi.content-copy'),
            iconVisibleInMenu=True,
            toolTip='Copy selection',
            shortcut=QKeySequence.StandardKey.Copy,
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.copySelection()
        )

        self._pasteAction = QAction(
            text='Paste',
            icon=qta.icon('mdi.content-paste'),
            iconVisibleInMenu=True,
            toolTip='Paste copy',
            shortcut=QKeySequence.StandardKey.Paste,
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.pasteCopy()
        )

        self._expandAllAction = QAction(
            text='Expand All',
            toolTip='Expand all',
            triggered=lambda checked: self.expandAll()
        )

        self._collapseAllAction = QAction(
            text='Collapse All',
            toolTip='Collapse all',
            triggered=lambda checked: self.collapseAll()
        )

        self._resizeAllColumnsToContentsAction = QAction(
            text='Resize Columns to Contents',
            toolTip='Resize all columns to contents',
            triggered=lambda checked: self.resizeAllColumnsToContents()
        )

        self._showAllAction = QAction(
            text='Show All',
            toolTip='Expand all and resize all columns to contents',
            triggered=lambda checked: self.showAll()
        )
    
    def setModel(self, model: AbstractTreeModel) -> None:
        super().setModel(model)
        model.refreshRequested.connect(self.refresh)
    
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
        model: AbstractTreeModel = self.model()
        if not model:
            return
        for item in model.rootItem().subtree_depth_first():
            try:
                del item._view_state
            except AttributeError:
                pass
    
    def storeViewState(self, items: list[AbstractTreeItem] = None) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        if items is None:
            items = list(model.rootItem().subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        for item in items:
            if item.isRoot():
                continue
            index: QModelIndex = model.indexFromItem(item)
            if not index.isValid():
                continue
            view_state = {
                'expanded': self.isExpanded(index),
                'selected': index in selected_indexes
            }
            item._view_state = view_state
            self._view_state[item.path()] = view_state

    def restoreViewState(self, items: list[AbstractTreeItem] = None) -> None:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        if items is None:
            items = list(model.rootItem().subtree_depth_first())
        selected_indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        to_be_selected: QItemSelection = QItemSelection()
        to_be_deselected: QItemSelection = QItemSelection()
        for item in items:
            if item.isRoot():
                continue
            try:
                view_state: dict = item._view_state
            except AttributeError:
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

    def selectedItems(self) -> list[AbstractTreeItem]:
        model: AbstractTreeModel = self.model()
        if not model:
            return
        indexes: list[QModelIndex] = self.selectionModel().selectedIndexes()
        # get unique items from indexes
        items: list[AbstractTreeItem] = []
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
            text = f'Remove {items[0].path()}?'
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
                    text = f'Remove {items[0].path()}?'
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
        """ Example context menu.
        
        Override in a derived class with the specific actions you want.
        """
        model: AbstractTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: AbstractTreeItem = model.itemFromIndex(index)
        
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
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items: list[AbstractTreeItem] = self.selectedItems()
        if not items:
            return
        # only copy the branch roots (this includes the descendents)
        items = AbstractTreeModel._branchRootItemsOnly(items)
        # copy items
        TreeView._copied_items = [item.copy() for item in items]
    
    def pasteCopy(self, parent_item: AbstractTreeItem = None, row: int = None) -> None:
        if not self.hasCopy():
            return
        model: AbstractTreeModel = self.model()
        if not model:
            return
        if parent_item is None:
            selected_items = self.selectedItems()
            if selected_items:
                parent_item = selected_items[0]
            else:
                parent_item = model.rootItem()
        if row is None or row == -1:
            row = len(parent_item.children)
        items_to_paste = [item.copy() for item in TreeView._copied_items]
        model.insertItems(items_to_paste, row, parent_item)
    
    def hasCopy(self) -> bool:
        return len(TreeView._copied_items) > 0
    
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
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
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
        return super().keyPressEvent(event)
    
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
        mime_data: TreeMimeData = event.mimeData()
        # print('dragEnterEvent', mime_data.formats())

        if not hasattr(mime_data, '_dragged_items'):
            # gather all items being dragged (includes descendents in subtrees)
            # !!! Only do this at the start of the drag, do not repeat on subsequent dragEnterEvents such as when dragging between views.
            dragged_items: list[AbstractTreeItem] = []
            for src_item in mime_data.src_items:
                for item in src_item.subtree_depth_first():
                    if item not in dragged_items:
                        dragged_items.append(item)
            
            # keep track of full list of dragged items (plus their descendents) in mime data
            mime_data._dragged_items = dragged_items

            # store view state of all dragged items in the items themselves
            self.storeViewState(dragged_items)

        QTreeView.dragEnterEvent(self, event)
    
    def dropEvent(self, event: QDropEvent) -> None:
        mime_data: TreeMimeData = event.mimeData()
        # print('dropEvent', mime_data.formats())
        if not isinstance(mime_data, TreeMimeData) and not issubclass(mime_data, TreeMimeData):
            event.ignore()
            return

        src_model: AbstractTreeModel = mime_data.src_model
        src_items: list[AbstractTreeItem] = mime_data.src_items
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
        
        # store drop location in mime data
        mime_data.dst_model = dst_model
        mime_data.dst_parent_item = dst_parent_item
        mime_data.dst_row = dst_row

        # handle drop event
        QTreeView.dropEvent(self, event)
        
        # update view state of dragged items and all their descendents as specified in the mime data
        # only update wether items are expanded, selection should be handled already in drag-n-drop
        dragged_items: list[AbstractTreeItem] = getattr(mime_data, '_dragged_items', [])
        for item in dragged_items:
            index: QModelIndex = dst_model.indexFromItem(item)
            if not index.isValid():
                continue
            try:
                view_state: dict = item._view_state
            except AttributeError:
                continue
            is_expanded = view_state['expanded'] # should be defined
            self.setExpanded(index, is_expanded)
            # assume selection is already handled in drag-n-drop
    
    # def dropMimeData(self, index: QModelIndex, data: QMimeData, action: Qt.DropAction) -> bool:
    #     print('dropMimeData...')
    #     return False
    
    # def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
    #     print('canDropMimeData...')
    #     return True
    
    # @staticmethod
    # def _determineWindowDecorationOffset():
    #     window = QWidget()
    #     window.show()
    #     frame: QRect = window.frameGeometry()
    #     geo: QRect = window.geometry()
    #     window.close()
    #     TreeView._window_decoration_offset = QPoint(frame.x() - geo.x(), frame.y() - geo.y())


def test_live():
    import faulthandler
    faulthandler.enable()
    
    class MyTreeItem(AbstractTreeItem):

        def __init__(self, data: str = '', parent: AbstractTreeItem = None, sibling_index: int = -1):
            super().__init__(parent, sibling_index)
            self.data = data
        
        def name(self) -> str:
            return self.data
    
    app = QApplication()

    for i in range(2):
        root = MyTreeItem(f'r{i}')
        a = MyTreeItem(f'a{i}', parent=root)
        b = MyTreeItem(f'b{i}')
        c = MyTreeItem(f'c{i}')
        d = MyTreeItem(f'd{i}')
        e = MyTreeItem(f'e{i}', parent=b)
        f = MyTreeItem(f'f{i}', parent=e)
        root.appendChild(b)
        root.insertChild(1, c)
        root.children[1].appendChild(d)

        model = AbstractTreeModel()
        model.setRootItem(root)

        view = TreeView()
        view.setModel(model)
        view.show()
        view.resize(800, 1000)
        view.showAll()
        view.move(50 + i * 850, 50)
        view.raise_()

    app.exec()


if __name__ == '__main__':
    test_live()
