""" PyQt tree item for a key: value mapping (with any amount of nesting).
"""

from __future__ import annotations
import numpy as np
from xarray_graph.tree import AbstractTreeItem
from copy import deepcopy


class KeyValueTreeItem(AbstractTreeItem):
    """ Holds a key:value pair and parent-child linkage for nested structures.
    """

    def __init__(self, key, value, parent: KeyValueTreeItem = None, sibling_index: int = None):
        self._key = key
        self._value = value
        super().__init__(parent, sibling_index)

    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(lambda item: f'{item.key()}: {item.value()}')
    
    def isList(self) -> bool:
        return isinstance(self.value(), list)
    
    def isDict(self) -> bool:
        return isinstance(self.value(), dict)
    
    def isContainer(self) -> bool:
        return isinstance(self.value(), (dict, list))
    
    def rebuildSubtree(self) -> None:
        """ Recursively build subtree if value is itself a container with key:value access.
        """
        self.children = []
        value = self.value()
        if isinstance(value, dict):
            for key, val in value.items():
                child = KeyValueTreeItem(key, val, parent=self)
                child.rebuildSubtree()
        elif isinstance(value, list):
            for key, val in enumerate(value):
                child = KeyValueTreeItem(key, val, parent=self)
                child.rebuildSubtree()
    
    def key(self):
        # if this item is in a list, return the item's sibling index
        parent: KeyValueTreeItem = self.parent
        if parent and isinstance(parent.value(), list):
            return self.siblingIndex()
        # otherwise, return the item's key
        return self._key
    
    def setKey(self, key) -> None:
        # if this item is in a dict, update the key in the parent dict
        parent: KeyValueTreeItem = self.parent
        if parent:
            parent_map: dict | list = parent.value()
            if isinstance(parent_map, dict):
                parent_map[key] = parent_map.pop(self.key())
        # update this item's key
        self._key = key
    
    def value(self):
        return self._value
    
    def setValue(self, value) -> None:
        parent: KeyValueTreeItem = self.parent
        if parent:
            parent_map: dict | list = parent.value()
            parent_map[self.key()] = value
        self._value = value
        self.rebuildSubtree()
    
    def name(self) -> str:
        key = self.key()
        if key is None and self.parent is None:
            return self._path_sep
        return str(key)
    
    def setName(self, name: str) -> None:
        self.setKey(name)

    def orphan(self) -> None:
        if not self.parent:
            return
        
        # Remove value from parent map
        parent: KeyValueTreeItem = self.parent
        parent.value().pop(self.key())
        
        # Update item linkage
        self.parent.children.remove(self)
        self.parent = None
    
    def insertChild(self, index: int, item: KeyValueTreeItem) -> None:
        # Insert child value into this map
        value = self.value()
        if isinstance(value, dict):
            value[item._key] = item._value
        elif isinstance(value, list):
            value.insert(index, item._value)
        else:
            raise TypeError(f'Cannot insert child into value of type {type(value)}')

        # Update item linkage
        self.children.insert(index, item)
        item.parent = self
    
    def copy(self) -> KeyValueTreeItem:
        """ Returns an orphaned copy of this item.
        """
        item_copy = KeyValueTreeItem(self.key(), deepcopy(self.value()))
        item_copy.rebuildSubtree()
        return item_copy
    

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

    root = KeyValueTreeItem(None, tree)
    root.rebuildSubtree()
    print('-'*82)
    print(root)

    print('-'*82)
    print('remove /a')
    root['/a'].orphan()
    print(root)

    print('-'*82)
    print('remove /c/d/f')
    root['c/d/f'].orphan()
    print(root)

    print('-'*82)
    print('move /c/d to /d')
    d = root['c/d']
    d.orphan()
    root.appendChild(d)
    print(root)

    print('-'*82)
    print('move /d to 2nd child of /')
    d.orphan()
    root.insertChild(1, d)
    print(root)

    print('-'*82)
    print('move /d to 3rd child of /b')
    d.orphan()
    root['b'].insertChild(2, d)
    print(root)

    print('-'*82)
    print('remove /b/1')
    root['b/1'].orphan()
    print(root)

    print('-'*82)
    print('/c/me:hi -> /c/me:bye')
    me: KeyValueTreeItem = root['c/me']
    me.setValue('bye')
    print(root)

    print('-'*82)
    print('move /b/1 to first child of /c')
    b1 = root['b/1']
    b1.orphan()
    c: KeyValueTreeItem = root['c']
    c.insertChild(0, b1)
    print(root)

    print('-'*82)
    print('/c -> 82')
    c.setValue(82)
    print(root)

    print('-'*82)
    print('/c -> {a:1, b:2}')
    c.setValue({'a': 1, 'b': 2})
    print(root)

    print('-'*82)
    print('/nd')
    print(root['/nd'])


if __name__ == '__main__':
    test_tree()