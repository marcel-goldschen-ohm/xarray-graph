""" PyQt tree model interface for a key: value mapping (with any amount of nesting).

TODO:
"""

from __future__ import annotations
from typing import Any
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import AbstractTreeItem, AbstractTreeModel, AbstractTreeMimeData


class KeyValueTreeItem(AbstractTreeItem):

    def __init__(self, key: str | None, value: dict | list | Any, parent: KeyValueTreeItem = None, sibling_index: int = -1):
        # tree linkage
        super().__init__(parent, sibling_index)

        # item data
        self.key = key
        self.value = value

        self.updateSubtree()
    
    @property
    def name(self) -> str:
        if self.parent is None:
            return '/'
        return str(self.key)
    
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
                KeyValueTreeItem(key, val, parent=self)
        elif isinstance(self.value, list):
            for key, val in enumerate(self.value):
                KeyValueTreeItem(key, val, parent=self)


class KeyValueTreeModel(AbstractTreeModel):
    """ PyQt tree model interface for a key: value mapping.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['Key', 'Value']

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
        root_item = KeyValueTreeItem(None, data)
        self.setRootItem(root_item)
    
    def _onReset(self):
        root_item: KeyValueTreeItem = self.rootItem()
        root_item.updateSubtree()
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
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
        if index.column() == 0 and item.parent and item.parent.is_list:
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
                    value = item.value
                    if isinstance(value, np.ndarray):
                        value = self.ndarray_to_tuple(value)
                    else:
                        try:
                            # a numpy value
                            dtype = value.dtype
                            if np.issubdtype(dtype, np.floating):
                                value = float(value)
                            elif np.issubdtype(dtype, np.integer):
                                value = int(value)
                        except:
                            # not a numpy value
                            pass
                    return value
        
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
                    item.key = new_key
                    self.dataChanged.emit(index, index)
                    return True
            elif index.column() == 1:
                # edit value
                # TODO
                return True
        
        return False

    @staticmethod
    def ndarray_to_tuple(arr: np.ndarray):
        if arr.shape == ():
            return arr.item()
        else:
            return tuple(map(KeyValueTreeModel.ndarray_to_tuple, arr))
    

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
    root = KeyValueTreeItem(None, tree)
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