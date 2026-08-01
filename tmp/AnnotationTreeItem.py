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
    
    def isXarrayObject(self) -> bool:
        """ Check if the item is an Xarray DataTree or DataArray.
        """
        return isinstance(self.data, xr.DataTree) or isinstance(self.data, xr.DataArray)
    
    def isAnnotationGroup(self) -> bool:
        """ Check if the item is an annotation group (a string).
        """
        return isinstance(self.data, str)
    
    def isAnnotationDict(self) -> bool:
        """ Check if the item is an annotation (a dictionary).
        """
        return isinstance(self.data, dict)
    
    def xarrayObject(self) -> xr.DataTree | xr.DataArray:
        """ Get the Xarray DataTree or DataArray associated with this item.
        """
        if self.isXarrayObject():
            return self.data
        elif self.isAnnotationGroup() or self.isAnnotationDict():
            parentItem: AnnotationTreeItem = self.parent()
            if parentItem is not None:
                return parentItem.xarrayObject()
    
    def annotationsList(self) -> list[dict]:
        """ Get the list of annotations associated with this item.
        """
        xrobject: xr.DataTree | xr.DataArray = self.xarrayObject()
        if xrobject is None:
            return
        return xrobject.attrs.get(self.attrs_key, None)
    
    def annotations(self) -> list[dict]:
        """ Get the annotations associated with this item.
        """
        if self.isXarrayObject():
            return self.annotationsList()
        elif self.isAnnotationGroup():
            annotationsList = self.annotationsList()
            group = self.data
            return [annotation for annotation in annotationsList if annotation.get('group', None) == group]
        elif self.isAnnotationDict():
            return [self.data]
    
    def name(self) -> str:
        if self.isXarrayObject():
            return self.data.name
        elif self.isAnnotationGroup():
            return self.data
        elif self.isAnnotationDict():
            return self.annotationLabel(self.data)
    
    def setName(self, name: str) -> None:
        if self.isAnnotationGroup():
            group = str(name).strip()
            if not group:
                return
            if group == self.data:
                # no change
                return
            annotationsList = self.annotationsList()
            groups = [annotation['group'] for annotation in annotationsList if annotation.get('group', None)]
            if group in groups:
                # group already exists
                focused_widget: QWidget = QApplication.focusWidget()
                QMessageBox.warning(focused_widget, 'Group already exists', f'Group "{group}" already exists.')
                return
            # update group name
            for annotation in annotationsList:
                if annotation.get('group', None) == self.data:
                    annotation['group'] = group
            self.data = group
        
        elif self.isAnnotationDict():
            self.setAnnotationLabel(self.data, name)
    
    @staticmethod
    def annotationLabel(annotation: dict) -> str:
        """ Get the label for an annotation.
        """
        atype = annotation.get('type', '').lower()
        pos = annotation.get('position', None)
        dims = list(pos.keys()) if pos is not None else []
        data = list(pos.values()) if pos is not None else []
        text = annotation.get('text', '')
        label = text.strip(' ').split('\n')[0]
        if atype == 'vregion':
            if label == '':
                xdim = dims[0]
                xlim = data[0]
                lb = f'{xlim[0]: .3g}'.strip()
                ub = f'{xlim[1]: .3g}'.strip()
                label = f'{xdim}: ({lb}, {ub})'
        return label
    
    # @staticmethod
    # def setAnnotationLabel(annotation: dict, label: str) -> None:
    #     """ Set the label for an annotation.
    #     """
    #     text = str(label).strip()
    #     lines = annotation.get('text', '').split('\n')
    #     if lines:
    #         lines[0] = text
    #         annotation['text'] = '\n'.join(lines)
    #     elif text:
    #         annotation['text'] = text
    #     elif 'text' in annotation:
    #         del annotation['text']
    
    def __repr__(self):
        return str(self.name())
    
    def __str__(self) -> str:
        return self._tree_repr(lambda item: item.__repr__())
    
    def setParent(self, parent: AnnotationTreeItem | None) -> None:
        if self.isXarrayObject():
            raise ValueError('The DataTree is not mutable, only the annotations and their groups.')
        
        oldParent: AnnotationTreeItem | None = self.parent()
        newParent: AnnotationTreeItem | None = parent
        if oldParent is newParent:
            # nothing to do
            return
        if (newParent is not None) and newParent.hasAncestor(self):
            raise ValueError('Cannot set parent to a descendant.')
        if self.isAnnotationGroup():
            if newParent.isAnnotationGroup():
                raise ValueError('Groups cannot be nested.')
            elif newParent.isAnnotationDict():
                raise ValueError('Groups contain annotations, not vice-versa.')
        elif self.isAnnotationDict():
            if (newParent is not None) and newParent.isAnnotationDict():
                raise ValueError('Annotations cannot be nested.')
        
        annotations = self.annotations()

        if oldParent is not None:
            # detach from old parent
            oldAnnotationsList = self.annotationsList()
            if self in oldParent.children:
                oldParent.children.remove(self)
            self._parent = None
            for annotation in annotations:
                if annotation in oldAnnotationsList:
                    oldAnnotationsList.remove(annotation)
        
        if newParent is not None:
            newAnnotationsList = newParent.annotationsList()
            if newParent.isAnnotationGroup():
                newGroup = newParent.data
                for annotation in annotations:
                    annotation['group'] = newGroup
            # attach to new parent (appends as last child)
            if self not in newParent.children:
                newParent.children.append(self)
            self._parent = newParent
            for annotation in annotations:
                if annotation not in newAnnotationsList:
                    newAnnotationsList.append(annotation)
    
    def insertChild(self, index: int, child: AnnotationTreeItem) -> None:
        if child.isXarrayObject():
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
                annotationsList = self.annotationsList()
                child: AnnotationTreeItem
                for child in self.children:
                    annotations = child.annotations()
                    for annotation in annotations:
                        if annotation in annotationsList:
                            annotationsList.remove(annotation)
                        annotationsList.append(annotation)
