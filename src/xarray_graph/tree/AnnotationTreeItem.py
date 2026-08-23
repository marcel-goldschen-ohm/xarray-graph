""" PyQt tree item for annotation dictionaries.
"""
from __future__ import annotations

from xarray_graph.tree.AbstractTreeItem import AbstractTreeItem


class AnnotationTreeItem(AbstractTreeItem):
    """ Holds either an annotation dict or a list of annotation dicts.
    """

    def __init__(self, data: dict | list[dict], group: str = None, parent: AnnotationTreeItem = None, sibling_index: int = None):
        self._data = data
        self._group = group
        super().__init__(parent, sibling_index)

    def isAnnotation(self) -> bool:
        # data is an annotation dict
        return isinstance(self._data, dict)
    
    def isGroup(self) -> bool:
        # data is a list of annotation dicts
        return isinstance(self._data, list)
    
    def group(self) -> str | None:
        if self.isRoot():
            return None
        elif self.isGroup():
            return self._group
        elif self.isAnnotation():
            annotation = self._data
            assert isinstance(annotation, dict)
            return annotation.get('group', None)
    
    def setGroup(self, group: str) -> None:
        if self.isGroup():
            for data in self._data:
                data['group'] = group
            self._group = group  # keep track of this so empty groups retain their group name
        elif self.isAnnotation():
            annotation = self._data
            assert isinstance(annotation, dict)
            annotation['group'] = group
    
    def name(self) -> str:
        if self.isGroup():
            return str(self.group() or '')
        elif self.isAnnotation():
            from xarray_graph.utils.Annotation import annotation_label
            annotation = self._data
            assert isinstance(annotation, dict)
            return annotation_label(annotation)
        raise TypeError('Cannot get name of item with invalid data type')
    
    def setName(self, name: str) -> None:
        if self.isGroup():
            self.setGroup(name)
        elif self.isAnnotation():
            annotation = self._data
            assert isinstance(annotation, dict)
            annotation['text'] = name
    
    def rebuildSubtree(self) -> None:
        """ Recursively build subtree if this item is a list of annotation dicts.
        """
        self.children = []
        if isinstance(self._data, list):
            groups = {}
            for child_data in self._data:
                group = child_data.get('group', '')
                if group in groups:
                    groups[group].append(child_data)
                else:
                    groups[group] = [child_data]
            ungrouped = groups.pop('', [])
            for group, group_data in groups.items():
                child = AnnotationTreeItem(group_data, group=group, parent=self)
                for grandchild_data in group_data:
                    grandchild = AnnotationTreeItem(grandchild_data, parent=child)
            for child_data in ungrouped:
                child = AnnotationTreeItem(child_data, parent=self)

    def orphan(self) -> None:
        if not self.parent:
            return
        
        if self.isGroup():
            annotations_to_remove = self._data
        elif self.isAnnotation():
            annotations_to_remove = [self._data]
        
        # Remove data from parent group item
        parent = self.parent
        assert isinstance(parent, AnnotationTreeItem)
        group_list = parent._data
        assert isinstance(group_list, list)
        for annotation in annotations_to_remove:
            assert annotation in group_list
            group_list.remove(annotation)

        # Remove from root flat list of annotations
        root = self.root()
        assert isinstance(root, AnnotationTreeItem)
        if parent is not root:
            root_list = root._data
            assert isinstance(root_list, list)
            for annotation in annotations_to_remove:
                assert annotation in root_list
                root_list.remove(annotation)
        
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
        root = self.root()
        assert isinstance(root, AnnotationTreeItem)
        if self is not root:
            root_list = root._data
            assert isinstance(root_list, list)
            annotation_at_index = self._data[index] if index < len(self._data) else None
            if annotation_at_index is not None:
                root_index = root_list.index(annotation_at_index)
            else:
                root_index = len(root._data)

        # insert in parent group
        group_list = self._data
        assert isinstance(group_list, list)
        for i, annotation in enumerate(annotations_to_insert):
            assert isinstance(annotation, dict)
            group_list.insert(index + i, annotation)
        
        # insert in root flat list of annotations
        if self is not root:
            for i, annotation in enumerate(annotations_to_insert):
                assert isinstance(annotation, dict)
                root_list.insert(root_index + i, annotation)
        
        # update inserted annotation group
        if item.isAnnotation():
            group = self.group() or ''
            annotation = item._data
            assert isinstance(annotation, dict)
            annotation['group'] = group
        
        # Update item linkage
        self.children.insert(index, item)
        item.parent = self
    
    def copy(self) -> AnnotationTreeItem:
        """ Returns an orphaned copy of this item.
        """
        from copy import deepcopy
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