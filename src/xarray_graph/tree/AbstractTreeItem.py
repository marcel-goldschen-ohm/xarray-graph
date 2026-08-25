""" Generic tree item wrapper for a QAbstractItemModel.
"""
from __future__ import annotations

from typing import Self, Callable
from collections.abc import Iterator


class AbstractTreeItem():
    """ Generic tree item wrapper for a QAbstractItemModel.

    Only implements parent/child tree linkage. You'll need to add and manage any data in a derived class.

    Override in a derived class:
    - rebuildSubtree() - build item tree based on tree data
    - name() - for tree path access. e.g., see __getitem__()
    - setName() - for tree path modification. e.g., see __setitem__()
    - orphan() - update tree data when pruning the tree
    - insertChild() - update tree data when growing the tree
    - copy() - for copying tree data when copying tree items
    """

    # path separator
    _path_sep: str = '/'

    def __init__(self, parent: Self | None = None, sibling_index: int = None):
        self.parent: Self | None = parent
        self.children: list[Self] = []
        if parent:
            if sibling_index is None:
                # default to appending to end of parent's children list
                sibling_index = len(parent.children)
            # update item linkage only (no data management during init)
            parent.children.insert(sibling_index, self)

        # store view state (e.g., expanded/collapsed, selected, etc.)
        self._view_state: dict = {}
    
    def __repr__(self) -> str:
        """ Returns a single-line string representation of this item.
        """
        return self.name() or (self._path_sep if self.isRoot() else str(id(self)))

    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        item_str_func: Callable[[Self], str] = lambda item: repr(item)
        return self._tree_repr(item_str_func)
    
    def _tree_repr(self, item_str_func: Callable[[Self], str] = None) -> str:
            """ Returns a multi-line string representation of this item's tree branch.
    
            Each item is described by the single line str returned by item_str_func(item).
            """
            if item_str_func is None:
                item_str_func = lambda item: repr(item)
            items: list[Self] = list(self.subtree_depth_first())
            lines: list[str] = [item_str_func(item) for item in items]
            for i, item in enumerate(items):
                if item is self:
                    continue
                # as we skipped self (the root of the subtree), all other items must have a parent
                assert item.parent is not None
                if item is item.parent.lastChild():
                    lines[i] = '\u2514' + '\u2500'*2 + ' ' + lines[i]
                else:
                    lines[i] = '\u251C' + '\u2500'*2 + ' ' + lines[i]
                parent = item.parent
                while parent is not self:
                    # if parent is not self (the root of the subtree), parent must itself have a valid parent, and that parent's last descendant must be valid as well
                    parent_of_parent = parent.parent
                    assert parent_of_parent is not None
                    last_descendant = parent_of_parent.lastChild()
                    assert last_descendant is not None
                    if i < items.index(last_descendant):
                        lines[i] = '\u2502' + ' '*3 + lines[i]
                    else:
                        lines[i] = ' '*4 + lines[i]
                    parent = parent_of_parent
            return '\n'.join(lines)
        
    def __getitem__(self, path: str) -> Self:
        """ Return subtree item at path starting from this item.

        !! For unique item access, all paths in the tree must be unique.
           Unique paths are not a requirement, it is up to you to enforce this if you want it.
           If the path is not unique, the first item with path is returned.
        """
        if path.startswith(self._path_sep):
            # path is absolute, so start from root
            item = self.root()
        else:
            # path is relative, so start from this item
            item = self
        path = path.strip(self._path_sep)
        if not path:
            return item
        path_parts = path.split(self._path_sep)
        for name in path_parts:
            child_names = [child.name() for child in item.children]
            child_index = child_names.index(name)
            item = item.children[child_index]
            # if child_names.count(name) > 1:
            #     from warnings import warn
            #     warn('Path is not unique.')
        return item
    
    def __setitem__(self, path: str, new_item: Self) -> None:
        """ Set subtree item at path starting from this item.

        For nonexistent paths, new items will be created to ensure validity of the path.

        !! For unique item access, all paths in the tree must be unique.
           Unique paths are not a requirement, it is up to you to enforce this if you want it.
           If the path is not unique, the first item with path will be set to the new item.
        """
        if path.startswith(self._path_sep):
            # path is absolute, so start from root
            item = self.root()
        else:
            # path is relative, so start from this item
            item = self
        path = path.strip(self._path_sep)
        path_parts = path.split(self._path_sep)
        if len(path_parts) == 0:
            if item is self:
                raise ValueError('An item cannot set itself to a new item.')
            if item.parent is None:
                raise ValueError('An item cannot set the root item to a new item.')
        for name in path_parts[:-1]:
            try:
                child_names = [child.name() for child in item.children]
                child_index = child_names.index(name)
                item = item.children[child_index]
                # if child_names.count(name) > 1:
                #     from warnings import warn
                #     warn('Path is not unique.')
            except ValueError:
                # create new tree item to ensure validity of path
                NewItemType = type(new_item)
                item = NewItemType(parent=item)
                item.setName(name)
        # set new_item at path
        new_item_name = path_parts[-1]
        if new_item.parent is not None:
            new_item.orphan()  # remove new_item from its current parent
        new_item.setName(new_item_name)
        child_names = [child.name() for child in item.children]
        if new_item_name in child_names:
            # replace item at path with new_item
            child_index = child_names.index(new_item_name)
            item.children[child_index].orphan()  # remove current item at path
            item.insertChild(child_index, new_item)  # insert new_item at path
        else:
            # add new_item at path
            item.appendChild(new_item)
    
    def viewState(self) -> dict:
        return self._view_state

    def setViewState(self, view_state: dict) -> None:
        self._view_state = view_state

    # Override in derived class with data-specific logic.
    
    def rebuildSubtree(self) -> None:
        """ Recursively build item subtree based on this item's data.
        """
        raise NotImplementedError('Implement in derived class with data-specific logic.')
    
    def name(self) -> str:
        """ Tree path key.
        
        This implementation is for testing/debugging. Override in a derived class to get name from data.
        """
        return getattr(self, '_name', str(id(self)))
    
    def setName(self, name: str) -> None:
        """ Tree path key.
        
        This implementation is for testing/debugging. Override in a derived class to modify data.
        """
        setattr(self, '_name', name)
    
    def orphan(self) -> None:
        """ Remove this item from its parent.
        
        Override in a derived class to update tree data.
        """
        if not self.parent:
            return
        
        # !! WARNING: Update tree data in derived class...
        
        # Update item linkage
        self.parent.children.remove(self)
        self.parent = None
    
    def insertChild(self, index: int, item: Self) -> None:
        """ Insert a child item at the specified index.

        Override in a derived class to update tree data.
        """
        # !! WARNING: Update tree data in derived class...

        # Update item linkage
        self.children.insert(index, item)
        item.parent = self
    
    def copy(self) -> Self:
        """ Returns an orphaned copy of this item.

        This implementation is for testing/debugging. Override in a derived class to copy tree data.
        """
        from copy import deepcopy

        cls = type(self)
        item_copy = cls()
        item_copy.setName(self.name())
        item_copy.setViewState(deepcopy(self.viewState()))

        # !! WARNING: Copy tree data in derived class...

        # recursively copy children
        for child in self.children:
            child_copy = child.copy()
            item_copy.appendChild(child_copy)
        return item_copy
    
    # Methods below should not need to be overridden.
    
    # Basics
    
    def root(self) -> Self:
        item = self
        while item.parent is not None:
            item = item.parent
        return item
    
    def path(self) -> str:
        """ Absolute path from the root of the tree to this item.

        The path does not include the name of the root item, just a leading path separator.
        """
        if self.parent is None:
            return self._path_sep
        path_parts: list[str] = list(reversed([item.name() for item in self.parents()])) + [self.name()]
        path_parts[0] = ''
        return self._path_sep.join(path_parts)
    
    def row(self) -> int:
        return self.siblingIndex()
    
    def level(self) -> int:
        level: int = 0
        item = self
        while item.parent:
            level += 1
            item = item.parent
        return level
    
    def subtreeDepth(self) -> int:
        """ Maximum depth of this item's entire subtree.
        """
        max_depth: int = 0
        for leaf in self.subtree_leaves():
            depth: int = leaf.level() - self.level()
            if depth > max_depth:
                max_depth = depth
        return max_depth
    
    def isRoot(self) -> bool:
        return self.parent is None
    
    def isLeaf(self) -> bool:
        return not self.children
    
    def hasAncestor(self, item: Self) -> bool:
        for ancestor in self.parents():
            if ancestor is item:
                return True
        return False
    
    def appendChild(self, item: Self) -> None:
        index: int = len(self.children)
        self.insertChild(index, item)
    
    # Tree traversal
    
    def firstChild(self) -> Self | None:
        if self.children:
            return self.children[0]
    
    def lastChild(self) -> Self | None:
        if self.children:
            return self.children[-1]
    
    def nextSibling(self) -> Self | None:
        if self.parent:
            siblings: list[Self] = self.parent.children
            i: int = siblings.index(self)
            if i+1 < len(siblings):
                return siblings[i+1]
    
    def prevSibling(self) -> Self | None:
        if self.parent:
            siblings: list[Self] = self.parent.children
            i: int = siblings.index(self)
            if i-1 >= 0:
                return siblings[i-1]
    
    def siblingIndex(self) -> int:
        if not self.parent:
            return 0
        return self.parent.children.index(self)
    
    def next(self) -> Self | None:
        """ Returns the next item in a depth-first traversal of the tree.
        """
        if self.children:
            return self.firstChild()
        next_sibling = self.nextSibling()
        if next_sibling:
            return next_sibling
        item = self.parent
        while item is not None:
            next_sibling = item.nextSibling()
            if next_sibling:
                return next_sibling
            item = item.parent
        return None

    def prev(self) -> Self | None:
        """ Returns the previous item in a depth-first traversal of the tree.
        """
        prev_sibling = self.prevSibling()
        if prev_sibling:
            return prev_sibling.lastLeaf()
        if self.parent:
            return self.parent
        return None
    
    def firstLeaf(self) -> Self:
        item = self
        while item.children:
            item = item.children[0]
        return item
    
    def lastLeaf(self) -> Self:
        item = self
        while item.children:
            item = item.children[-1]
        return item
    
    def nextLeaf(self) -> Self | None:
        next = self.next()
        if next is not None:
            return next.firstLeaf()

    def prevLeaf(self) -> Self | None:
        item = self.prev()
        while (item is not None) and item.children:
            item = item.prev()
        return item
    
    # Ancestor iteration
    
    def parents(self) -> Iterator[Self]:
        """ Iterate ancestors of this item from closest to most distant.
        """
        item = self.parent
        while item is not None:
            yield item
            item = item.parent
    
    # Subtree iteration
    
    def subtree_depth_first(self) -> Iterator[Self]:
        """ Depth-first iteration of this item's subtree (inclusive of this item).
        """
        item = self
        end_item = self.lastLeaf().next()
        while (item is not None) and (item is not end_item):
            yield item
            item = item.next()
    
    def subtree_reverse_depth_first(self) -> Iterator[Self]:
        """ Reverse depth-first iteration of this item's subtree (inclusive of this item).
        """
        item = self.lastLeaf()
        end_item = self.prev()
        while (item is not None) and (item is not end_item):
            yield item
            item = item.prev()
    
    def subtree_breadth_first(self) -> Iterator[Self]:
        """ Breadth-first iteration of this item's subtree (inclusive of this item).
        """
        level_items: list[Self] = [self]
        index: int = 0
        while True:
            if index >= len(level_items):
                # get all items on next level
                level_items = [child for item in level_items for child in item.children]
                if not level_items:
                    return
                index = 0
            yield level_items[index]
            index += 1
    
    def subtree_leaves(self) -> Iterator[Self]:
        """ Iterate leaves of this item's subtree (leaves ordered depth-first).
        """
        item = self.firstLeaf()
        end_item = self.lastLeaf().nextLeaf()
        while (item is not None) and (item is not end_item):
            yield item
            item = item.nextLeaf()
    
    def subtree_reverse_leaves(self) -> Iterator[Self]:
        """ Iterate leaves of this item's subtree in reverse (leaves ordered reverse depth-first).
        """
        item = self.lastLeaf()
        end_item = self.firstLeaf().prevLeaf()
        while (item is not None) and (item is not end_item):
            yield item
            item = item.prevLeaf()
    

