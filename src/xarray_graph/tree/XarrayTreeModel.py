""" Tree model that uses XarrayTreeItem for its data interface.
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from pyqt_ext.tree import AbstractTreeItem, AbstractTreeModel


class XarrayTreeModel(AbstractTreeModel):
    
    def __init__(self, dt: xr.DataTree = None, parent: QObject = None):
        AbstractTreeModel.__init__(self, parent=parent)

        # optional details column
        self._isDetailsColumnVisible = True

        # column labels
        self.setColumnLabels(['DataTree', 'Details'])

        # set data tree
        self.setDataTree(dt)
    
    def dataTree(self) -> xr.DataTree | None:
        return getattr(self, '_dataTree', None)
    
    def setDataTree(self, dt: xr.DataTree | None, include_vars: bool = True, include_coords: bool = True) -> None:
        self._dataTree = dt
        if dt is None:
            root_item = AbstractTreeItem()
            self.setRoot(root_item)
            return
        root_item: AbstractTreeItem = AbstractTreeItem(name=dt.name, parent=None)
        for node in dt.subtree:
            if node is not dt:
                # node item
                parent_item: AbstractTreeItem = self.itemFromPath(node.parent.path, root=root_item)
                AbstractTreeItem(name=node.name, parent=parent_item)
            if include_vars:
                for key in list(node.ds.data_vars):
                    # var item
                    parent_item: AbstractTreeItem = self.itemFromPath(node.path, root=root_item)
                    AbstractTreeItem(name=key, parent=parent_item)
            if include_coords:
                for key in list(node.ds.coords):
                    # coord item
                    parent_item: AbstractTreeItem = self.itemFromPath(node.path, root=root_item)
                    AbstractTreeItem(name=key, parent=parent_item)
        # set item tree
        self.setRoot(root_item)
    
    def dataTypeAtPath(self, path: str) -> str | None:
        """ Get the data type associated with path.
        """
        dt: xr.DataTree | None = self.dataTree()
        if dt is None:
            return
        obj: xr.DataTree | xr.DataArray | None = dt[path]
        if isinstance(obj, xr.DataTree):
            return 'node'
        if isinstance(obj, xr.DataArray):
            parent_path = '/'.join(path.rstrip('/').split('/')[:-1])
            node: xr.DataTree = dt[parent_path]
            if node is not None:
                if obj.name in list(node.dataset.data_vars):
                    return 'var'
                if obj.name in list(node.dataset.coords):
                    return 'coord'
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if self.isDetailsColumnVisible():
            return 2
        return 1

    def isDetailsColumnVisible(self) -> bool:
        return self._isDetailsColumnVisible
    
    def setDetailsColumnVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._isDetailsColumnVisible = visible
        self.endResetModel()
    
    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        path: str = self.pathFromIndex(index)
        data_type: str | None = self.dataTypeAtPath(path)
        if index.column() == 0:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        elif index.column() == 1:
            # cannot edit details column
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        # drag and drop
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            if data_type == 'node':
                # can only drag and drop node items
                flags |= (Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        dt: xr.DataTree | None = self.dataTree()
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            item: AbstractTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                return item.name
            elif index.column() == 1:
                path: str = self.pathFromIndex(index)
                data_type: str | None = self.dataTypeAtPath(path)
                if data_type == 'node':
                    node: xr.DataTree = dt[path]
                    sizes = node.dataset.sizes
                    return '(' + ', '.join([f'{dim}: {size}' for dim, size in sizes.items()]) + ')'
                if data_type == 'var':
                    node: xr.DataTree = dt[self.pathFromItem(item.parent)]
                    rep = str(node.dataset)
                    i = rep.find('Data variables:')
                    i = rep.find(item.name, i)  # find var
                    i = rep.find(') ', i) + 2  # skip dimensions
                    i = rep.find(' ', i) + 1  # skip dtype
                    i = rep.find(' ', i) + 1  # skip bytes
                    j = rep.find('\n', i)
                    return rep[i:j] if j > 0 else rep[i:]
                if data_type == 'coord':
                    node: xr.DataTree = dt[self.pathFromItem(item.parent)]
                    rep = str(node.dataset)
                    i = rep.find('Coordinates:')
                    i = rep.find(item.name, i)  # find coord
                    i = rep.find(') ', i) + 2  # skip dimensions
                    i = rep.find(' ', i) + 1  # skip dtype
                    i = rep.find(' ', i) + 1  # skip bytes
                    j = rep.find('\n', i)
                    return rep[i:j] if j > 0 else rep[i:]
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                path: str = self.pathFromIndex(index)
                data_type: str | None = self.dataTypeAtPath(path)
                if data_type == 'node':
                    return qta.icon('ph.folder-thin')
                if data_type == 'var':
                    return qta.icon('ph.cube-thin')
                if data_type == 'coord':
                    return qta.icon('ph.list-numbers-thin')

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AbstractTreeItem = self.itemFromIndex(index)
                old_name: str = item.name
                new_name: str = value
                if new_name == old_name:
                    return False
                sibling_names = [child.name for child in item.parent.children]
                if new_name in sibling_names:
                    QMessageBox.warning(None, 'Name already exists', f'Name "{new_name}" already exists in parent node.')
                    return False
                path: str = self.pathFromIndex(index)
                data_type: str | None = self.dataTypeAtPath(path)
                dt: xr.DataTree | None = self.dataTree()
                if dt is None:
                    return False
                if data_type == 'node':
                    # rename node
                    node: xr.DataTree = dt[path]
                    parent_node: xr.DataTree = node.parent
                    node.orphan()
                    node.name = new_name
                    node.parent = parent_node
                    item.name = new_name
                    return True
                elif data_type in ['var', 'coord']:
                    # rename array
                    node: xr.DataTree = dt[self.pathFromItem(item.parent)]
                    node.dataset = node.to_dataset().rename_vars({old_name: new_name})
                    item.name = new_name
                    return True
        return False
    
    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        """ Remove rows from the model and data tree.

        If you don't want to affect the data tree, use AbstractTreeModel.removeRows(self, ...) instead.
        """
        # get items/paths to remove
        paths_to_remove = [self.pathFromIndex(self.index(row + i, 0, parent_index)) for i in range(count)]
        # remove items
        success: bool = AbstractTreeModel.removeRows(self, row, count, parent_index)
        if success:
            # remove data
            dt: xr.DataTree = self.dataTree()
            if dt is not None:
                for path in paths_to_remove:
                    obj: xr.DataTree | xr.DataArray = dt[path]
                    if isinstance(obj, xr.DataTree):
                        obj.orphan()
                    elif isinstance(obj, xr.DataArray):
                        obj_name = path.rstrip('/').split('/')[-1]
                        parent_path = '/'.join(path.rstrip('/').split('/')[:-1])
                        node: xr.DataTree = dt[parent_path]
                        node.dataset = node.to_dataset().drop_vars(obj_name)
        return success
    
    def moveRow(self, src_parent_index: QModelIndex, src_row: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        dt: xr.DataTree = self.dataTree()
        if dt is None:
            return False
        src_parent_item: AbstractTreeItem = self.itemFromIndex(src_parent_index)
        src_item: AbstractTreeItem = src_parent_item.children[src_row]
        src_path: str = self.pathFromItem(src_item)
        dst_parent_path: str = self.pathFromIndex(dst_parent_index)
        
        dst_parent_dtype: str | None = self.dataTypeAtPath(dst_parent_path)
        if dst_parent_dtype != 'node':
            raise ValueError('Destination parent must be a node.')
        
        src_node: xr.DataTree = dt[src_path]
        dst_parent_node: xr.DataTree = dt[dst_parent_path]

        if src_parent_index != dst_parent_index:
            # If we are not rearranging children within the same parent node,
            # ensure there is not a name conflict.
            if src_item.name in (list(dst_parent_node.children) + list(dst_parent_node.dataset.data_vars) + list(dst_parent_node.dataset.coords)):
                raise ValueError('Name already exists in destination parent.')
        
        # move item
        success: bool = AbstractTreeModel.moveRow(self, src_parent_index, src_row, dst_parent_index, dst_row)
        if success:
            # move data
            src_node.orphan()
            src_node.parent = dst_parent_node
        return success
    
    # def assignNode(self, node: DataTree, path: str):
    #     """ Assign node at path.
    #     """
    #     # TODO
    #     pass
    
    # def assignVar(self, var: xr.DataArray, path: str):
    #     """ Assign variable at path.
    #     """
    #     # TODO
    #     pass
    
    # def assignCoord(self, coord: xr.DataArray, path: str):
    #     """ Assign coordinate at path.
    #     """
    #     # TODO
    #     pass
    

class XarrayDndTreeModel(XarrayTreeModel):

    def __init__(self, dt: xr.DataTree = None, parent: QObject = None):
        XarrayTreeModel.__init__(self, dt=dt, parent=parent)
    
    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction


def test_model():
    print('\nDataTree...')
    dt = xr.DataTree(name='root')
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.DataTree()
    dt['child3/grandchild2'] = xr.DataTree()
    print(dt)

    print('\nXarrayTreeModel...')
    model = XarrayTreeModel(dt=dt)
    print(model.root())

    app = QApplication()
    view = QTreeView()
    view.setModel(model)
    view.show()
    app.exec()


if __name__ == '__main__':
    test_model()