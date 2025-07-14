""" Data interface for metadata annotations in an Xarray DataTree.

Expects that DataTree/DataArray.attrs['annotations'] is a list of dictionaries, each representing an annotation.

Keys other than 'annotations' can be specified via the `attrs_key` parameter in the constructor.

Annotations can be grouped by a 'group' key in each annotation dictionary.
"""

from __future__ import annotations
from warnings import warn
from typing import Any
import xarray as xr
from qtpy.QtWidgets import *
from pyqt_ext.tree import AbstractTreeItem


class AnnotationTreeItem(AbstractTreeItem):
    
    def __init__(self, data: xr.DataTree | xr.DataArray | str | dict = None, parent: AnnotationTreeItem | None = None, attrs_key: str = 'annotations') -> None:
        super().__init__()
        self.data = data
        self.attrs_key = attrs_key
        if parent is not None:
            self._parent = parent
            parent.children.append(self)
    
    def name(self) -> str:
        if isinstance(self.data, xr.DataTree):
            return self.data.name
        elif isinstance(self.data, xr.DataArray):
            return self.data.name
        elif isinstance(self.data, str):
            # group name
            return self.data
        elif isinstance(self.data, dict):
            # annotation dict
            return self._get_annotation_label(self.data)
    
    def setName(self, name: str) -> None:
        if isinstance(self.data, str):
            # group name
            group = str(name).strip()
            if not group:
                return
            if group == self.data:
                # no change
                return
            parent_item: AbstractTreeItem = self.parent()
            groups = [child_item.name() for child_item in parent_item.children if isinstance(getattr(child_item, 'data', None), str)]
            if group in groups:
                # group already exists
                focused_widget: QWidget = QApplication.focusWidget()
                QMessageBox.warning(focused_widget, 'Group already exists', f'Group "{group}" already exists.')
                return
            # update group name
            self.data = group
            for annotation_item in self.children:
                annotation = getattr(annotation_item, 'data', None)
                if annotation is not None:
                    # update annotation group
                    annotation['group'] = group
        elif isinstance(self.data, dict):
            # annotation dict
            self._set_annotation_label(self.data, name)
    
    def _get_annotations(self) -> list[dict]:
        """ Get the annotations associated with this item.
        """
        if isinstance(self.data, xr.DataTree) or isinstance(self.data, xr.DataArray):
            return self.data.attrs.get(self.attrs_key, [])
        elif isinstance(self.data, str):
            # group name
            parent_item: AbstractTreeItem = self.parent()
            annotations = parent_item.data.attrs.get(self.attrs_key, [])
            return [annotation for annotation in annotations if annotation.get('group', None) == self.data]
        elif isinstance(self.data, dict):
            # annotation dict
            return [self.data]
        else:
            return []
    
    def _get_annotation_label(self, annotation: dict) -> str:
        """ Get the label for an annotation.
        """
        atype = annotation.get('type', None).lower()
        pos = annotation.get('position', None)
        dims = list(pos.keys()) if pos is not None else []
        data = list(pos.values()) if pos is not None else []
        text = annotation.get('text', '')
        if atype == 'vregion':
            label = text.strip(' ').split('\n')[0]
            if label == '':
                xdim = dims[0]
                xlim = data[0]
                label = f'{xdim}: ({xlim[0]: .2g}, {xlim[1]: .2g})'
        return label
    
    def _set_annotation_label(self, annotation: dict, label: str) -> str:
        """ Set the label for an annotation.
        """
        text = str(label).strip()
        lines = annotation.get('text', '').split('\n')
        if lines:
            lines[0] = text
            annotation['text'] = '\n'.join(lines)
        elif text:
            lines = [text]
            annotation['text'] = '\n'.join(lines)
        elif 'text' in annotation:
            del annotation['text']
    
    def __repr__(self):
        return str(self.name())
    
    def __str__(self) -> str:
        return self._tree_repr(lambda item: item.__repr__())
    
    def setParent(self, parent: AnnotationTreeItem | None) -> None:
        if isinstance(self.data, xr.DataTree) or isinstance(self.data, xr.DataArray):
            raise ValueError('The DataTree is not mutable, only the annotations and their groups.')
        
        oldParent: AnnotationTreeItem | None = self.parent()
        newParent: AnnotationTreeItem | None = parent

        if isinstance(self.data, str):
            if isinstance(newParent.data, str):
                raise ValueError('Groups cannot be nested.')
            elif isinstance(newParent.data, dict):
                raise ValueError('Groups contain annotations, not vice-versa.')
        elif isinstance(self.data, dict):
            if isinstance(newParent.data, dict):
                raise ValueError('Annotations cannot be nested.')
        
        # item tree
        super().setParent(newParent)
        
        # annotations in DataTree/DataArray
        if isinstance(self.data, str):
            # group
            oldObject = oldParent.data
            annotations = oldObject.attrs.get(self.attrs_key, [])
            annotations = [annotation for annotation in annotations if annotation.get('group', None) == self.data]
            for annotation in annotations:
                oldObject.attrs[self.attrs_key].remove(annotation)
            newObject = newParent.data
            for annotation in annotations:
                newObject.attrs[self.attrs_key].append(annotation)
        elif isinstance(self.data, dict):
            # annotation
            if isinstance(oldParent.data, str):
                oldObject = oldParent.parent().data
            else:
                oldObject = oldParent.data
            annotation = self.data
            oldObject.attrs[self.attrs_key].remove(annotation)
            if isinstance(newParent.data, str):
                newGroup = newParent.data   
                annotation['group'] = newGroup
                newObject = newParent.parent().data
            else:
                newObject = newParent.data
                if 'group' in annotation:
                    del annotation['group']
            newObject.attrs[self.attrs_key].append(annotation)
    
    def insertChild(self, index: int, child: AnnotationTreeItem) -> None:
        if isinstance(child.data, xr.DataTree) or isinstance(child.data, xr.DataArray):
            raise ValueError('The DataTree is not mutable, only the annotations and their groups.')
        
        if not (0 <= index <= len(self.children)):
            raise IndexError('Index out of range.')
        
        # append as last child
        child.setParent(self)
        
        # move item to index
        pos = self.children.index(child)
        if pos != index:
            if pos < index:
                index -= 1
            if pos != index:
                # reorder child items
                self.children.insert(index, self.children.pop(pos))
                # reorder annotations in DataTree/DataArray
                if isinstance(self.data, xr.DataTree) or isinstance(self.data, xr.DataArray):
                    obj = self.data
                elif isinstance(self.data, str):
                    obj = self.parent().data
                annotations_list = obj.attrs.get(self.attrs_key, [])
                for child_item in self.children:
                    annotations = child_item._get_annotations()
                    for annotation in annotations:
                        if annotation not in annotations_list:
                            continue
                        annotations_list.remove(annotation)
                        annotations_list.append(annotation)