def test_tree():
    
    class MyTreeItem(AbstractTreeItem):

        def __init__(self, data: str = '', parent: Self | None = None, sibling_index: int = None):
            super().__init__(parent, sibling_index)
            self.data = data
        
        def name(self) -> str:
            return self.data

        def setName(self, name: str) -> None:
            self.data = name

    root = MyTreeItem('r')
    a = MyTreeItem('a', parent=root)
    b = MyTreeItem('b')
    c = MyTreeItem('c')
    d = MyTreeItem('d')
    e = MyTreeItem('e', parent=b)
    f = MyTreeItem('f', parent=e)
    root.appendChild(b)
    root.insertChild(1, c)
    root.children[1].appendChild(d)
    
    print('\nInitial tree...')
    print(root)

    # print('\nInitial tree...')
    # print(root._tree_repr(lambda item: str(id(item))))

    print('\nDepth-first iteration...')
    for item in root.subtree_depth_first():
        print(item.name() or ' ', item.path())

    print('\nReverse depth-first iteration...')
    for item in root.subtree_reverse_depth_first():
        print(item.name() or ' ', item.path())

    print('\nBreadth-first iteration...')
    for item in root.subtree_breadth_first():
        print(item.name() or ' ', item.path())

    print('\nLeaf iteration...')
    for item in root.subtree_leaves():
        print(item.name() or ' ', item.path())

    print('\nReverse leaf iteration...')
    for item in root.subtree_reverse_leaves():
        print(item.name() or ' ', item.path())

    print(f'\nRemove {e.name()}...')
    e.orphan()
    print(root)

    print(f'\nInsert {e.name()}...')
    b.appendChild(e)
    print(root)


if __name__ == '__main__':
    test_tree()
