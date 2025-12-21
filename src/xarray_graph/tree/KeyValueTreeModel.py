""" PyQt tree model interface for a key: value mapping (with any amount of nesting).

TODO:
- json serialization. note: this isn't really needed currently.
"""

from __future__ import annotations
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import AbstractTreeItem, AbstractTreeModel


class KeyValueTreeItem(AbstractTreeItem):

    def __init__(self, data, parent: KeyValueTreeItem = None, sibling_index: int = -1):
        # tree linkage
        super().__init__(parent, sibling_index)

        # item data (either the root map or a key into the parent map)
        self.data = data

        self.updateSubtree()
    
    @property
    def name(self) -> str:
        if self.parent is None:
            return '/'
        return str(self.key)
    
    @property
    def path(self) -> str:
        if self.parent is None:
            return '/'
        return super().path[1:]
    
    @property
    def key(self) -> str | int | None:
        if self.parent is None:
            return
        if self.parent.is_list:
            return self.row
        return self.data
    
    @property
    def value(self):
        if self.parent is None:
            return self.data
        return self.parent.value[self.key]
    
    @property
    def is_map(self) -> bool:
        value = self.value
        return isinstance(value, dict) or isinstance(value, list)
    
    @property
    def is_dict(self) -> bool:
        return isinstance(self.value, dict)
    
    @property
    def is_list(self) -> bool:
        return isinstance(self.value, list)
    
    def updateSubtree(self):
        """ Recursively build subtree if value is itself a container with key:value access.
        """
        self.children = []
        if isinstance(self.value, dict):
            for key, val in self.value.items():
                KeyValueTreeItem(key, parent=self)
        elif isinstance(self.value, list):
            for key, val in enumerate(self.value):
                KeyValueTreeItem(key, parent=self)
    
    # def json(self) -> str:
    #     value = self.value
    #     if isinstance(value, dict):
    #         return '{' + ', '.join([f'{item.key}: {item.json()}' for item in self.children]) + '}'
    #     elif isinstance(value, list):
    #         return '[' + ', '.join([item.json() for item in self.children]) + ']'
    #     else:
    #         vtype = type(value)
    #         if vtype.__module__ == 'builtins':
    #             return str(value)
    #         return f'{vtype.__module__}.{vtype.__name__}({KeyValueTreeModel.value_to_str(value)})'
    
    # def setJson(self, text: str) -> None:
    #     old_value = self.value
    #     old_vtype = type(old_value)
    #     new_value = KeyValueTreeModel.str_to_value(text, default_type=old_vtype)
    #     self.orphan()
    #     self.data = new_value
    #     self.updateSubtree()


