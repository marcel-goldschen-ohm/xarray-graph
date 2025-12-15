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
        raise NotImplementedError('To remove rows, removeRows must be implemented in subclasses of AbstractTreeModel.')
    
    def removeItems(self, items: list[AbstractTreeItem]) -> None:
        raise NotImplementedError('To remove items, removeItems must be implemented in subclasses of AbstractTreeModel.')
    
    def insertRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        raise NotImplementedError('To insert new default rows, insertRows must be implemented in subclasses of AbstractTreeModel.')
    
    def insertItems(self, items: list[AbstractTreeItem], row: int, parent_item: AbstractTreeItem) -> None:
        raise NotImplementedError('To insert new items, insertItems must be implemented in subclasses of AbstractTreeModel.')
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        raise NotImplementedError('To move rows within the model, moveRows must be implemented in subclasses of AbstractTreeModel.')
    
    def moveItems(self, src_items: list[AbstractTreeItem], dst_parent_item: AbstractTreeItem, dst_row: int) -> None:
        raise NotImplementedError('To move items within the model, moveItems must be implemented in subclasses of AbstractTreeModel.')
    
    def transferItems(self, src_items: list[AbstractTreeItem], dst_model: AbstractTreeModel, dst_parent_item: AbstractTreeItem, dst_row: int) -> None:
        if dst_model is self:
            self.moveItems(src_items, dst_parent_item, dst_row)
            return
        
        raise NotImplementedError('To move items between models, transferItems must be implemented in subclasses of AbstractTreeModel.')
    
    def supportedDropActions(self) -> Qt.DropActions:
        return self._supportedDropActions
    
    def setSupportedDropActions(self, actions: Qt.DropActions) -> None:
        self._supportedDropActions = actions

    def mimeTypes(self) -> list[str]:
        """ Return the MIME types supported by this view for drag-and-drop operations.
        """
        return [AbstractTreeMimeData.MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> AbstractTreeMimeData | None:
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
        
        return AbstractTreeMimeData(self, items)

    def dropMimeData(self, data: AbstractTreeMimeData, action: Qt.DropAction, row: int, column: int, parent_index: QModelIndex) -> bool:
        if not isinstance(data, AbstractTreeMimeData):
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

        # !? If we return True, the model will attempt to remove rows.
        # As we already completely handled the drop action above, this will corrupt our model, so return False.
        return False
    
    @staticmethod
    def _popupWarningDialog(self, text: str, system_warn: bool = True) -> None:
        focused_widget: QWidget = QApplication.focusWidget()
        QMessageBox.warning(focused_widget, 'Warning', text)
        if system_warn:
            from warnings import warn
            warn(text)


class AbstractTreeMimeData(QMimeData):
    """ Custom MIME data class for `AbstractTreeModel`.

    Used to transfer `AbstractTreeItem`s within and between `AbstractTreeModel`s.

    Note:
    This approach probably won't work if you need to pass items between `AbstractTreeModel`s in separate programs/processes.
    If you really need to do this, you need to somehow serialize the `AbstractTreeItem`s, pass the serialized bytes in the drag MIME data, then deserialize back to `AbstractTreeItem`s on drop.
    """

    MIME_TYPE = 'application/x-abstract-tree-model'

    def __init__(self, src_model: AbstractTreeModel, src_items: list[AbstractTreeItem]):
        QMimeData.__init__(self)

        # these define the datatree items being dragged
        self.src_model: AbstractTreeModel = src_model
        self.src_items: list[AbstractTreeItem] = src_items

        # these define where they are being dragged to (set in drop event)
        self.dst_model: AbstractTreeModel = None
        self.dst_parent_item: AbstractTreeItem = None
        self.dst_row: int = -1

        # Ensure that the MIME type self.MIME_TYPE is set.
        # The actual value of the data here is not important, as we won't use it.
        # Instead, we will use the above attributes to handle drag-and-drop.
        self.setData(self.MIME_TYPE, self.MIME_TYPE.encode('utf-8'))
    
    def hasFormat(self, mime_type: str) -> bool:
        """ Check if the MIME data has the specified format.
        
        Overrides the default method to check for self.MIME_TYPE.
        """
        return mime_type == self.MIME_TYPE or super().hasFormat(mime_type)
