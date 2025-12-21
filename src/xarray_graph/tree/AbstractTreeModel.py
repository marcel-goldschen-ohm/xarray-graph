""" PyQt tree model interface for `AbstractTreeItem`.
"""

from __future__ import annotations
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from xarray_graph.tree import AbstractTreeItem


class AbstractTreeModel(QAbstractItemModel):
    """ PyQt tree model interface for `AbstractTreeItem`.
    """

    MIME_TYPE = 'application/x-abstract-tree-model'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['DataTree', 'Details']

        # drag-and-drop support for moving tree items within the tree or copying them to other tree models
        self._supportedDropActions: Qt.DropActions = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

        # setup item tree
        self._root_item = AbstractTreeItem()
    
    def currentViews(self) -> list:
        self._views = [view for view in self._views if view.model() is self]
        return self._views
    
    def rootItem(self) -> AbstractTreeItem:
        return self._root_item
    
    def setRootItem(self, root_item: AbstractTreeItem) -> None:
        self.beginResetModel()
        self._root_item = root_item
        self._onReset()
        self.endResetModel()
    
    def reset(self) -> None:
        """ Reset the model to an empty state with only the root item.
        """
        self.beginResetModel()
        self._onReset()
        self.endResetModel()
    
    def _onReset(self) -> None:
        """ Custom actions when tree is reset.
        """
        pass # reimplement in subclasses if needed
    
    def itemFromIndex(self, index: QModelIndex) -> AbstractTreeItem:
        if not index.isValid():
            return self._root_item
        item: AbstractTreeItem = index.internalPointer()
        return item
    
    def indexFromItem(self, item: AbstractTreeItem, column: int = 0) -> QModelIndex:
        if (item is self._root_item) or (item.parent is None):
            return QModelIndex()
        row: int = item.parent.children.index(item)
        return self.createIndex(row, column, item)
    
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        parent_item: AbstractTreeItem = self.itemFromIndex(parent_index)
        if parent_item is None:
            return 0
        return len(parent_item.children)
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        return 1

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        item: AbstractTreeItem = self.itemFromIndex(index)
        parent_item: AbstractTreeItem = item.parent
        if (parent_item is None) or (parent_item is self._root_item):
            return QModelIndex()
        return self.indexFromItem(parent_item)

    def index(self, row: int, column: int, parent_index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent_index):
            return QModelIndex()
        if parent_index.isValid() and parent_index.column() != 0:
            return QModelIndex()
        try:
            parent_item: AbstractTreeItem = self.itemFromIndex(parent_index)
            item: AbstractTreeItem = parent_item.children[row]
            return self.createIndex(row, column, item)
        except IndexError:
            return QModelIndex()

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """ Default item flags.
        
        Supports drag-and-drop if it is enabled in `supportedDropActions`.
        """
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            flags |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            item: AbstractTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                return item.name

    def setData(self, index: QModelIndex, value, /, role: int = ...) -> bool:
        raise NotImplementedError('setData must be implemented in subclasses of AbstractTreeModel.')
    
    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        """ Get data from `rowLabels` or `columnLabels`.
        """
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = self.columnLabels()
            elif orientation == Qt.Orientation.Vertical:
                labels = self.rowLabels()
            if section < len(labels):
                label = labels[section]
                if label is not None:
                    return label
            return section

    def setHeaderData(self, section: int, orientation: Qt.Orientation, value, role: int) -> bool:
        """ Set data in `rowLabels` or `columnLabels`.
        """
        if role == Qt.ItemDataRole.EditRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = self.columnLabels()
            elif orientation == Qt.Orientation.Vertical:
                labels = self.rowLabels()
            if section < len(labels):
                labels[section] = value
            else:
                labels += [None] * (section - len(labels)) + [value]
            if orientation == Qt.Orientation.Horizontal:
                self.setColumnLabels(labels)
            elif orientation == Qt.Orientation.Vertical:
                self.setRowLabels(labels)
            self.headerDataChanged.emit(orientation, section, section)
            return True
        return False
    
    def rowLabels(self) -> list:
        return self._row_labels
    
    def setRowLabels(self, labels: list) -> None:
        old_labels = self._row_labels
        n_overlap = min(len(labels), len(old_labels))
        first_change = 0
        while (first_change < n_overlap) and (labels[first_change] == old_labels[first_change]):
            first_change += 1
        last_change = max(len(labels), len(old_labels)) - 1
        while (last_change < n_overlap) and (labels[last_change] == old_labels[last_change]):
            last_change -= 1
        self._row_labels = labels
        if first_change <= last_change: 
            self.headerDataChanged.emit(Qt.Orientation.Vertical, first_change, last_change)
    
    def columnLabels(self) -> list | None:
        return self._column_labels
    
    def setColumnLabels(self, labels: list | None) -> None:
        old_labels = self._column_labels
        n_overlap = min(len(labels), len(old_labels))
        first_change = 0
        while (first_change < n_overlap) and (labels[first_change] == old_labels[first_change]):
            first_change += 1
        last_change = max(len(labels), len(old_labels)) - 1
        while (last_change < n_overlap) and (labels[last_change] == old_labels[last_change]):
            last_change -= 1
        self._column_labels = labels
        if first_change <= last_change: 
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, first_change, last_change)
    
    def depth(self) -> int:
        """ Maximum depth of root's subtree.
        """
        return self.rootItem().subtree_max_depth()
    
    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        """ Removes items only. Reimplement in a subclass to remove associated data.
        """

        # raise NotImplementedError('Implement removeRows() in subclasses of AbstractTreeModel.')
    
        if count <= 0:
            return False
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row + count > num_rows):
            return False
        
        parent_item: AbstractTreeItem = self.itemFromIndex(parent_index)
        items_to_remove: list[AbstractTreeItem] = parent_item.children[row: row + count]

        self.beginRemoveRows(parent_index, row, row + count - 1)

        item: AbstractTreeItem
        for item in reversed(items_to_remove):
            item.parent = None
        del parent_item.children[row: row + count]

        self.endRemoveRows()
        
        return True
    
    def removeItems(self, items: list[AbstractTreeItem]) -> None:
        if not items:
            return
        
        # discard items that are descendents of other items to be removed
        items = self._branchRootItemsOnly(items)
        
        if len(items) == 1:
            item: AbstractTreeItem = items[0]
            row: int = item.row
            parent_index: QModelIndex = self.indexFromItem(item.parent)
            self.removeRows(row, 1, parent_index)
            return
        
        # group items into blocks by parent and contiguous rows
        item_blocks: list[list[AbstractTreeItem]] = self._itemBlocks(items)
        
        # remove each item block
        # note: blocks are in depth-first order, so remove in reverse order to ensure row indices remain valid after removing each block
        for block in reversed(item_blocks):
            row: int = block[0].row
            count: int = len(block)
            parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            self.removeRows(row, count, parent_index)
    
    def insertRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        """ Inserts default items only. Reimplement in a subclass to insert associated data.
        """

        # raise NotImplementedError('Implement insertRows() in subclasses of AbstractTreeModel.')
    
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row > num_rows):
            return False
        
        parent_item: AbstractTreeItem = self.itemFromIndex(parent_index)

        self.beginInsertRows(parent_index, row, row + count - 1)

        for i in range(row, row + count):
            AbstractTreeItem(parent=parent_item, sibling_index=i)

        self.endInsertRows()
        
        return True
    
    def insertItems(self, items: list[AbstractTreeItem], row: int, parent_item: AbstractTreeItem) -> None:
        """ Inserts items only. Reimplement in a subclass to insert associated data.
        """

        # raise NotImplementedError('Implement insertItems() in subclasses of AbstractTreeModel.')
    
        parent_index: QModelIndex = self.indexFromItem(parent_item)
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row > num_rows):
            return False

        count: int = len(items)
        self.beginInsertRows(parent_index, row, row + count - 1)

        item: AbstractTreeItem
        for i, item in zip(range(row, row + count), items):
            parent_item.insert_child(i, item)
        
        self.endInsertRows()
        
        return True
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        """ Moves items only. Reimplement in a subclass to move associated data.
        """
        
        # raise NotImplementedError('Implement moveRows() in subclasses of AbstractTreeModel.')
    
        if count <= 0:
            return False
        num_src_rows: int = self.rowCount(src_parent_index)
        if (src_row < 0) or (src_row + count > num_src_rows):
            return False
        num_dst_rows: int = self.rowCount(dst_parent_index)
        if (dst_row < 0) or (dst_row > num_dst_rows):
            return False
        
        src_parent_item: AbstractTreeItem = self.itemFromIndex(src_parent_index)
        dst_parent_item: AbstractTreeItem = self.itemFromIndex(dst_parent_index)

        if src_parent_item is dst_parent_item:
            if src_row <= dst_row <= src_row + count:
                # nothing moved
                return False
        
        items_to_move: list[AbstractTreeItem] = src_parent_item.children[src_row: src_row + count]
        
        item: AbstractTreeItem
        for item in items_to_move:
            if dst_parent_item is item or dst_parent_item.has_ancestor(item):
                parent_widget: QWidget = QApplication.focusWidget()
                title = 'Invalid Move'
                text = f'Cannot move item "{item.path}" to its own descendent "{dst_parent_item.path}".'
                QMessageBox.warning(parent_widget, title, text)
                return False
        
        self.beginMoveRows(src_parent_index, src_row, src_row + count - 1, dst_parent_index, dst_row)

        # remove items from source
        del src_parent_item.children[src_row: src_row + count]
        
        # insert items at destination
        if (src_parent_item is dst_parent_item) and (dst_row > src_row):
            dst_row -= count
        
        item: AbstractTreeItem
        for i, item in zip(range(dst_row, dst_row + count), items_to_move):
            dst_parent_item.insert_child(i, item)

        self.endMoveRows()
        
        return True
    
    def moveItems(self, src_items: list[AbstractTreeItem], dst_parent_item: AbstractTreeItem, dst_row: int) -> None:
        if not src_items or not dst_parent_item:
            return
        
        dst_parent_index: QModelIndex = self.indexFromItem(dst_parent_item)
        
        if len(src_items) == 1:
            src_item: AbstractTreeItem = src_items[0]
            src_parent_index: QModelIndex = self.indexFromItem(src_item.parent)
            src_row: int = src_item.row
            self.moveRows(src_parent_index, src_row, 1, dst_parent_index, dst_row)
            return
        
        # group items into blocks by data type, parent, and contiguous rows
        src_item_blocks: list[list[AbstractTreeItem]] = self._itemBlocks(src_items)
        
        # move each item block
        # note: blocks are in depth-first order, so move in reverse order to ensure row indices remain valid after moving each block
        for block in reversed(src_item_blocks):
            src_parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            src_row: int = block[0].row
            count: int = len(block)
            self.moveRows(src_parent_index, src_row, count, dst_parent_index, dst_row)
    
    def transferItems(self, src_items: list[AbstractTreeItem], dst_model: AbstractTreeModel, dst_parent_item: AbstractTreeItem, dst_row: int) -> None:
        if dst_model is self:
            self.moveItems(src_items, dst_parent_item, dst_row)
            return
        
        name_item_map: dict[str, AbstractTreeItem] = {item.name: item for item in src_items}
        self.removeItems(src_items)
        dst_model.insertItems(name_item_map, dst_row, dst_parent_item)
    
    @staticmethod
    def _branchRootItemsOnly(items: list[AbstractTreeItem]) -> list[AbstractTreeItem]:
        """ Discard items that are descendents of other items.
        """
        items = items.copy()
        item: AbstractTreeItem
        for item in tuple(items):
            for other_item in items:
                if other_item is item:
                    continue
                if item.has_ancestor(other_item):
                    # item is a descendent of other_item
                    items.remove(item)
                    break
        return items
    
    @staticmethod
    def _itemBlocks(items: list[AbstractTreeItem]) -> list[list[AbstractTreeItem]]:
        """ Group items by parent and contiguous rows.

        Each block can be input to removeRows() or moveRows().
        Blocks are ordered depth-first. Typically you should remove/move blocks in reverse depth-first order to ensure insertion row indices remain valid after handling each block.
        """
        # so we don't modify the input list
        items = items.copy()

        # order items depth-first so that it is easier to group them into blocks
        items.sort(key=lambda item: item.level)
        items.sort(key=lambda item: item.row)

        # group items into blocks by parent and contiguous rows
        blocks: list[list[AbstractTreeItem]] = [[items[0]]]
        for item in items[1:]:
            added_to_block = False
            for block in blocks:
                if item.parent is block[0].parent:
                    if item.row == block[-1].row + 1:
                        block.append(item)
                    else:
                        blocks.append([item])
                    added_to_block = True
                    break
            if not added_to_block:
                blocks.append([item])
        return blocks
    
    def supportedDropActions(self) -> Qt.DropActions:
        return self._supportedDropActions
    
    def setSupportedDropActions(self, actions: Qt.DropActions) -> None:
        self._supportedDropActions = actions

    def mimeTypes(self) -> list[str]:
        """ Return the MIME types supported by this model for drag-and-drop operations.
        """
        return [self.MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> TreeMimeData | None:
        if not indexes:
            return
        
        # ensure unique items
        items: list[AbstractTreeItem] = []
        index: QModelIndex
        for index in indexes:
            item: AbstractTreeItem = self.itemFromIndex(index)
            if item not in items:
                items.append(item)
        if not items:
            return
        
        return TreeMimeData(self, items, self.MIME_TYPE)

    def dropMimeData(self, data: TreeMimeData, action: Qt.DropAction, row: int, column: int, parent_index: QModelIndex) -> bool:
        if not isinstance(data, TreeMimeData) and not issubclass(data, TreeMimeData):
            return False
        
        src_model: AbstractTreeModel = data.src_model
        src_items: list[AbstractTreeItem] = data.src_items
        dst_model: AbstractTreeModel = data.dst_model
        dst_parent_item: AbstractTreeItem = data.dst_parent_item
        dst_row: int = data.dst_row
        if dst_model is not self:
            # sanity check
            return False

        if action == Qt.DropAction.MoveAction:
            src_model.transferItems(src_items, dst_model, dst_parent_item, dst_row)
        else:
            raise NotImplementedError(f'Reimplement dropMimeData() to support {action.name} actions.')

        # !? If we return True, the model will attempt to remove rows. As we already completely handled the drop action above, this will corrupt our model, so return False.
        return False
    
    @staticmethod
    def popupWarningDialog(self, text: str, system_warn: bool = True) -> None:
        focused_widget: QWidget = QApplication.focusWidget()
        QMessageBox.warning(focused_widget, 'Warning', text)
        if system_warn:
            from warnings import warn
            warn(text)


class TreeMimeData(QMimeData):
    """ Custom MIME data class for `AbstractTreeModel` and subclasses.

    Used to transfer `AbstractTreeItem`s within and between `AbstractTreeModel`s.

    Note: This approach only enables drag-n-drop within a program/process. If you need to pass items between `AbstractTreeModel`s in separate programs/processes, you'll need to somehow serialize the `AbstractTreeItem`s, pass the serialized bytes in the drag MIME data, then deserialize back to `AbstractTreeItem`s on drop.
    """

    def __init__(self, src_model: AbstractTreeModel, src_items: list[AbstractTreeItem], mime_type: str = AbstractTreeModel.MIME_TYPE):
        QMimeData.__init__(self)

        # these define the datatree items being dragged
        self.src_model: AbstractTreeModel = src_model
        self.src_items: list[AbstractTreeItem] = src_items

        # these define where they are being dragged to (set in drop event)
        self.dst_model: AbstractTreeModel = None
        self.dst_parent_item: AbstractTreeItem = None
        self.dst_row: int = -1

        # Ensure that the input MIME type is set.
        # The actual value of the data here is not important, as we won't use it.
        # Instead, we will use the above attributes to handle drag-and-drop.
        self.setData(mime_type, mime_type.encode('utf-8'))