class KeyValueTreeModel(AbstractTreeModel):
    """ PyQt tree model interface for a key: value mapping.
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
        self.setKeyValueMap({})
    
    def keyValueMap(self) -> dict | list:
        """ Get the model's current key: value map.
        """
        root_item: KeyValueTreeItem = self.rootItem()
        return root_item.value
    
    def setKeyValueMap(self, data: dict | list) -> None:
        """ Reset the model to the input key: value map.
        """
        root_item = KeyValueTreeItem(data)
        self.setRootItem(root_item)
    
    def _onReset(self):
        root_item: KeyValueTreeItem = self.rootItem()
        root_item.updateSubtree()
    
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
        if index.column() == 2:
            # types column is not editable
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        elif index.column() == 0 and item.parent and item.parent.is_list:
            # list index is not editable
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        else:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
            if item.is_dict or item.is_list:
                flags |= Qt.ItemFlag.ItemIsDropEnabled
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            item: KeyValueTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                return item.key
            elif index.column() == 1:
                if item.is_leaf:
                    return self.value_to_str(item.value)
            elif index.column() == 2:
                value = item.value
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
                if isinstance(item.value, dict):
                    return self._dict_icon
                elif isinstance(item.value, list):
                    return self._list_icon
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            if index.column() == 0:
                item: KeyValueTreeItem = self.itemFromIndex(index)
                if item.parent and item.parent.is_list:
                    # list index 50% transparent
                    color: QColor = QApplication.palette().color(QPalette.ColorRole.Text)
                    color.setAlpha(128)
                    return color

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False
        
        if role == Qt.ItemDataRole.EditRole:
            item: KeyValueTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                # edit key (dict only)
                if item.parent.is_dict:
                    old_key = item.key
                    new_key = value
                    if new_key == old_key:
                        return False
                    parent_dict: dict = item.parent.value
                    if new_key in parent_dict:
                        return False
                    parent_dict[new_key] = parent_dict.pop(old_key)
                    item.data = new_key
                    self.dataChanged.emit(index, index)
                    return True
            elif index.column() == 1:
                # edit value
                old_value = item.value
                old_vtype = type(old_value)
                new_value = self.str_to_value(value, default_type=old_vtype)

                parent_map: dict | list = item.parent.value

                has_old_subtree: bool = len(item.children) > 0
                has_new_subtree: bool = type(new_value) in [dict, list] and len(new_value) > 0
                if not has_old_subtree and not has_new_subtree:
                    # edit single leaf value
                    parent_map[item.key] = new_value
                    self.dataChanged.emit(index, index)
                    return True
                
                if has_old_subtree:
                    parent_widget = QApplication.focusWidget()
                    title = 'Overwrite?'
                    text = f'Overwrite non-empty key:value map "{item.path}"?'
                    answer = QMessageBox.question(parent_widget, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if answer == QMessageBox.StandardButton.No:
                        return False
                
                row: int = item.row
                parent_index: QModelIndex = self.parent(index)
                parent_item: KeyValueTreeItem = self.itemFromIndex(parent_index)
                name = item.key
                new_item = KeyValueTreeItem(new_value)
                self.removeRow(item.row, parent_index)
                self.insertItems({name: new_item}, row, parent_item)
                return True
        
        return False

    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        if count <= 0:
            return False
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row + count > num_rows):
            return False
        
        parent_item: KeyValueTreeItem = self.itemFromIndex(parent_index)
        items_to_remove: list[KeyValueTreeItem] = parent_item.children[row: row + count]
        parent_map: dict | list = parent_item.value

        self.beginRemoveRows(parent_index, row, row + count - 1)

        item: KeyValueTreeItem
        for item in reversed(items_to_remove):
            item.data = parent_map.pop(item.key)
            item.parent = None
        del parent_item.children[row: row + count]

        self.endRemoveRows()
        
        return True
    
    def insertRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        """ Defaults to inserting new empty auto-named groups. For anything else, see `insertItems` instead.
        """
        parent_item: KeyValueTreeItem = self.itemFromIndex(parent_index)
        parent_map: dict | list = parent_item.value
        parent_keys = [str(key) for key in parent_map.keys()]
        name_item_map = {}
        for _ in range(row, row + count):
            name = self.unique_name('New', parent_keys)
            name_item_map[name] = KeyValueTreeItem('')
            parent_keys.append(name)
        return self.insertItems(name_item_map, row, parent_item)

        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row > num_rows):
            return False
        
        parent_item: KeyValueTreeItem = self.itemFromIndex(parent_index)
        parent_map: dict | list = parent_item.value
        parent_is_dict: bool = isinstance(parent_map, dict)
        parent_is_list: bool = not parent_is_dict and isinstance(parent_map, list)
        
        # can only insert children in a dict or list
        if not parent_is_dict and not parent_is_list:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot insert items in non-dict/list "{parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False

        if parent_is_dict:
            keys = [str(key) for key in parent_map.keys()]

        self.beginInsertRows(parent_index, row, row + count - 1)

        after_keys = []
        if parent_is_dict and row < len(parent_map):
            after_keys = list(parent_map.keys())[row:]

        for i in range(row, row + count):
            new_data = ''
            if parent_is_dict:
                new_key = self.unique_name('New', keys)
                parent_map[new_key] = new_data
                keys.append(new_key)
            elif parent_is_list:
                new_key = None
                parent_map.insert(i, new_data)
            KeyValueTreeItem(new_key, parent=parent_item, sibling_index=i)
        
        # reorder dict to match item tree
        if parent_is_dict and after_keys:
            for key in after_keys:
                value = parent_map.pop(key)
                parent_map[key] = value

        self.endInsertRows()
        
        return True
    
    def insertItems(self, name_item_map: dict[str, KeyValueTreeItem], row: int, parent_item: KeyValueTreeItem) -> None:
        num_rows: int = len(parent_item.children)
        if row < 0:
            # negative indexing
            row += num_rows
        if (row < 0) or (row > num_rows):
            return False
        
        parent_index: QModelIndex = self.indexFromItem(parent_item)
        parent_map: dict | list = parent_item.value
        parent_is_dict: bool = isinstance(parent_map, dict)
        parent_is_list: bool = not parent_is_dict and isinstance(parent_map, list)
        
        # can only insert children in a dict or list
        if not parent_is_dict and not parent_is_list:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot insert items in non-dict/list "{parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False

        if parent_is_dict:
            keys = [str(key) for key in parent_map.keys()]

        count: int = len(name_item_map)
        self.beginInsertRows(parent_index, row, row + count - 1)

        after_keys = []
        if parent_is_dict and row < len(parent_map):
            after_keys = list(parent_map.keys())[row:]

        name: str
        item: KeyValueTreeItem
        for i, (name, item) in zip(range(row, row + count), name_item_map.items()):
            if parent_is_dict:
                new_key = self.unique_name(name, keys)
                parent_map[new_key] = item.value
                keys.append(new_key)
            elif parent_is_list:
                new_key = None
                parent_map.insert(i, item.value)
            item.data = new_key
            parent_item.insert_child(i, item)
        
        # reorder dict to match item tree
        if parent_is_dict and after_keys:
            for key in after_keys:
                value = parent_map.pop(key)
                parent_map[key] = value

        self.endInsertRows()
        
        return True
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        if count <= 0:
            return False
        num_src_rows: int = self.rowCount(src_parent_index)
        if (src_row < 0) or (src_row + count > num_src_rows):
            return False
        num_dst_rows: int = self.rowCount(dst_parent_index)
        if (dst_row < 0) or (dst_row > num_dst_rows):
            return False
        
        src_parent_item: KeyValueTreeItem = self.itemFromIndex(src_parent_index)
        dst_parent_item: KeyValueTreeItem = self.itemFromIndex(dst_parent_index)

        if src_parent_item is dst_parent_item:
            if src_row <= dst_row <= src_row + count:
                # nothing moved
                return False
        
        src_parent_map: dict | list = src_parent_item.value
        dst_parent_map: dict | list = dst_parent_item.value

        dst_parent_is_dict: bool = isinstance(dst_parent_map, dict)
        dst_parent_is_list: bool = not dst_parent_is_dict and isinstance(dst_parent_map, list)
        
        # can only move children to a dict or list
        if not dst_parent_is_dict and not dst_parent_is_list:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot move items to non-dict/list "{dst_parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False
        
        items_to_move: list[KeyValueTreeItem] = src_parent_item.children[src_row: src_row + count]

        item: KeyValueTreeItem
        for item in items_to_move:
            if dst_parent_item is item or dst_parent_item.has_ancestor(item):
                parent_widget: QWidget = QApplication.focusWidget()
                title = 'Invalid Move'
                text = f'Cannot move item "{item.path}" to its own descendent "{dst_parent_item.path}".'
                QMessageBox.warning(parent_widget, title, text)
                return False
        
        if dst_parent_is_dict:
            dst_keys = [str(key) for key in dst_parent_map.keys()]
        
        # import json
        # print('BEFORE', '-'*42)
        # print(json.dumps(self.keyValueMap(), indent=2))
        # print(self.rootItem())

        self.beginMoveRows(src_parent_index, src_row, src_row + count - 1, dst_parent_index, dst_row)
        
        # remove items from source (store keys to use at destination)
        keys = [item.key for item in items_to_move]
        item: KeyValueTreeItem
        for item in reversed(items_to_move):
            item.data = src_parent_map.pop(item.key)
            item.orphan()
        
        # insert items at destination
        if (src_parent_item is dst_parent_item) and (dst_row > src_row):
            dst_row -= count
        
        dst_after_keys = []
        if dst_parent_is_dict and dst_row < len(dst_parent_map):
            dst_after_keys = list(dst_parent_map.keys())[dst_row:]
        
        item: AbstractTreeItem
        for i, key, item in zip(range(dst_row, dst_row + count), keys, items_to_move):
            if dst_parent_is_dict:
                key = self.unique_name(key, dst_keys)
                dst_parent_map[key] = item.value
                dst_keys.append(key)
            elif dst_parent_is_list:
                key = None
                dst_parent_map.insert(i, item.value)
            item.data = key
            dst_parent_item.insert_child(i, item)
        
        # reorder dst dict to match item tree
        if dst_parent_is_dict and dst_after_keys:
            for key in dst_after_keys:
                value = dst_parent_map.pop(key)
                dst_parent_map[key] = value
        
        self.endMoveRows()
        
        # print('AFTER', '-'*42)
        # print(json.dumps(self.keyValueMap(), indent=2))
        # print(self.rootItem())

        return True
    
    @staticmethod
    def unique_name(name: str, names: list[str], unique_counter_start: int = 1) -> str:
        """ Return name_1, or name_2, etc. until a unique name is found that does not exist in names.
        """
        if name not in names:
            return name
        base_name = name
        i = unique_counter_start
        name = f'{base_name}_{i}'
        while name in names:
            i += 1
            name = f'{base_name}_{i}'
        return name

    @staticmethod
    def ndarray_to_tuple(arr: np.ndarray):
        if arr.shape == ():
            return arr.item()
        else:
            return tuple(map(KeyValueTreeModel.ndarray_to_tuple, arr))
    
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
            if issubclass(default_type, np.integer):
                return default_type(value)
            return value
        except ValueError:
            try:
                value = float(text)
                if issubclass(default_type, np.floating):
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


def test_tree():
    import json

    tree = {
        'a': 1,
        'b': [4, 8, 9, 5, 7, 99],
        'c': {
            'me': 'hi',
            3: 67,
            'd': {
                'e': 3,
                'f': 'ya!',
                'g': 5,
            },
        },
        'nd': np.array([[1, 2, 3], [4, 5, 6]]),
    }

    # print(json.dumps(tree, indent='    '))
    root = KeyValueTreeItem(tree)
    print('-'*82)
    print(root)
    # print(json.dumps(tree, indent='    '))

    # print('-'*82)
    # print('remove /a')
    # root.removeChild(root['/a'])
    # print(root)

    # print('-'*82)
    # print('remove /c/d/f')
    # d = root['c/d']
    # f = root['c/d/f']
    # d.removeChild(f)
    # print(root)

    # print('-'*82)
    # print('move /c/d to /d')
    # d.setParent(root)
    # print(root)

    # print('-'*82)
    # print('move /d to 2nd child of /')
    # root.insertChild(1, d)
    # print(root)

    # print('-'*82)
    # print('move /d to 3rd child of /b')
    # b = root['b']
    # b.insertChild(2, d)
    # print(root)

    # print('-'*82)
    # print('remove /b/1')
    # b.removeChild(b['1'])
    # print(root)

    # print('-'*82)
    # print('/c/me:hi -> /c/me:bye')
    # c = root['c']
    # c.children[0].setValue('bye')
    # print(root)

    # print('-'*82)
    # print('move /b/1 to first child of /c')
    # c.insertChild(0, b['1'])
    # print(root)

    # print('-'*82)
    # print('/c -> 82')
    # c.setValue(82)
    # print(root)

    # print('-'*82)
    # print('/c -> {a:1, b:2}')
    # c.setValue({'a': 1, 'b': 2})
    # print(root)

    # print('-'*82)
    # print('/nd')
    # print(root['/nd'])


if __name__ == '__main__':
    test_tree()