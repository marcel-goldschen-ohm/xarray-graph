""" PyQt tree item for a key: value mapping (with any amount of nesting).
"""
from __future__ import annotations

from xarray_graph.tree.AbstractTreeItem import AbstractTreeItem


class KeyValueTreeItem(AbstractTreeItem):
    """ Holds a key:value pair and parent-child linkage for nested structures.
    """

    def __init__(self, key, value, parent: KeyValueTreeItem = None, sibling_index: int = None):
        self._key = key
        self._value = value
        super().__init__(parent, sibling_index)

    def __repr__(self) -> str:
            """ Returns a single-line string representation of this item.
            """
            return f'{self.key()}: {self.value()}'
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr()
    
    def key(self):
        # if this item is in a list, return the item's sibling index
        parent = self.parent
        if isinstance(parent, KeyValueTreeItem) and isinstance(parent.value(), list):
            return self.siblingIndex()
        # otherwise, return the item's key
        return self._key
    
    def setKey(self, key) -> None:
        # if this item is in a dict, update the key in the parent dict
        parent = self.parent
        if isinstance(parent, KeyValueTreeItem):
            parent_map: dict | list = parent.value()
            if isinstance(parent_map, dict):
                # we only need to update the underlying data for dicts, since lists are indexed by sibling order
                parent_map[key] = parent_map.pop(self.key())
        # update this item's key
        self._key = key
    
    def value(self):
        return self._value
    
    def setValue(self, value) -> None:
        parent = self.parent
        if isinstance(parent, KeyValueTreeItem):
            parent_map: dict | list = parent.value()
            parent_map[self.key()] = value
        self._value = value
        self.rebuildSubtree()
    
    def name(self) -> str:
        # the name is just the key
        key = self.key()
        if key is None and self.parent is None:
            # root item can have no key, so we return the path separator as its name
            return self._path_sep
        return str(key)
    
    def setName(self, name: str) -> None:
        # the name is just the key
        self.setKey(name)
    
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

    def orphan(self) -> None:
        if not self.parent:
            return
        
        # Remove value from parent map
        parent = self.parent
        assert isinstance(parent, KeyValueTreeItem)
        parent.value().pop(self.key())
        
        # Update item linkage
        self.parent.children.remove(self)
        self.parent = None
    
    def insertChild(self, index: int, item: KeyValueTreeItem) -> None:
        # Insert child value into this map
        value = self.value()
        if isinstance(value, dict):
            item_key = item.key()
            if item_key in value:
                raise KeyError(f'Key {item_key} already exists in dict')
            value[item_key] = item.value()
        elif isinstance(value, list):
            value.insert(index, item.value())
        else:
            raise TypeError(f'Cannot insert child into value of type {type(value)}')

        # Update item linkage
        self.children.insert(index, item)
        item.parent = self
    
    def copy(self) -> KeyValueTreeItem:
        """ Returns an orphaned copy of this item.
        """
        from copy import deepcopy
        item_copy = KeyValueTreeItem(self.key(), deepcopy(self.value()))
        item_copy.rebuildSubtree()
        return item_copy
    

def test_tree():
    import numpy as np
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
    assert isinstance(d, KeyValueTreeItem)
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
    me = root['c/me']
    assert isinstance(me, KeyValueTreeItem)
    me.setValue('bye')
    print(root)

    print('-'*82)
    print('move /b/1 to first child of /c')
    b1 = root['b/1']
    assert isinstance(b1, KeyValueTreeItem)
    b1.orphan()
    c = root['c']
    assert isinstance(c, KeyValueTreeItem)
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