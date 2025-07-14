""" Tree model for metadata annotations in an Xarray DataTree.

Expects that DataTree/DataArray.attrs['annotations'] is a list of dictionaries, each representing an annotation.

Keys other than 'annotations' can be specified via the `attrs_key` parameter in the constructor.

Annotations can be grouped by a 'group' key in each annotation dictionary.

TODO:
- merge dropped groups if group with same name already exists
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import AnnotationTreeItem
from pyqt_ext.tree import AbstractTreeModel


class AnnotationTreeModel(AbstractTreeModel):
    
    def __init__(self, datatree: xr.DataTree = None, paths: list[str] = None, attrs_key: str = 'annotations', parent: QObject = None):
        AbstractTreeModel.__init__(self, parent=parent)

        # column labels
        self.setColumnLabels(['Annotations'])

        # set data tree
        self.setDataTree(datatree, paths=paths, attrs_key=attrs_key)
    
    def dataTree(self) -> xr.DataTree | None:
        return getattr(self, '_dataTree', None)
    
    def setDataTree(self, datatree: xr.DataTree | None, paths: list[str] = None, attrs_key: str = 'annotations') -> None:
        self._dataTree = datatree
        self._paths = paths
        self._key = attrs_key

        if datatree is None:
            root_item = AnnotationTreeItem(data=None, attrs_key=attrs_key)
            self.setRootItem(root_item)
            return
        
        root_item = AnnotationTreeItem(data=datatree, attrs_key=attrs_key)
        
        if paths is None:
            paths = []
            for node in datatree.subtree:
                paths.append(node.path)
                for var in node.data_vars:
                    paths.append('/'.join([node.path, var]))
                for coord in node.coords:
                    paths.append('/'.join([node.path, coord]))
        
        for path in paths:
            obj = datatree[path]
            annotations = obj.attrs.get(attrs_key, None)
            if annotations is None:
                continue
            
            if obj is datatree:
                obj_item = root_item
            else:
                # ensure path to obj_item exists
                item: AnnotationTreeItem = root_item
                path_parts = path.strip('/').split('/')
                for i, name in enumerate(path_parts[:-1]):
                    try:
                        child_names = [child.name() for child in item.children]
                        child_index = child_names.index(name)
                        item = item.children[child_index]
                    except Exception as error:
                        # create new tree item to ensure validity of path
                        subpath = '/' + '/'.join(path_parts[:i + 1])
                        subobj = datatree[subpath]
                        item = AnnotationTreeItem(data=subobj, parent=item, attrs_key=attrs_key)
                obj_item = AnnotationTreeItem(data=obj, parent=item, attrs_key=attrs_key)
            
            ungrouped_annotations = [annotation for annotation in annotations if not annotation.get('group', None)]
            for annotation in ungrouped_annotations:
                item = AnnotationTreeItem(data=annotation, parent=obj_item, attrs_key=attrs_key)
            
            groups = []
            for annotation in annotations:
                group = annotation.get('group', None)
                if group is None:
                    continue
                if group not in groups:
                    groups.append(group)
            
            for group in groups:
                group_item = AnnotationTreeItem(data=group, parent=obj_item, attrs_key=attrs_key)
                group_annotations = [annotation for annotation in annotations if annotation.get('group', None) == group]
                for annotation in group_annotations:
                    AnnotationTreeItem(data=annotation, parent=group_item, attrs_key=attrs_key)
        
        # set item tree
        self.setRootItem(root_item)
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        
        if index.column() != 0:
            return Qt.ItemFlag.NoItemFlags
        
        item: AnnotationTreeItem = self.itemFromIndex(index)
        data = getattr(item, 'data', None)
        if isinstance(data, xr.DataTree): # node
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        elif isinstance(data, xr.DataArray): # variable or coordinate
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        elif isinstance(data, str): # annotation group
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        elif isinstance(data, dict): # annotation
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        else:
            return Qt.ItemFlag.NoItemFlags
        
        # drag and drop
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            if isinstance(data, xr.DataTree) or isinstance(data, xr.DataArray):
                # can only drop onto DataTree/DataArray items
                flags |= Qt.ItemFlag.ItemIsDropEnabled
            elif isinstance(data, str) or isinstance(data, dict): # annotation group or annotation
                # can drag and drop annotation items or groups
                flags |= (Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                return item.name()
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                data = getattr(item, 'data', None)
                if isinstance(data, xr.DataTree): # node
                    return qta.icon('ph.folder-thin')
                if isinstance(data, xr.DataArray): # variable or coordinate
                    node = item.parent().data
                    if data.name in list(node.data_vars): # variable
                        return qta.icon('ph.cube-thin')
                    if data.name in list(node.coords): # coordinate
                        return qta.icon('ph.list-numbers-thin')
                if isinstance(data, str): # annotation group
                    return qta.icon('mdi.group')
                if isinstance(data, dict): # annotation
                    atype = data.get('type', '').lower()
                    if atype == 'vregion':
                        return qta.icon('mdi.arrow-expand-horizontal')
                    else:
                        return qta.icon('mdi.tag-multiple')

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                data = getattr(item, 'data', None)
                if isinstance(data, str):
                    # annotation group
                    group = str(value).strip()
                    if not group:
                        return False
                    if group == item.name():
                        # no change
                        return False
                    obj_item: AnnotationTreeItem = item.parent()
                    groups = [child_item.name() for child_item in obj_item.children if isinstance(getattr(child_item, 'data', None), str)]
                    if group in groups:
                        # group already exists
                        focus_widget: QWidget = QApplication.focusWidget()
                        QMessageBox.warning(focus_widget, 'Group already exists', f'Group "{group}" already exists.')
                        return False
                    # update group name
                    item.setName(group)
                    return True
                if isinstance(data, dict):
                    # annotation
                    item._set_annotation_label(data, value)
                    return True
        return False
  

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
    model = AnnotationTreeModel(datatree=dt)#, paths=['child1', 'child2'])
    print(model.rootItem())

    app = QApplication()
    view = QTreeView()
    view.setModel(model)
    view.show()
    app.exec()

    print(model.rootItem())
    # print(dt)
    print(dt.attrs['annotations'])
    print(dt['child1'].attrs['annotations'])


if __name__ == '__main__':
    test_model()