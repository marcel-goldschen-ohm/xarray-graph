""" PyQt tree item for annotation dictionaries.
"""

from __future__ import annotations
import numpy as np
from xarray_graph.tree import AbstractTreeItem
from xarray_graph.utils import annotation_label
from copy import deepcopy


class AnnotationTreeItem(AbstractTreeItem):
    """ Holds either an annotation dict or a list of annotation dicts.
    """

    def __init__(self, data: dict | list[dict], group: str = None, parent: AnnotationTreeItem = None, sibling_index: int = None):
        self._data = data
        self._group = group
        super().__init__(parent, sibling_index)

    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(lambda item: item.name())
    
    def isAnnotation(self) -> bool:
        return isinstance(self._data, dict)
    
    def isGroup(self) -> bool:
        return isinstance(self._data, list)
    
    def rebuildSubtree(self) -> None:
        """ Recursively build subtree if this item is a list of annotation dicts.
        """
        self.children = []
        if isinstance(self._data, list):
            groups = {}
            for child_data in self._data:
                group = child_data.get('group', None)
                if group in groups:
                    groups[group].append(child_data)
                else:
                    groups[group] = [child_data]
            ungrouped = groups.pop(None, [])
            for group, group_data in groups.items():
                child = AnnotationTreeItem(group_data, group=group, parent=self)
                for grandchild_data in group_data:
                    grandchild = AnnotationTreeItem(grandchild_data, parent=child)
            for child_data in ungrouped:
                child = AnnotationTreeItem(child_data, parent=self)
    
    def group(self) -> str | None:
        if self.isGroup():
            return self._group
    
    def setGroup(self, group: str) -> None:
        if not self.isGroup():
            return
        for data in self._data:
            data['group'] = group
        self._group = group
    
    def name(self) -> str:
        if self.isGroup():
            return str(self.group())
        elif self.isAnnotation():
            return annotation_label(self._data)
    
    def setName(self, name: str) -> None:
        if self.isGroup():
            self.setGroup(name)
        elif self.isAnnotation():
            self._data['text'] = name

    def orphan(self) -> None:
        if not self.parent:
            return
        
        if self.isGroup():
            annotations_to_remove = self._data
        elif self.isAnnotation():
            annotations_to_remove = [self._data]
        
        # Remove data from parent group item
        parent: AnnotationTreeItem = self.parent
        for annotation in annotations_to_remove:
            parent._data.remove(annotation)

        # Remove from root flat list of annotations
        if parent is not self.root():
            root: AnnotationTreeItem = self.root()
            for annotation in annotations_to_remove:
                root._data.remove(annotation)
        
        # Update item linkage
        self.parent.children.remove(self)
        self.parent = None
    
    def insertChild(self, index: int, item: AnnotationTreeItem) -> None:
        if not self.isGroup():
            raise TypeError('Cannot insert child into non-group item')
        
        # Insert annotations
        if item.isGroup():
            annotations_to_insert = item._data
        elif item.isAnnotation():
            annotations_to_insert = [item._data]
        
        # find index in root flat list of annotations
        root: AnnotationTreeItem = self.root()
        if self is not root:
            annotation_at_index = self._data[index] if index < len(self._data) else None
            if annotation_at_index is not None:
                root_index = root._data.index(annotation_at_index)
            else:
                root_index = len(root._data)

        # insert in parent group
        for i, annotation in enumerate(annotations_to_insert):
            self._data.insert(index + i, annotation)
        
        # insert in root flat list of annotations
        if self is not root:
            for i, annotation in enumerate(annotations_to_insert):
                root._data.insert(root_index + i, annotation)
        
        # update inserted annotation group
        if self is root:
            for annotation in annotations_to_insert:
                if 'group' in annotation:
                    del annotation['group']
        else:
            group = self.group()
            for annotation in annotations_to_insert:
                annotation['group'] = group
        
        # Update item linkage
        self.children.insert(index, item)
        item.parent = self
    
    def copy(self) -> AnnotationTreeItem:
        """ Returns an orphaned copy of this item.
        """
        item_copy = AnnotationTreeItem(deepcopy(self._data), group=self._group, parent=None)
        item_copy.rebuildSubtree()
        return item_copy
    

def test_tree():

    annotations = [
        {'type': 'region', 'position': {'lat': [0, 1]}},
        {'type': 'region', 'position': {'lon': [2, 3]}},
        {'type': 'region', 'position': {'lat': [4, 5], 'lon': [6, 7]}, 'group': 'Group A'},
        {'type': 'region', 'position': {'lon': [6, 7]}, 'group': 'Group A', 'text': 'some text\nsecond line'},
        {'type': 'region', 'position': {'lat': [8, 9]}, 'group': 'Group B'},
    ]

    root = AnnotationTreeItem(annotations)
    root.rebuildSubtree()
    print('-'*82)
    print(root)


if __name__ == '__main__':
    test_tree()