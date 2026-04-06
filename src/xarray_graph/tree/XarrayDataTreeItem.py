""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- moveRows: merge items?
- should we ask before removing inherited coords in descendents when moving a coord?
- enforce coord order at all times? note: this currently happens when refreshing the tree, but not otherwise.
"""

from __future__ import annotations
from collections.abc import Iterator
from enum import Enum
from copy import copy, deepcopy
import xarray as xr
# from qtpy.QtCore import *
# from qtpy.QtGui import *
# from qtpy.QtWidgets import *
# import qtawesome as qta
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import AbstractTreeItem#, AbstractTreeModel
import cmap


class XarrayDataTreeType(Enum):
    NODE = 1
    DATA_VAR = 2
    COORD = 3

# for convenience in this file
NODE, DATA_VAR, COORD = list(XarrayDataTreeType)


class XarrayDataTreeItem(AbstractTreeItem):
    """ Tree item wrapper for xarray nodes and variables in XarrayDataTreeModel.

    This isn't strictly necessary, but it speeds object access and thus tree UI performance as compared to using paths to access the underlying datatree objects, and it also provides a consistent interface to all tree models using AbstractTreeItem to interface with their data.
    """

    def __init__(self, data: xr.DataTree | xr.DataArray, data_type: XarrayDataTreeType = None, parent: XarrayDataTreeItem = None, sibling_index: int = None):
        self.data: xr.DataTree | xr.DataArray = data
        super().__init__(parent, sibling_index)
        self._data_type: XarrayDataTreeType = XarrayDataTreeItem.autodetectDataType(self) or data_type
    
    @staticmethod
    def autodetectDataType(item: XarrayDataTreeItem) -> XarrayDataTreeType | None:
        if isinstance(item.data, xr.DataTree):
            return NODE
        elif isinstance(item.data, xr.DataArray):
            var: xr.DataArray = item.data
            parent_item: XarrayDataTreeItem = item.parent
            if parent_item is not None:
                parent_node: xr.DataTree = parent_item.data
                if var.name in parent_node.data_vars:
                    return DATA_VAR
                elif var.name in parent_node.coords:
                    return COORD
    
    def isNode(self) -> bool:
        return isinstance(self.data, xr.DataTree)
    
    def isVariable(self) -> bool:
        return isinstance(self.data, xr.DataArray)
    
    def isDataVar(self) -> bool:
        if not isinstance(self.data, xr.DataArray):
            return False
        var: xr.DataArray = self.data
        parent_item: XarrayDataTreeItem = self.parent
        if parent_item is not None:
            parent_node: xr.DataTree = parent_item.data
            if var.name in parent_node.data_vars:
                return True
        return self._data_type == DATA_VAR
    
    def isCoord(self) -> bool:
        if not isinstance(self.data, xr.DataArray):
            return False
        var: xr.DataArray = self.data
        parent_item: XarrayDataTreeItem = self.parent
        if parent_item is not None:
            parent_node: xr.DataTree = parent_item.data
            if var.name in parent_node.coords:
                return True
        return self._data_type == COORD
    
    def isIndexCoord(self) -> bool:
        if not isinstance(self.data, xr.DataArray):
            return False
        var: xr.DataArray = self.data
        parent_item: XarrayDataTreeItem = self.parent
        if parent_item is not None:
            parent_node: xr.DataTree = parent_item.data
            if var.name in parent_node.xindexes:
                return True
        return False
    
    def isInheritedCoord(self) -> bool:
        if not isinstance(self.data, xr.DataArray):
            return False
        var: xr.DataArray = self.data
        parent_item: XarrayDataTreeItem = self.parent
        if parent_item is not None:
            parent_node: xr.DataTree = parent_item.data
            if var.name in parent_node._inherited_coords_set():
                return True
        return False
    
    def updateSubtree(self, include_data_vars: bool = True, include_coords: bool = True, include_inherited_coords: bool = True, data_type_order: tuple[XarrayDataTreeType] = (COORD, DATA_VAR, NODE)) -> None:
        self.children = []
        if not self.isNode():
            return
        node: xr.DataTree = self.data
        for data_type in data_type_order:
            if data_type == COORD:
                if include_coords:
                    for coord in xarray_utils.ordered_coords_iter(node, include_inherited_coords):
                        child = XarrayDataTreeItem(coord, COORD, parent=self)
            elif data_type == DATA_VAR:
                if include_data_vars:
                    for var in node.data_vars.values():
                        child = XarrayDataTreeItem(var, DATA_VAR, parent=self)
            elif data_type == NODE:
                for child in node.children.values():
                    child = XarrayDataTreeItem(child, NODE, parent=self)
                    child.updateSubtree(include_data_vars, include_coords, include_inherited_coords, data_type_order)
    
    def name(self) -> str:
        name = self.data.name
        if not name and self.parent is None:
            return '/'
        return name
    
    def setName(self, name: str) -> None:
        # TODO: check for name conflict
        old_name = self.data.name
        if name == old_name:
            return
        parent_item: XarrayDataTreeItem = self.parent
        if parent_item is None:
            self.data.name = name
            return
        parent_node: xr.DataTree = parent_item.data
        if self.isNode() or self.isDataVar():
            parent_node[name] = self.data
            del parent_node[old_name]
        elif self.isCoord():
            parent_node.dataset = parent_node.to_dataset().assign_coords({name: self.data}).drop_vars(old_name)
    
    def orphan(self) -> None:
        if not self.parent:
            return
        
        # Update datatree
        if self.isNode():
            node: xr.DataTree = self.data
            inherited_index_coords = {name: node.coords[name] for name in node._inherited_coords_set() if name in node.xindexes}
            node.orphan()
            if inherited_index_coords:
                node.dataset = node.to_dataset().assign_coords(inherited_index_coords)
        else:
            var: xr.DataArray = self.data
            parent_item: XarrayDataTreeItem = self.parent
            parent_node: xr.DataTree = parent_item.data
            # store data type as otherwise it may be indeterminate after orphaning
            data_type = XarrayDataTreeItem.autodetectDataType(self)
            if data_type is not None:
                self._data_type = data_type
            # Remove data from parent node
            parent_node.dataset = parent_node.to_dataset().drop_vars(var.name)
        
        # Update item linkage
        self.parent.children.remove(self)
        self.parent = None
    
    def insertChild(self, index: int, child_item: XarrayDataTreeItem) -> None:
        # TODO: check for name conflict
        # TODO: check for alignment?
        # TODO: handle inherited coord?
        if not self.isNode():
            raise TypeError('Cannot insert child into non-node item')
        
        # Update datatree
        node: xr.DataTree = self.data
        if child_item.isNode():
            child_node: xr.DataTree = child_item.data
            # !! Insert child using root[path/to/child] to ensure inherited coords are properly updated in the tree. If you insert using node[child], then inheritance won't be updated!?
            dt: xr.DataTree = node.root
            parent_node_path: str = node.path.rstrip('/')
            child_node_path: str = parent_node_path + f'/{child_node.name}'
            dt[child_node_path] = child_node
            # update child item's data ref
            child_item.data = dt[child_node_path]
        else:
            child_var: xr.DataArray = child_item.data
            if child_item.isCoord():
                node.dataset = node.to_dataset().assign_coords({child_var.name: child_var})
            else:
                # assume child is a data_var
                node[child_var.name] = child_var
            # update child item's data ref
            child_item.data = node[child_var.name]
        
        # Update item linkage
        self.children.insert(index, child_item)
        child_item.parent = self

        # update data refs in child item's subtree
        item: XarrayDataTreeItem
        for item in child_item.subtree_depth_first():
            if item is child_item:
                continue
            item.data = dt[item.path()]
    
    def copy(self, deep: bool = True) -> XarrayDataTreeItem:
        """ Returns an orphaned copy of this item.
        """
        if self.isNode():
            data = self.data.copy(inherit=True, deep=deep)
        else:
            data = self.data.copy(deep=deep)
        
        item_copy = XarrayDataTreeItem(data, self._data_type)
        item_copy.updateSubtree()
        return item_copy
    
    def data_path(self) -> str:
        if self.isNode():
            node: xr.DataTree = self.data
            return node.path
        var: xr.DataArray = self.data
        parent_item: XarrayDataTreeItem = self.parent
        parent_node: xr.DataTree = parent_item.data
        return parent_node.path.rstrip('/') + f'/{var.name}'
    
    def sanityCheck(self) -> None:
        root_item: XarrayDataTreeItem = self.root()
        root_data: xr.DataTree | xr.DataArray = root_item.data

        if isinstance(root_data, xr.DataArray):
            da: xr.DataArray = root_data

            assert root_item.data.identical(da), \
                f'Sanity check failed: item data does not match DataArray for item {item.name()}'
        
        elif isinstance(root_data, xr.DataTree):
            dt: xr.DataTree = root_data
            
            # sanity check that all items in the tree have data that matches the datatree node/variable at their path
            item: XarrayDataTreeItem
            for item in root_item.subtree_depth_first():
                tree_data = dt[item.path()]
                if item.isNode():
                    assert item.data is tree_data, \
                        f'Sanity check failed: item data does not match DataTree node at path {item.path()}'
                elif item.isVariable():
                    assert item.data.identical(tree_data), \
                        f'Sanity check failed: item data does not match DataTree variable at path {item.path()}'
            
            # sanity check that all nodes/variables in the datatree have a corresponding item with matching data
            for node in dt.subtree:
                assert root_item[node.path] is not None, \
                    f'Sanity check failed: no item for node at path {node.path}'
                for name in node.data_vars:
                    assert root_item[node.path + '/' + name] is not None, \
                        f'Sanity check failed: no item for data_var {name} at path {node.path + "/" + name}'
                for name in node.coords:
                    assert root_item[node.path + '/' + name] is not None, \
                        f'Sanity check failed: no item for coord {name} at path {node.path + "/" + name}'

        print('Sanity check passed')


def test_tree():
    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child/grandchild/greatgrandchild'] = xr.DataTree()
    dt['child/grandchild/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['child/grandchild/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    # print(dt)

    root = XarrayDataTreeItem(dt)
    root.updateSubtree()
    # print('-'*82)
    # print('-'*82)
    # root.sanityCheck()
    # return

    print('-'*82)
    print('-'*82)
    print(root)
    print(dt)
    root.sanityCheck()
    # return

    print('-'*82)
    print('orphan child/grandchild/rasm')
    print('-'*82)
    rasm = root['child/grandchild/rasm']
    rasm.orphan()
    print(root)
    print(rasm)
    print(dt)
    root.sanityCheck()
    # return
    
    print('-'*82)
    print('orphan air_temperature/twice air')
    print('-'*82)
    twice_air = root['air_temperature/twice air']
    twice_air.orphan()
    print(root)
    print(twice_air)
    print(twice_air.data)
    print(dt)
    root.sanityCheck()
    # return
    
    print('-'*82)
    print('reinsert air_temperature/twice air')
    print('-'*82)
    root['air_temperature'].insertChild(1, twice_air)
    print(root)
    print(dt['air_temperature/twice air'])
    print(dt)
    root.sanityCheck()
    # return

    print('-'*82)
    print('orphan air_temperature/inherits')
    print('-'*82)
    inherits: XarrayDataTreeItem = root['air_temperature/inherits']
    print(inherits.data)
    inherits.orphan()
    print(root)
    print(inherits)
    print(inherits.data)
    print(inherits['again'].data)
    print(dt)
    root.sanityCheck()
    inherits.sanityCheck()
    # return

    print('-'*82)
    print('reinsert air_temperature/inherits')
    print('-'*82)
    root['air_temperature'].insertChild(0, inherits)
    print(root)
    print(inherits)
    print(inherits.data)
    print(dt['air_temperature'])
    print(dt['air_temperature/inherits'])
    print(dt['air_temperature/inherits/again'])
    print(inherits['again'])
    print(inherits['again'].data)
    print(dt)
    root.sanityCheck()
    inherits.sanityCheck()
    # return

    print('-'*82)
    print('orphan air_temperature/inherits/air')
    print('-'*82)
    print(dt['air_temperature/inherits/air'])
    air: XarrayDataTreeItem = root['air_temperature/inherits/air']
    air.orphan()
    print(root)
    print(air)
    print(air.data)
    print(dt['air_temperature/inherits'])
    print(dt)
    root.sanityCheck()
    air.sanityCheck()
    # return
    
    print('-'*82)
    print('reinsert air_temperature/inherits/air')
    print('-'*82)
    root['air_temperature/inherits'].appendChild(air)
    print(root)
    print(dt['air_temperature/inherits/air'])
    print(dt['air_temperature/inherits'])
    print(dt)
    root.sanityCheck()
    air.sanityCheck()
    # return

    print('-'*82)
    print('orphan air_temperature/inherits/again')
    print('-'*82)
    again: XarrayDataTreeItem = root['air_temperature/inherits/again']
    print(again.data)
    again.orphan()
    print(root)
    print(again)
    print(again.data)
    print(dt)
    root.sanityCheck()
    again.sanityCheck()
    # return

    print('-'*82)
    print('reinsert air_temperature/inherits/again')
    print('-'*82)
    root['air_temperature'].insertChild(2, again)
    print(root)
    print(again)
    print(dt['air_temperature'])
    print(dt['air_temperature/inherits'])
    print(dt['air_temperature/again'])
    print(dt)
    root.sanityCheck()
    again.sanityCheck()
    return


if __name__ == '__main__':
    test_tree()