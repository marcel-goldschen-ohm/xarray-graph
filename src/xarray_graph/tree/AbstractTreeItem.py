""" Generic tree item wrapper for a QAbstractItemModel.
"""

from __future__ import annotations
from typing import Callable
from collections.abc import Iterator
from warnings import warn
from copy import deepcopy


class AbstractTreeItem():
    """ Generic tree item wrapper for a QAbstractItemModel.

    Only implements parent/child tree linkage. You'll need to add and manage any data in a derived class.

    Override in a derived class:
    - updateSubtree() - build item tree based on tree data
    - name() - for tree path access. e.g., see __getitem__()
    - setName() - for tree path modification. e.g., see __setitem__()
    - orphan() - update tree data when pruning the tree
    - insertChild() - update tree data when growing the tree
    - copy() - for copying tree data when copying tree items
    """

    # path separator
    _path_sep: str = '/'

    def __init__(self, parent: AbstractTreeItem = None, sibling_index: int = None):
        self.parent: AbstractTreeItem = parent
        self.children: list[AbstractTreeItem] = []
        if parent:
            if sibling_index is None:
                sibling_index = len(parent.children)
            # update item linkage only (no data management during init)
            parent.children.insert(sibling_index, self)
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(lambda item: item.name() or self._path_sep)
    
    def __getitem__(self, path: str) -> AbstractTreeItem:
        """ Return subtree item at path starting from this item.

        !! For unique item access, all paths in the tree must be unique.
           Unique paths are not a requirement, it is up to you to enforce this if you want it.
           If the path is not unique, the first item with path is returned.
        """
        item: AbstractTreeItem = self
        stripped_path = path.strip(self._path_sep)
        if not stripped_path:
            return self
        path_parts = stripped_path.split(self._path_sep)
        for name in path_parts:
            try:
                child_names = [child.name() for child in item.children]
                child_index = child_names.index(name)
                item = item.children[child_index]
                if child_names.count(name) > 1:
                    warn('Path is not unique.')
            except Exception as error:
                warn(str(error))
                return None
        return item
    
    def __setitem__(self, path: str, new_item: AbstractTreeItem) -> None:
        """ Set subtree item at path starting from this item.

        !! For unique item access, all paths in the tree must be unique.
           Unique paths are not a requirement, it is up to you to enforce this if you want it.
           If the path is not unique, the first item with path will be set to the new item.
        """
        item: AbstractTreeItem = self
        path_parts = path.strip('/').split('/')
        if len(path_parts) == 0:
            raise ValueError('An item cannot set itself to a new item.')
        for name in path_parts[:-1]:
            try:
                child_names = [child.name() for child in item.children]
                child_index = child_names.index(name)
                item = item.children[child_index]
                if child_names.count(name) > 1:
                    warn('Path is not unique.')
            except Exception as error:
                # create new tree item to ensure validity of path
                new_item_type = type(new_item)
                item = new_item_type(parent=item)
                item.setName(name)
        # set new_item at path
        new_item_name = path_parts[-1]
        child_names = [child.name() for child in item.children]
        if new_item_name in child_names:
            # replace item at path with new_item
            child_index = child_names.index(new_item_name)
            item.children[child_index].orphan()  # remove current item at path
            item.insertChild(child_index, new_item)  # insert new_item at path
        else:
            # add new_item at path
            item.appendChild(new_item)
        # name new_item according to path (ignore's new_item's current name)
        new_item.setName(new_item_name)
    
    # Override in derived class with data-specific logic.
    
    def rebuildSubtree(self) -> None:
        """ Recursively build item subtree based on this item's data.
        """
        raise NotImplementedError('Implement in derived class with data-specific logic.')
    
    def name(self) -> str:
        """ Tree path key.
        
        This implementation is for testing/debugging. Override in a derived class to get name from data.
        """
        try:
            return self._name
        except AttributeError:
            return str(id(self))
    
    def setName(self, name: str) -> None:
        """ Tree path key.
        
        This implementation is for testing/debugging. Override in a derived class to modify data.
        """
        raise NotImplementedError('Implement in derived class with data-specific logic.')
        # use below for testing/debugging if not implementing setName in derived class
        self._name = name
    
    def orphan(self) -> None:
        """ Remove this item from its parent.
        
        Override in a derived class to update tree data.
        """
        if not self.parent:
            return
        
        # Update tree data
        # TODO: implement in derived class...
        
        # Update item linkage
        self.parent.children.remove(self)
        self.parent = None
    
    def insertChild(self, index: int, item: AbstractTreeItem) -> None:
        """ Insert a child item at the specified index.

        Override in a derived class to update tree data.
        """
        # Update tree data
        # TODO: implement in derived class...

        # Update item linkage
        self.children.insert(index, item)
        item.parent = self
    
    def copy(self) -> AbstractTreeItem:
        """ Returns an orphaned copy of this item.

        This implementation is for testing/debugging. Override in a derived class to copy tree data.
        """
        item_copy = AbstractTreeItem()
        item_copy.setName(self.name()) # testing/debugging just copies name
        try:
            item_copy._view_state = deepcopy(self._view_state)
        except AttributeError:
            pass
        # recursively copy children
        for child in self.children:
            child_copy = child.copy()
            item_copy.appendChild(child_copy)
            try:
                child_copy._view_state = deepcopy(child._view_state)
            except AttributeError:
                pass
        return item_copy
    
    # Methods below should not need to be overridden.
    
    # Basics
    
    def root(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.parent is not None:
            item = item.parent
        return item
    
    def path(self) -> str:
        if self.parent is None:
            return self._path_sep
        path_parts: list[str] = list(reversed([item.name() for item in self.parents()])) + [self.name()]
        # if path_parts[0] == self._path_sep:
        #     path_parts[0] = ''
        return self._path_sep.join(path_parts[1:])
    
    def row(self) -> int:
        return self.siblingIndex()
    
    def level(self) -> int:
        level: int = 0
        item: AbstractTreeItem = self
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
    
    def hasAncestor(self, item: AbstractTreeItem) -> bool:
        for ancestor in self.parents():
            if ancestor is item:
                return True
        return False
    
    def _tree_repr(self, func: Callable[[AbstractTreeItem], str] = None) -> str:
        """ Returns a multi-line string representation of this item's tree branch.

        Each item is described by the single line str returned by func(item).
        See __str__ for example.
        """
        if func is None:
            func = lambda item: item.name() or self._path_sep
        items: list[AbstractTreeItem] = list(self.subtree_depth_first())
        lines: list[str] = [func(item) for item in items]
        for i, item in enumerate(items):
            if item is self:
                continue
            if item is item.parent.lastChild():
                lines[i] = '\u2514' + '\u2500'*2 + ' ' + lines[i]
            else:
                lines[i] = '\u251C' + '\u2500'*2 + ' ' + lines[i]
            parent = item.parent
            while parent is not self:
                if i < items.index(parent.parent.lastChild()):
                    lines[i] = '\u2502' + ' '*3 + lines[i]
                else:
                    lines[i] = ' '*4 + lines[i]
                parent = parent.parent
        return '\n'.join(lines)
    
    def appendChild(self, item: AbstractTreeItem) -> bool:
        index: int = len(self.children)
        return self.insertChild(index, item)
    
    @staticmethod
    def orderedItems(items: list[AbstractTreeItem], order='depth-first') -> list[AbstractTreeItem]:
        """ Returns the input items ordered according to their position in the tree.
        """
        if not items:
            return []
        root = items[0].root()
        ordered_items: list[AbstractTreeItem] = []
        if order == 'depth-first':
            for item in root.subtree_depth_first():
                if item in items:
                    ordered_items.append(item)
        elif order == 'breadth-first':
            for item in root.subtree_breadth_first():
                if item in items:
                    ordered_items.append(item)
        return ordered_items
    
    # Tree traversal
    
    def firstChild(self) -> AbstractTreeItem | None:
        if self.children:
            return self.children[0]
    
    def lastChild(self) -> AbstractTreeItem | None:
        if self.children:
            return self.children[-1]
    
    def nextSibling(self) -> AbstractTreeItem | None:
        if self.parent:
            siblings: list[AbstractTreeItem] = self.parent.children
            i: int = siblings.index(self)
            if i+1 < len(siblings):
                return siblings[i+1]
    
    def prevSibling(self) -> AbstractTreeItem | None:
        if self.parent:
            siblings: list[AbstractTreeItem] = self.parent.children
            i: int = siblings.index(self)
            if i-1 >= 0:
                return siblings[i-1]
    
    def siblingIndex(self) -> int:
        if not self.parent:
            return 0
        return self.parent.children.index(self)
    
    def next(self) -> AbstractTreeItem | None:
        """ Returns the next item in a depth-first traversal of the tree.
        """
        if self.children:
            return self.firstChild()
        next_sibling: AbstractTreeItem = self.nextSibling()
        if next_sibling:
            return next_sibling
        item: AbstractTreeItem = self.parent
        while item is not None:
            next_sibling: AbstractTreeItem = item.nextSibling()
            if next_sibling:
                return next_sibling
            item = item.parent
        return None

    def prev(self) -> AbstractTreeItem | None:
        """ Returns the previous item in a depth-first traversal of the tree.
        """
        prev_sibling: AbstractTreeItem = self.prevSibling()
        if prev_sibling:
            return prev_sibling.lastLeaf()
        if self.parent:
            return self.parent
        return None
    
    def firstLeaf(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.children:
            item = item.firstChild()
        return item
    
    def lastLeaf(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.children:
            item = item.lastChild()
        return item
    
    def nextLeaf(self) -> AbstractTreeItem | None:
        try:
            return self.next().firstLeaf()
        except Exception:
            return None

    def prevLeaf(self) -> AbstractTreeItem | None:
        item: AbstractTreeItem | None = self.prev()
        while (item is not None) and item.children:
            item = item.prev()
        return item
    
    # Ancestor iteration
    
    def parents(self) -> Iterator[AbstractTreeItem]:
        """ Iterate ancestors of this item from closest to most distant.
        """
        item: AbstractTreeItem = self.parent
        while item is not None:
            yield item
            item = item.parent
    
    # Subtree iteration
    
    def subtree_depth_first(self) -> Iterator[AbstractTreeItem]:
        """ Depth-first iteration of this item's subtree (inclusive of this item).
        """
        item: AbstractTreeItem = self
        end_item: AbstractTreeItem | None = self.lastLeaf().next()
        while item is not end_item:
            yield item
            item = item.next()
    
    def subtree_reverse_depth_first(self) -> Iterator[AbstractTreeItem]:
        """ Reverse depth-first iteration of this item's subtree (inclusive of this item).
        """
        item: AbstractTreeItem = self.lastLeaf()
        end_item: AbstractTreeItem | None = self.prev()
        while item is not end_item:
            yield item
            item = item.prev()
    
    def subtree_breadth_first(self) -> Iterator[AbstractTreeItem]:
        """ Breadth-first iteration of this item's subtree (inclusive of this item).
        """
        level_items: list[AbstractTreeItem] = [self]
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
    
    def subtree_leaves(self) -> Iterator[AbstractTreeItem]:
        """ Iterate leaves of this item's subtree (leaves ordered depth-first).
        """
        item: AbstractTreeItem = self.firstLeaf()
        end_item: AbstractTreeItem | None = self.lastLeaf().nextLeaf()
        while item is not end_item:
            yield item
            item = item.nextLeaf()
    
    def subtree_reverse_leaves(self) -> Iterator[AbstractTreeItem]:
        """ Iterate leaves of this item's subtree in reverse (leaves ordered reverse depth-first).
        """
        item: AbstractTreeItem = self.lastLeaf()
        end_item: AbstractTreeItem | None = self.firstLeaf().prevLeaf()
        while item is not end_item:
            yield item
            item = item.prevLeaf()


def test_tree():
    
    class MyTreeItem(AbstractTreeItem):

        def __init__(self, data: str = '', parent: AbstractTreeItem = None, sibling_index: int = None):
            super().__init__(parent, sibling_index)
            self.data = data
        
        def name(self) -> str:
            return self.data

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
