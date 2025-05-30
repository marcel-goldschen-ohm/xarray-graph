""" Tree model for metadata annotations in an Xarray DataTree.
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from pyqt_ext.tree import AbstractTreeItem, AbstractTreeModel


class AnnotationTreeModel(AbstractTreeModel):
    
    def __init__(self, dt: xr.DataTree = None, paths: list[str] = None, key: str = 'annotations', parent: QObject = None):
        AbstractTreeModel.__init__(self, parent=parent)

        # column labels
        self.setColumnLabels(['Annotations'])

        # set data tree
        self.setDataTree(dt, paths=paths, key=key)
    
    def dataTree(self) -> xr.DataTree | None:
        return getattr(self, '_dataTree', None)
    
    def setDataTree(self, dt: xr.DataTree | None, paths: list[str] = None, key: str = 'annotations') -> None:
        self._dataTree = dt
        self._paths = paths
        self._key = key

        if dt is None:
            root_item = AbstractTreeItem()
            self.setRoot(root_item)
            root_item._data = None
            return
        root_item: AbstractTreeItem = AbstractTreeItem(name=dt.name, parent=None)
        root_item._data = dt
        
        if paths is None:
            paths = []
            for node in dt.subtree:
                paths.append(node.path)
                for var in node.data_vars:
                    paths.append('/'.join([node.path, var]))
                for coord in node.coords:
                    paths.append('/'.join([node.path, coord]))
        
        for path in paths:
            obj = dt[path]
            annotations = obj.attrs.get(key, [])
            if annotations:
                parent_item: AbstractTreeItem = self._ensureItemAtPath(path, root_item)
                parent_item._data = obj
                ungrouped_annotations = [annotation for annotation in annotations if not annotation.get('group', None)]
                for annotation in ungrouped_annotations:
                    label = self._get_annotation_label(annotation)
                    item = AbstractTreeItem(name=label, parent=parent_item)
                    item._data = annotation
                groups = []
                for annotation in annotations:
                    group = annotation.get('group', None)
                    if group is None:
                        continue
                    if group not in groups:
                        groups.append(group)
                for group in groups:
                    group_item: AbstractTreeItem = self._ensureItemAtPath('/'.join([path, group]), root_item)
                    group_item._data = group
                    group_annotations = [annotation for annotation in annotations if annotation.get('group', None) == group]
                    for annotation in group_annotations:
                        label = self._get_annotation_label(annotation)
                        item = AbstractTreeItem(name=label, parent=group_item)
                        item._data = annotation
        
        # set item tree
        self.setRoot(root_item)
    
    def _ensureItemAtPath(self, path: str, root_item: AbstractTreeItem = None) -> AbstractTreeItem:
        """ Ensure that the path exists in the model.
        """
        if root_item is None:
            root_item = self.root()
        if path == '/':
            return root_item
        item = root_item
        parts = path.strip('/').split('/')
        for part in parts:
            child_items = item.children
            child_names = [child.name for child in child_items]
            try:
                i = child_names.index(part)
                item = child_items[i]
            except ValueError:
                # create new item
                item = AbstractTreeItem(name=part, parent=item)
                item._data = None
        return item
    
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
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        
        if index.column() == 0:
            item: AbstractTreeItem = self.itemFromIndex(index)
            data = getattr(item, '_data', None)
            if isinstance(data, xr.DataTree): # node
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            elif isinstance(data, xr.DataArray): # variable or coordinate
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            elif isinstance(data, str): # annotation group
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
            elif isinstance(data, dict): # annotation
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        
        # drag and drop
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            if isinstance(data, str) or isinstance(data, dict): # annotation group or annotation
                # can only drag and drop annotation items or annotation group items
                flags |= (Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            item: AbstractTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                return item.name
        if role == Qt.ItemDataRole.DecorationRole:
            item: AbstractTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                data = getattr(item, '_data', None)
                if isinstance(data, xr.DataTree): # node
                    return qta.icon('ph.folder-thin')
                if isinstance(data, xr.DataArray): # variable or coordinate
                    node = item.parent._data
                    if data.name in list(node.data_vars): # variable
                        return qta.icon('ph.cube-thin')
                    if data.name in list(node.coords): # coordinate
                        return qta.icon('ph.list-numbers-thin')
                if isinstance(data, str): # annotation group
                    return qta.icon('mdi.group')
                if isinstance(data, dict): # annotation
                    atype = data.get('type', None).lower()
                    if atype == 'vregion':
                        return qta.icon('mdi.arrow-expand-horizontal')
                    else:
                        return qta.icon('mdi.tag-multiple')

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if role == Qt.ItemDataRole.EditRole:
            item: AbstractTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                data = getattr(item, '_data', None)
                if isinstance(data, str): # annotation group
                    group = str(value).strip()
                    if not group:
                        return False
                    if group == item.name:
                        # no change
                        return False
                    parent_item: AbstractTreeItem = item.parent
                    groups = [child_item.name for child_item in parent_item.children if isinstance(getattr(child_item, '_data', None), str)]
                    if group in groups:
                        # group already exists
                        QMessageBox.warning(None, 'Group already exists', f'Group "{group}" already exists.')
                        return False
                    # update group name
                    item.name = group
                    for annotation_item in item.children:
                        annotation = getattr(annotation_item, '_data', None)
                        if annotation is not None:
                            # update annotation group
                            annotation['group'] = group
                    return True
                if isinstance(data, dict): # annotation
                    item: AbstractTreeItem = self.itemFromIndex(index)
                    annotation = getattr(item, '_data', None)
                    if annotation is not None:
                        # update annotation label
                        text = str(value).strip()
                        lines = annotation.get('text', '').split('\n')
                        if lines:
                            lines[0] = text
                            annotation['text'] = '\n'.join(lines)
                        elif text:
                            lines = [text]
                            annotation['text'] = '\n'.join(lines)
                        elif 'text' in annotation:
                            del annotation['text']
                        item.name = self._get_annotation_label(annotation)
                        return True
        return False
    
    def removeItem(self, item: AbstractTreeItem) -> bool:
        """ Remove the item from the model.
        """
        data = getattr(item, '_data', None)
        if isinstance(data, str): # annotation group
            obj = item.parent._data
            annotations = obj.attrs.get(self._key, [])
            obj.attrs[self._key] = [annotation for annotation in annotations if annotation.get('group', None) != data]
        elif isinstance(data, dict): # annotation
            obj = item.parent._data
            if isinstance(obj, str):
                obj = item.parent.parent._data
            annotations = obj.attrs.get(self._key, [])
            annotations.remove(data)
        else:
            return False
        return AbstractTreeModel.removeItem(self, item)
    
    # def moveRow(self, src_parent_index: QModelIndex, src_row: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
    #     # TODO: update for moving annotations
    #     dt: DataTree = self.dataTree()
    #     if dt is None:
    #         return False
    #     src_parent_item: AbstractTreeItem = self.itemFromIndex(src_parent_index)
    #     src_item: AbstractTreeItem = src_parent_item.children[src_row]
    #     src_path: str = self.pathFromItem(src_item)
    #     dst_parent_path: str = self.pathFromIndex(dst_parent_index)
        
    #     dst_parent_dtype: str | None = self.dataTypeAtPath(dst_parent_path)
    #     if dst_parent_dtype != 'node':
    #         raise ValueError('Destination parent must be a node.')
        
    #     src_node: xr.DataTree = dt[src_path]
    #     dst_parent_node: xr.DataTree = dt[dst_parent_path]

    #     if src_parent_index != dst_parent_index:
    #         # If we are not rearranging children within the same parent node,
    #         # ensure there is not a name conflict.
    #         if src_item.name in (list(dst_parent_node.children) + list(dst_parent_node.dataset.data_vars) + list(dst_parent_node.dataset.coords)):
    #             raise ValueError('Name already exists in destination parent.')
        
    #     # move item
    #     success: bool = AbstractTreeModel.moveRow(self, src_parent_index, src_row, dst_parent_index, dst_row)
    #     if success:
    #         # move data
    #         src_node.orphan()
    #         src_node.parent = dst_parent_node
    #     return success
    

class AnnotationDndTreeModel(AnnotationTreeModel):

    def __init__(self, dt: xr.DataTree = None, parent: QObject = None):
        AnnotationTreeModel.__init__(self, dt=dt, parent=parent)
    
    def supportedDropActions(self) -> Qt.DropAction.ActionMask:
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction


def test_model():
    print('\nDataTree...')
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.DataTree()
    dt['child3/grandchild2'] = xr.DataTree()
    

    dt.attrs['annotations'] = [
        {'type': 'vregion', 'position': {'lat': [0, 1]}},
        {'type': 'vregion', 'position': {'lat': [2, 3]}, 'group': 'group2', 'text': '10 mM GABA\n1 mM PTX'},
    ]
    dt['child1'].attrs['annotations'] = [
        {'type': 'vregion', 'position': {'lat': [0, 1]}, 'group': 'group1'},
        {'type': 'vregion', 'position': {'lat': [2, 3]}, 'group': 'group1'},
        {'type': 'vregion', 'position': {'lat': [2, 3]}, 'group': 'group2'},
    ]
    print(dt)

    print('\nAnnotationTreeModel...')
    model = AnnotationTreeModel(dt=dt)#, paths=['child1', 'child2'])
    print(model.root())

    app = QApplication()
    view = QTreeView()
    view.setModel(model)
    view.show()
    app.exec()


if __name__ == '__main__':
    test_model()