""" Generic tree item wrapper for a QAbstractItemModel.

TODO:
- breadth-first iteration
"""

from __future__ import annotations
from typing import Callable
from collections.abc import Iterator


class AbstractTreeItem():
    """ Generic tree item wrapper for a QAbstractItemModel.

    Only implements parent/child tree linkage. You'll need to add and manage any data (and override the `name` property) in a derived class.
    """

    # path separator
    _path_sep: str = '/'

    def __init__(self, parent: AbstractTreeItem = None, sibling_index: int = -1):
        self.parent: AbstractTreeItem = parent
        self.children: list[AbstractTreeItem] = []
        if parent:
            if sibling_index == -1:
                parent.children.append(self)
            else:
                parent.children.insert(sibling_index, self)
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(lambda item: item.name or self._path_sep)
    
    @property
    def name(self) -> str:
        """ Tree path key.
        
        This implementation is for testing/debugging. You should override this in a derived class.
        """
        return str(id(self))
    
    @property
    def path(self) -> str:
        if self.parent is None:
            return self.name or self._path_sep
        path_parts: list[str] = list(reversed([item.name for item in self.parents()])) + [self.name]
        return self._path_sep.join(path_parts)
    
    @property
    def row(self) -> int:
        if not self.parent:
            return 0
        return self.parent.children.index(self)
    
    @property
    def level(self) -> int:
        level: int = 0
        item: AbstractTreeItem = self
        while item.parent:
            level += 1
            item = item.parent
        return level
    
    @property
    def is_root(self) -> bool:
        return self.parent is None
    
    @property
    def is_leaf(self) -> bool:
        return not self.children
    
    @property
    def root(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.parent is not None:
            item = item.parent
        return item
    
    @property
    def first_child(self) -> AbstractTreeItem | None:
        if self.children:
            return self.children[0]
    
    @property
    def last_child(self) -> AbstractTreeItem | None:
        if self.children:
            return self.children[-1]
    
    @property
    def next_sibling(self) -> AbstractTreeItem | None:
        if self.parent:
            siblings: list[AbstractTreeItem] = self.parent.children
            i: int = siblings.index(self)
            if i+1 < len(siblings):
                return siblings[i+1]
    
    @property
    def prev_sibling(self) -> AbstractTreeItem | None:
        if self.parent:
            siblings: list[AbstractTreeItem] = self.parent.children
            i: int = siblings.index(self)
            if i-1 >= 0:
                return siblings[i-1]
    
    @property
    def _first_depth_first(self) -> AbstractTreeItem:
        return self
    
    @property
    def _last_depth_first(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.children:
            item = item.last_child
        return item
    
    @property
    def _next_depth_first(self) -> AbstractTreeItem | None:
        if self.children:
            return self.first_child
        next_sibling: AbstractTreeItem = self.next_sibling
        if next_sibling:
            return next_sibling
        item: AbstractTreeItem = self.parent
        while item is not None:
            next_sibling: AbstractTreeItem = item.next_sibling
            if next_sibling:
                return next_sibling
            item = item.parent
        return None

    @property
    def _prev_depth_first(self) -> AbstractTreeItem | None:
        prev_sibling: AbstractTreeItem = self.prev_sibling
        if prev_sibling:
            return prev_sibling._last_depth_first
        if self.parent:
            return self.parent
        return None
    
    @property
    def _first_leaf(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.children:
            item = item.first_child
        return item
    
    @property
    def _last_leaf(self) -> AbstractTreeItem:
        item: AbstractTreeItem = self
        while item.children:
            item = item.last_child
        return item
    
    @property
    def _next_leaf(self) -> AbstractTreeItem | None:
        try:
            return self._next_depth_first._first_leaf
        except Exception:
            return None

    @property
    def _prev_leaf(self) -> AbstractTreeItem | None:
        item: AbstractTreeItem | None = self._prev_depth_first
        while (item is not None) and item.children:
            item = item._prev_depth_first
        return item
    
    def parents(self) -> Iterator[AbstractTreeItem]:
        """ Iterate ancestors of this item from closest to most distant.
        """
        item: AbstractTreeItem = self.parent
        while item is not None:
            yield item
            item = item.parent
    
    def subtree_depth_first(self) -> Iterator[AbstractTreeItem]:
        """ Depth-first iteration of this item's subtree (inclusive of this item).
        """
        item: AbstractTreeItem = self
        end_item: AbstractTreeItem | None = self._last_depth_first._next_depth_first
        while item is not end_item:
            yield item
            item = item._next_depth_first
    
    def subtree_reverse_depth_first(self) -> Iterator[AbstractTreeItem]:
        """ Reverse depth-first iteration of this item's subtree (inclusive of this item).
        """
        item: AbstractTreeItem = self._last_depth_first
        end_item: AbstractTreeItem | None = self._prev_depth_first
        while item is not end_item:
            yield item
            item = item._prev_depth_first
    
    def subtree_leaves(self) -> Iterator[AbstractTreeItem]:
        """ Iterate leaves of this item's subtree (leaves ordered depth-first).
        """
        item: AbstractTreeItem = self._first_leaf
        end_item: AbstractTreeItem | None = self._last_leaf._next_leaf
        while item is not end_item:
            yield item
            item = item._next_leaf
    
    def subtree_reverse_leaves(self) -> Iterator[AbstractTreeItem]:
        """ Iterate leaves of this item's subtree in reverse (leaves ordered reverse depth-first).
        """
        item: AbstractTreeItem = self._last_leaf
        end_item: AbstractTreeItem | None = self._first_leaf._prev_leaf
        while item is not end_item:
            yield item
            item = item._prev_leaf
    
    def subtree_max_depth(self) -> int:
        """ Maximum depth of this item's entire subtree.
        """
        max_depth: int = 0
        for leaf in self.subtree_leaves():
            depth: int = leaf.level - self.level
            if depth > max_depth:
                max_depth = depth
        return max_depth
    
    def orphan(self) -> None:
        if self.parent:
            self.parent.children.remove(self)
            self.parent = None
    
    def append_child(self, item: AbstractTreeItem) -> None:
        self.children.append(item)
        item.parent = self
    
    def insert_child(self, index: int, item: AbstractTreeItem) -> None:
        self.children.insert(index, item)
        item.parent = self
    
    def has_ancestor(self, item: AbstractTreeItem) -> bool:
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
            func = lambda item: item.name or self._path_sep
        items: list[AbstractTreeItem] = list(self.subtree_depth_first())
        lines: list[str] = [func(item) for item in items]
        for i, item in enumerate(items):
            if item is self:
                continue
            if item is item.parent.last_child:
                lines[i] = '\u2514' + '\u2500'*2 + ' ' + lines[i]
            else:
                lines[i] = '\u251C' + '\u2500'*2 + ' ' + lines[i]
            parent = item.parent
            while parent is not self:
                if i < items.index(parent.parent.last_child):
                    lines[i] = '\u2502' + ' '*3 + lines[i]
                else:
                    lines[i] = ' '*4 + lines[i]
                parent = parent.parent
        return '\n'.join(lines)


def test_tree():
    
    class MyTreeItem(AbstractTreeItem):

        def __init__(self, name: str = '', parent: AbstractTreeItem = None, sibling_index: int = -1):
            super().__init__(parent, sibling_index)
            self._name = name
        
        @property
        def name(self) -> str:
            return self._name

    root = MyTreeItem('r')
    a = MyTreeItem('a', parent=root)
    b = MyTreeItem('b')
    c = MyTreeItem('c')
    d = MyTreeItem('d')
    e = MyTreeItem('e', parent=b)
    f = MyTreeItem('f', parent=e)
    root.append_child(b)
    root.insert_child(1, c)
    root.children[1].append_child(d)
    
    print('\nInitial tree...')
    print(root)

    print('\nInitial tree...')
    print(root._tree_repr(lambda item: str(id(item))))

    print('\nDepth-first iteration...')
    for item in root.subtree_depth_first():
        print(item.name or ' ', item.path)

    print('\nReverse depth-first iteration...')
    for item in root.subtree_reverse_depth_first():
        print(item.name or ' ', item.path)

    print('\nLeaf iteration...')
    for item in root.subtree_leaves():
        print(item.name or ' ', item.path)

    print('\nReverse leaf iteration...')
    for item in root.subtree_reverse_leaves():
        print(item.name or ' ', item.path)

    print(f'\nRemove {e.name}...')
    e.orphan()
    print(root)

    print(f'\nInsert {e.name}...')
    b.append_child(e)
    print(root)


if __name__ == '__main__':
    test_tree()
