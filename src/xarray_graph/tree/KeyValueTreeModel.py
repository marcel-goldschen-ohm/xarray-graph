""" PyQt tree model interface for a key: value mapping (with any amount of nesting).
"""

from __future__ import annotations
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import KeyValueTreeItem, AbstractTreeModel


class KeyValueTreeModel(AbstractTreeModel):
    """ PyQt tree model interface for a key:value mapping.
    """

    MIME_TYPE = 'application/x-key-value-tree-model'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['Key', 'Value', 'Type']

        # options
        self._is_types_column_visible: bool = False

        # icons
        self._dict_icon: QIcon = qta.icon('ph.folder-thin')
        self._list_icon: QIcon = qta.icon('ph.list-numbers-thin')

        # setup item tree
        self.setRootItem(KeyValueTreeItem(None, {}))
    
    # def treeData(self) -> dict | list:
    #     """ Get the root key:value map.
    #     """
    #     root_item: KeyValueTreeItem = self.rootItem()
    #     return root_item.value()
    
    # def setTreeData(self, data: dict | list) -> None:
    #     """ Set the root key:value map.
    #     """
    #     new_root_item = KeyValueTreeItem(None, data)
    #     self.setRootItem(new_root_item)
    
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
        
        item: KeyValueTreeItem = self.itemFromIndex(index)
        parent_item: KeyValueTreeItem = item.parent
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
            item: KeyValueTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                return item.key()
            elif index.column() == 1:
                if item.isLeaf() and not item.isContainer():
                    return self.value_to_str(item.value())
            elif index.column() == 2:
                value = item.value()
                vtype = type(value)
                if vtype.__module__ == 'builtins':
                    text = vtype.__name__
                else:
                    text = f'{vtype.__module__}.{vtype.__name__}'
                if vtype is np.ndarray:
                    text += f' of {value.dtype}'
                return text
        
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: KeyValueTreeItem = self.itemFromIndex(index)
                if isinstance(item.value(), dict):
                    return self._dict_icon
                elif isinstance(item.value(), list):
                    return self._list_icon
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            # non-editable items are 50% transparent
            is_editable = self.flags(index) & Qt.ItemFlag.ItemIsEditable
            if not is_editable:
                color: QColor = QApplication.palette().color(QPalette.ColorRole.Text)
                color.setAlpha(128)
                return color

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False
        
        if role == Qt.ItemDataRole.EditRole:
            item: KeyValueTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                # edit key
                item.setKey(value)
                # self.dataChanged.emit(index, index)
                return True
            elif index.column() == 1:
                # edit value
                old_value = item.value()
                old_vtype = type(old_value)
                new_value = self.str_to_value(value, default_type=old_vtype)
                n_old_children: int = len(item.children)
                n_new_children: int = len(new_value) if type(new_value) in [dict, list] else 0
                if n_old_children:
                    parent_widget = QApplication.focusWidget()
                    title = 'Overwrite?'
                    text = f'Overwrite non-empty key:value map "{item.path()}"?'
                    answer = QMessageBox.question(parent_widget, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
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
                # self.dataChanged.emit(index, index)
                return True
        
        return False

    @staticmethod
    def str_to_value(text: str, default_type = None) -> bool | int | float | str | tuple | list | dict | set | np.ndarray:
        if text.lower().strip() == 'true':
            return True
        if text.lower().strip() == 'false':
            return False
        str_to_value = KeyValueTreeModel.str_to_value
        split_text = KeyValueTreeModel.split_text
        if text.lstrip().startswith('numpy.array(') and text.rstrip().endswith(')'):
            # numpy array
            inner_text = text.strip()[len('numpy.array(['):-2]
            values = [str_to_value(item.strip()) for item in split_text(inner_text)]
            return np.array(values)
        if text.lstrip().startswith('np.array(') and text.rstrip().endswith(')'):
            # numpy array
            inner_text = text.strip()[len('np.array(['):-2]
            values = [str_to_value(item.strip()) for item in split_text(inner_text)]
            return np.array(values)
        if text.lstrip().startswith('array(') and text.rstrip().endswith(')'):
            # numpy array
            inner_text = text.strip()[len('array(['):-2]
            values = [str_to_value(item.strip()) for item in split_text(inner_text)]
            return np.array(values)
        if text.lstrip().startswith('(') and text.rstrip().endswith(')'):
            # tuple
            inner_text = text.strip()[1:-1]
            values = [str_to_value(item.strip()) for item in split_text(inner_text)]
            return tuple(values)
        if text.lstrip().startswith('[') and text.rstrip().endswith(']'):
            # list or numpy array
            inner_text = text.strip()[1:-1]
            values = [str_to_value(item.strip()) for item in split_text(inner_text)]
            if default_type is np.ndarray:
                return np.array(values)
            return values
        if text.lstrip().startswith('{') and text.rstrip().endswith('}'):
            # dict or set
            inner_text = text.strip()[1:-1]
            items = split_text(inner_text)
            if not items:
                # empty dict
                return {}
            if ':' in items[0]:
                # dict
                values = {}
                for item in items:
                    key, value = item.split(':')
                    values[key.strip()] = str_to_value(value.strip())
                return values
            else:
                # set
                values = set()
                for item in items:
                    values.add(str_to_value(item))
                return values
        try:
            value = int(text)
            if default_type and issubclass(default_type, np.integer):
                return default_type(value)
            return value
        except ValueError:
            try:
                value = float(text)
                if default_type and issubclass(default_type, np.floating):
                    return default_type(value)
                return value
            except ValueError:
                return text

    @staticmethod
    def value_to_str(value, in_recursion: bool = False) -> str:
        if isinstance(value, str):
            return value
        if type(value) in [bool, int, float]:
            return str(value)
        value_to_str = KeyValueTreeModel.value_to_str
        if isinstance(value, tuple):
            return '(' + ', '.join([value_to_str(val) for val in value]) + ')'
        if isinstance(value, list):
            return '[' + ', '.join([value_to_str(val) for val in value]) + ']'
        if isinstance(value, set):
            return '{' + ', '.join([value_to_str(val) for val in value]) + '}'
        if isinstance(value, dict):
            return '{' + ', '.join([f'{key}: ' + value_to_str(val) for key, val in value.items()]) + '}'
        if isinstance(value, np.ndarray):
            return '[' + ', '.join([value_to_str(val, in_recursion=True) for val in value]) + ']'
        return str(value)

    @staticmethod
    def split_text(text: str) -> list[str]:
        parts: list[str] = ['']
        grouping: str = ''
        for char in text:
            if char == '(' or char == '[' or char == '{':
                grouping += char
            elif grouping:
                if grouping[-1] == '(' and char == ')':
                    grouping = grouping[:-1]
                elif grouping[-1] == '[' and char == ']':
                    grouping = grouping[:-1]
                elif grouping[-1] == '{' and char == '}':
                    grouping = grouping[:-1]
            if char == ',' and not grouping:
                parts.append('')
            else:
                parts[-1] += char
        parts = [part.strip() for part in parts if part.strip()]
        return parts


def test_live():
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
    }
    root = KeyValueTreeItem(None, data)
    model = KeyValueTreeModel()
    model.setTypesColumnVisible(True)
    model.setRootItem(root)
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