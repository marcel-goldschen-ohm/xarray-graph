""" Generic tree item wrapper for a QAbstractItemModel.

Only implements parent/child linkage, you'll need to add any data in a derived class.
"""

from __future__ import annotations
from typing import Callable
from collections.abc import Iterator


class TreeItem():
    """ Tree item wrapper for a QAbstractItemModel.

    Only implements parent/child linkage, you'll need to add any data in a derived class.
    """

    def __init__(self, parent: TreeItem = None, sibling_index: int = -1):
        self.parent: TreeItem = parent
        self.children: list[TreeItem] = []
        if parent:
            if sibling_index == -1:
                parent.children.append(self)
            else:
                parent.children.insert(sibling_index, self)
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(repr)
    
    @property
    def row(self) -> int:
        if not self.parent:
            return 0
        return self.parent.children.index(self)
    
    @property
    def level(self) -> int:
        if self.is_node:
            return self.data.level
        return self.parent.level + 1
    
    @property
    def is_root(self) -> bool:
        return self.parent is None
    
    @property
    def is_leaf(self) -> bool:
        return not self.children
    
    @property
    def first_child(self) -> TreeItem | None:
        if self.children:
            return self.children[0]
    
    @property
    def last_child(self) -> TreeItem | None:
        if self.children:
            return self.children[-1]
    
    @property
    def next_sibling(self) -> TreeItem | None:
        if self.parent:
            siblings: list[TreeItem] = self.parent.children
            i: int = siblings.index(self)
            if i+1 < len(siblings):
                return siblings[i+1]
    
    @property
    def prev_sibling(self) -> TreeItem | None:
        if self.parent:
            siblings: list[TreeItem] = self.parent.children
            i: int = siblings.index(self)
            if i-1 >= 0:
                return siblings[i-1]
    
    def has_ancestor(self, item: TreeItem) -> bool:
        for ancestor in self.parents():
            if ancestor is item:
                return True
        return False
    
    def parents(self) -> Iterator[TreeItem]:
        item: TreeItem = self.parent
        while item is not None:
            yield item
            item = item.parent
    
    def subtree_depth_first(self) -> Iterator[TreeItem]:
        item: TreeItem = self
        end_item: TreeItem | None = self._last_depth_first()._next_depth_first()
        while item is not end_item:
            yield item
            item = item._next_depth_first()
    
    def subtree_reverse_depth_first(self) -> Iterator[TreeItem]:
        item: TreeItem = self._last_depth_first()
        end_item: TreeItem | None = self._prev_depth_first()
        while item is not end_item:
            yield item
            item = item._prev_depth_first()
    
    def _next_depth_first(self) -> TreeItem | None:
        if self.children:
            return self.first_child
        next_sibling: TreeItem = self.next_sibling
        if next_sibling:
            return next_sibling
        item: TreeItem = self.parent
        while item is not None:
            next_sibling: TreeItem = item.next_sibling
            if next_sibling:
                return next_sibling
            item = item.parent
        return None

    def _prev_depth_first(self) -> TreeItem | None:
        prev_sibling: TreeItem = self.prev_sibling
        if prev_sibling:
            return prev_sibling._last_depth_first()
        if self.parent:
            return self.parent
        return None
    
    def _last_depth_first(self) -> TreeItem:
        item: TreeItem = self
        while item.children:
            item = item.last_child
        return item
    
    def _tree_repr(self, func: Callable[[TreeItem], str] = None) -> str:
        """ Returns a multi-line string representation of this item's tree branch.

        Each item is described by the single line str returned by func(item).
        See __str__ for example.
        """
        if func is None:
            func = repr
        items: list[TreeItem] = list(self.subtree_depth_first())
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
