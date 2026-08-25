""" PyQt tree model interface for a key: value mapping (with any amount of nesting).
"""
from __future__ import annotations

from qtpy.QtCore import Qt, QPoint, QSize, QModelIndex
from qtpy.QtGui import QColor
from xarray_graph.tree.KeyValueTreeItem import KeyValueTreeItem
from xarray_graph.tree.AbstractTreeModel import AbstractTreeModel
from xarray_graph.utils.utils import str_to_value, value_to_str

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from qtpy.QtGui import QIcon


class KeyValueTreeModel(AbstractTreeModel[KeyValueTreeItem]):
    """ PyQt tree model interface for a key:value mapping.
    """

    MIME_TYPE = 'application/x-key-value-tree-model'

    def __init__(self, root_item: KeyValueTreeItem, *args, **kwargs):
        super().__init__(root_item, *args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['Key', 'Value', 'Type']

        # options
        self._is_types_column_visible: bool = True

        # icons
        import qtawesome as qta
        self._dict_icon: QIcon = qta.icon('ph.folder-thin')
        self._list_icon: QIcon = qta.icon('ph.list-numbers-thin')
    
    def treeData(self) -> dict | list:
        """ Get the root key:value map.
        """
        return self.rootItem().value()
    
    def setTreeData(self, data: dict | list) -> None:
        """ Set the root key:value map.
        """
        new_root_item = KeyValueTreeItem(None, data)
        new_root_item.rebuildSubtree()
        self.setRootItem(new_root_item)
    
    def isTypesColumnVisible(self) -> bool:
        return self._is_types_column_visible
    
    def setTypesColumnVisible(self, visible: bool) -> None:
        if visible == self.isTypesColumnVisible():
            return
        
        if visible:
            self.beginInsertColumns(QModelIndex(), 2, 2)
            self._is_types_column_visible = visible
            self.endInsertColumns()
        else:
            self.beginRemoveColumns(QModelIndex(), 2, 2)
            self._is_types_column_visible = visible
            self.endRemoveColumns()
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        if self.isTypesColumnVisible():
            return 3
        return 2

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """ Default item flags.
        
        Supports drag-and-drop if it is enabled in `supportedDropActions`.
        """
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        
        item = self.itemFromIndex(index)
        parent_item = item.parent
        if index.column() == 2:
            # types column is not editable
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        elif index.column() == 0 and parent_item and isinstance(parent_item.value(), list):
            # list index is not editable
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        else:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
            if isinstance(item.value(), (dict, list)):
                # can only drop on containers
                flags |= Qt.ItemFlag.ItemIsDropEnabled
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            item = self.itemFromIndex(index)
            if index.column() == 0:
                return item.key()
            elif index.column() == 1:
                if item.isLeaf() and not item.isContainer():
                    return value_to_str(item.value())
            elif index.column() == 2:
                value = item.value()
                vtype = type(value)
                import numpy as np
                if isinstance(value, np.ndarray):
                    text = f'{vtype.__name__} of {value.dtype}'
                else:
                    text = vtype.__name__
                return text
        
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item = self.itemFromIndex(index)
                if isinstance(item.value(), dict):
                    return self._dict_icon
                elif isinstance(item.value(), list):
                    return self._list_icon
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            # non-editable items are 50% transparent
            is_editable = self.flags(index) & Qt.ItemFlag.ItemIsEditable
            if not is_editable:
                from qtpy.QtGui import QPalette
                from qtpy.QtWidgets import QApplication
                color: QColor = QApplication.palette().color(QPalette.ColorRole.Text)
                color.setAlpha(128)
                return color

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False
        
        if role == Qt.ItemDataRole.EditRole:
            item = self.itemFromIndex(index)
            if index.column() == 0:
                # edit key
                item.setKey(value)
                self.dataChanged.emit(index, index)
                return True
            elif index.column() == 1:
                # edit value
                new_value = str_to_value(value)
                n_old_children: int = len(item.children)
                n_new_children: int = len(new_value) if isinstance(new_value, (dict, list)) else 0
                if n_old_children:
                    from qtpy.QtWidgets import QApplication, QMessageBox
                    focus_widget = QApplication.focusWidget()
                    title = 'Overwrite?'
                    text = f'Overwrite non-empty key:value map "{item.path()}"?'
                    answer = QMessageBox.question(focus_widget, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if answer == QMessageBox.StandardButton.No:
                        return False
                    
                    # remove old subtree items
                    self.removeRows(0, n_old_children, index)
                if n_new_children:
                    # insert new subtree items (handled by setValue)
                    self.beginInsertRows(index, 0, n_new_children - 1)
                    item.setValue(new_value)
                    self.endInsertRows()
                    # Ask the view to refresh because changes to the tree structure are not gauranteed to update in the view when performed here in setData.
                    self.refreshRequested.emit()
                else:
                    item.setValue(new_value)
                    self.dataChanged.emit(index, index)
                return True
        
        return False


def test_live():
    import numpy as np
    from qtpy.QtWidgets import QApplication, QTreeView
    app = QApplication()
    data = {
        'a': 1,
        'b': [4, 8, (1, 5.5234985270827504823702, True, 'good'), 5, 7, 99, True, False, 'hi', 'bye'],
        'c': {
            'me': 'hi',
            3: 67,
            'd': {
                'e': np.float32(3.14),
                'f': 'ya!',
                'g': np.int16(5),
            },
        },
        '1d': np.array([1, 2, 3]),
        'nd': np.array([[1, 2, 3], [4, 5, 6]]),
        'ndr': np.random.random((9,99)),
    }
    root = KeyValueTreeItem(None, data)
    root.rebuildSubtree()
    print(root)
    model = KeyValueTreeModel(root)
    view = QTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 800))
    view.move(QPoint(100, 100))
    view.raise_()
    app.exec()
    print(data)

if __name__ == '__main__':
    test_live()