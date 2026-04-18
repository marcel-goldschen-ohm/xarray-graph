""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- moveRows: merge items?
"""

from __future__ import annotations
from enum import Enum
from copy import deepcopy
import xarray as xr
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import AbstractTreeItem


class XarrayDataTreeItem(AbstractTreeItem):
    """ Tree item wrapper for xarray nodes and variables in XarrayDataTreeModel.

    This isn't strictly necessary, but it speeds object access and thus tree UI performance as compared to using paths to access the tree items, and it also provides a consistent interface to all tree models using AbstractTreeItem to interface with their data.
    """

    # order of data types in the tree model (top to bottom)
    class DataType(Enum):
        INDEX_COORD = 1
        COORD = 2
        DATA_VAR = 3
        NODE = 4

    def __init__(self, node: xr.DataTree, varname: str = '', parent: XarrayDataTreeItem = None, sibling_index: int = None):
        self._node = node
        self._varname = varname
        super().__init__(parent, sibling_index)
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(lambda item: item.abspath())
    
    def abspath(self) -> str:
        """ Returns the absolute path to this item in the datatree (e.g. '/air_temperature/air').
        """
        if self._varname:
            return f'{self._node.path.rstrip('/')}/{self._varname}'
        return self._node.path
    
    def data(self) -> xr.DataTree | xr.DataArray:
        if self._varname:
            return self._node[self._varname]
        return self._node
    
    def node(self) -> xr.DataTree:
        return self._node
    
    def parentNode(self) -> xr.DataTree | None:
        if self._varname:
            return self._node
        return self._node.parent
    
    def isNode(self) -> bool:
        return self._varname == ''
    
    def isVariable(self) -> bool:
        return self._varname != ''
    
    def isDataVar(self) -> bool:
        return (self._varname != '') and (self._varname in self._node.data_vars)
    
    def isCoord(self) -> bool:
        return (self._varname != '') and (self._varname in self._node.coords)

    def isIndexCoord(self) -> bool:
        return (self._varname != '') and (self._varname in self._node.xindexes)

    def isInheritedCoord(self) -> bool:
        return (self._varname != '') and (self._varname in self._node._inherited_coords_set())

    def dataType(self) -> XarrayDataTreeItem.DataType:
        if self.isIndexCoord():
            return XarrayDataTreeItem.DataType.INDEX_COORD
        elif self.isCoord():
            return XarrayDataTreeItem.DataType.COORD
        elif self.isDataVar():
            return XarrayDataTreeItem.DataType.DATA_VAR
        elif self.isNode():
            return XarrayDataTreeItem.DataType.NODE
    
    def rebuildSubtree(self, include_data_vars: bool = True, include_coords: bool = True, include_inherited_coords: bool = True) -> None:
        if not self.isNode():
            return
        self.children = []
        if include_coords:
            for coord in xarray_utils.ordered_coords_iter(self._node, include_inherited=include_inherited_coords):
                XarrayDataTreeItem(self._node, coord.name, parent=self)
        if include_data_vars:
            for name in self._node.data_vars:
                XarrayDataTreeItem(self._node, name, parent=self)
        for child_node in self._node.children.values():
            child_item = XarrayDataTreeItem(child_node, parent=self)
            child_item.rebuildSubtree(include_data_vars, include_coords, include_inherited_coords)
    
    def name(self) -> str:
        if self._varname:
            return self._varname
        return self._node.name
    
    def setName(self, name: str) -> None:
        if not name:
            # must have a valid name
            return
        if '/' in name:
            # object names cannot contain path separators "/"
            return
        if self.isInheritedCoord():
            # cannot rename inherited coords
            return
        old_name = self.name()
        if name == old_name:
            # nothing to do
            return
        parent_node: xr.DataTree = self.parentNode()
        if parent_node is None:
            # this is the root node
            self._node.name = name
            return
        if name in parent_node:
            raise ValueError(f'Name conflict: parent node already has an item named {name}')
        
        if self.isIndexCoord():
            # rename dimension in entire branch
            branch_root: xr.DataTree = xarray_utils.aligned_root(parent_node)
            branch_root.dataset = branch_root.to_dataset().rename_dims({old_name: name})
            for node in branch_root.descendants:
                node.dataset = node.to_dataset().swap_dims({old_name: name})
            # rename index coord
            new_index_coord = self.data()#.copy(deep=False).swap_dims({old_name: new_name})
            parent_node.dataset = parent_node.to_dataset().reindex({name: new_index_coord}, copy=False).drop_indexes(old_name).reset_coords(old_name, drop=True)
            for node in parent_node.descendants:
                if old_name in node.coords:
                    node.dataset = node.to_dataset().reset_coords(old_name, drop=True)
            # xarray_utils.rename_dims(parent_node, {old_name: name})
            self._varname = name
            # update item name in branch
            branch_root_item: XarrayDataTreeItem = self.root()[branch_root.path.strip('/')]
            branch_item: XarrayDataTreeItem
            for branch_item in branch_root_item.subtree_depth_first():
                if branch_item._varname == old_name:
                    branch_item._varname = name
        elif self.isVariable():
            parent_node.dataset = parent_node.to_dataset().rename_vars({old_name: name})
            self._varname = name
        elif self.isNode():
            parent_node.children = {name if name != old_name else name: child for name, child in parent_node.children.items()}
    
    def orphan(self) -> None:
        # remove data from existing datatree and put into new orphaned datatree
        if self.isNode():
            # need to copy in order to keep inherited coords
            new_node = self._node.copy(inherit=True, deep=False)
            self._node.orphan()
            self._node = new_node
        elif self.isDataVar():
            new_node = xr.DataTree(
                dataset=xr.Dataset(
                    data_vars={self._varname: self._node[self._varname]}
                ),
            )
            self._node.dataset = self._node.to_dataset().drop_vars(self._varname)
            self._node = new_node
        elif self.isCoord():
            new_node = xr.DataTree(
                dataset=xr.Dataset(
                    coords={self._varname: self._node[self._varname]}
                ),
            )
            self._node.dataset = self._node.to_dataset().drop_vars(self._varname)
            self._node = new_node
        
        # update itemtree
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None
        item: XarrayDataTreeItem
        for item in self.subtree_depth_first():
            if item is self:
                continue
            new_node_path = item.path().removesuffix(item._varname).strip('/')
            item._node = new_node[new_node_path]
    
    def insertChild(self, index: int, child_item: XarrayDataTreeItem) -> None:
        if not self.isNode():
            raise TypeError('Cannot insert child into non-node item')
        child_name = child_item.name()
        # if child_name in self._node:
        #     raise ValueError(f'Name conflict: node already has a child named {child_name}')
        
        # update datatree
        dt = self._node.root
        old_child_path = child_item.abspath()
        new_child_path = f'{self._node.path.rstrip('/')}/{child_name}'
        # print(old_child_path, '->', new_child_path)
        if child_item.isNode():
            dt[new_child_path] = child_item._node
            child_item._node = dt[new_child_path]
        elif child_item.isDataVar():
            dt[new_child_path] = child_item.data()
            child_item._node = self._node
        elif child_item.isCoord():
            self._node.dataset = self._node.to_dataset().assign_coords({child_name: child_item.data()})
            child_item._node = self._node
        
        # update itemtree
        self.children.insert(index, child_item)
        child_item.parent = self
        if old_child_path.endswith('/'):
            new_child_path += '/'
        item: XarrayDataTreeItem
        for item in child_item.subtree_depth_first():
            if item is child_item:
                continue
            new_node_path = item._node.path.replace(old_child_path, new_child_path, 1)
            # print(item._node.path, '->', new_node_path)
            item._node = dt[new_node_path]
    
    @staticmethod
    def _findInsertionIndex(parent_item: XarrayDataTreeItem, child_item: XarrayDataTreeItem, index: int) -> int:
        """ Find insertion index that preserves data type order.
        """
        data_type = child_item.dataType()
        items_of_type: list[XarrayDataTreeItem] = [item for item in parent_item.children if item.dataType() == data_type]

        if not items_of_type:
            # insert after all items of other data types that come before data_type in the model
            index = 0
            for dtype in tuple(XarrayDataTreeItem.DataType):
                if dtype == data_type:
                    break
                index += len([item for item in parent_item.children if item.dataType() == dtype])
            return index
        elif index > items_of_type[-1].siblingIndex():
            # append after last item of data_type
            return items_of_type[-1].siblingIndex() + 1
        elif index <= items_of_type[0].siblingIndex():
            # prepend before first item of data_type
            return items_of_type[0].siblingIndex()
        else:
            # insert at index which falls within items of data_type
            return index
    
    def copy(self, deep: bool = True) -> XarrayDataTreeItem:
        """ Returns an orphaned copy of this item.
        """
        # copy data as new datatree
        if self.isNode():
            node_copy = self._node.copy(inherit=True, deep=deep)
            item_copy = XarrayDataTreeItem(node_copy)
            # copy subtree
            item: XarrayDataTreeItem
            for item in self.subtree_depth_first():
                if item is self:
                    continue
                new_node_path_in_copy = item._node.relative_to(self._node)
                if new_node_path_in_copy == '.':
                    # item must be a variable
                    new_node = node_copy
                    new_parent_item = item_copy
                elif item.isVariable():
                    new_node = node_copy[new_node_path_in_copy]
                    new_parent_item = item_copy[new_node_path_in_copy.strip('/')]
                elif item.isNode():
                    new_node = node_copy[new_node_path_in_copy]
                    if '/' in new_node_path_in_copy.strip('/'):
                        new_parent_item = item_copy[new_node_path_in_copy.strip('/').rsplit('/', 1)[0]]
                    else:
                        new_parent_item = item_copy
                subitem_copy = XarrayDataTreeItem(new_node, item._varname, parent=new_parent_item)
                try:
                    subitem_copy._view_state = deepcopy(item._view_state)
                except AttributeError:
                    pass
        elif self.isDataVar():
            varname = self._varname
            var_copy = self._node[varname].copy(deep=deep)
            node_copy = xr.DataTree(
                dataset=xr.Dataset(
                    data_vars={varname: var_copy}
                ),
            )
            item_copy = XarrayDataTreeItem(node_copy, varname)
        elif self.isCoord():
            varname = self._varname
            coord_copy = self._node[varname].copy(deep=deep)
            node_copy = xr.DataTree(
                dataset=xr.Dataset(
                    coords={varname: coord_copy}
                ),
            )
            item_copy = XarrayDataTreeItem(node_copy, varname)
        try:
            item_copy._view_state = deepcopy(self._view_state)
        except AttributeError:
            pass
        return item_copy


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
    dt['rasm/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    # print(dt)

    # print(dt.path)
    # print(dt[''].path)
    # print(dt['/'].path)
    # print(dt['air_temperature'].path)
    # print(dt['air_temperature/inherits'].path)
    # print('/child'.rsplit('/', 1))
    # return

    root = XarrayDataTreeItem(dt)
    root.rebuildSubtree()

    print('-'*82)
    print('-'*82)
    print(root)
    # print(dt)
    # return

    print('-'*82)
    print('orphan child/grandchild/rasm')
    print('-'*82)
    rasm: XarrayDataTreeItem = root['child/grandchild/rasm']
    rasm.orphan()
    print(root)
    print(rasm)
    # print(rasm._node.path)
    # print(rasm['time']._node.path)
    # print(rasm['time']._node.path.strip('/'))
    # print(rasm['time']._varname)
    # print(rasm['time'].abspath())
    print(rasm.data())
    print(dt)
    # return
    
    print('-'*82)
    print('orphan air_temperature/twice air')
    print('-'*82)
    twice_air: XarrayDataTreeItem = root['air_temperature/twice air']
    twice_air.orphan()
    print(root)
    print(twice_air)
    print(twice_air.data())
    print(dt)
    # return
    
    print('-'*82)
    print('reinsert air_temperature/twice air')
    print('-'*82)
    root['air_temperature'].insertChild(1, twice_air)
    print(root)
    print(dt['air_temperature/twice air'])
    print(dt)
    # return

    print('-'*82)
    print('orphan air_temperature/inherits')
    print('-'*82)
    inherits: XarrayDataTreeItem = root['air_temperature/inherits']
    print(inherits.data())
    inherits.orphan()
    print(root)
    print(inherits)
    print(inherits.data())
    again: XarrayDataTreeItem = inherits['again']
    print(again.data())
    print(dt)
    # return

    print('-'*82)
    print('reinsert air_temperature/inherits')
    print('-'*82)
    root['air_temperature'].insertChild(0, inherits)
    print(root)
    print(inherits)
    # again: XarrayDataTreeItem = inherits['again']
    print(inherits.data())
    print(dt['air_temperature'])
    print(dt['air_temperature/inherits'])
    print(dt['air_temperature/inherits/again'])
    print(inherits['again'])
    print(inherits['again'].data())
    print(dt)
    # return

    print('-'*82)
    print('orphan air_temperature/inherits/air')
    print('-'*82)
    print(dt['air_temperature/inherits/air'])
    air: XarrayDataTreeItem = root['air_temperature/inherits/air']
    air.orphan()
    print(root)
    print(air)
    print(air.data())
    print(dt['air_temperature/inherits'])
    print(dt)
    # return
    
    print('-'*82)
    print('reinsert air_temperature/inherits/air')
    print('-'*82)
    root['air_temperature/inherits'].appendChild(air)
    print(root)
    print(dt['air_temperature/inherits/air'])
    print(dt['air_temperature/inherits'])
    print(dt)
    # return

    print('-'*82)
    print('orphan air_temperature/inherits/again')
    print('-'*82)
    again: XarrayDataTreeItem = root['air_temperature/inherits/again']
    print(again.data())
    again.orphan()
    print(root)
    print(again)
    print(again.data())
    print(dt)
    # return

    print('-'*82)
    print('reinsert air_temperature/inherits/again')
    print('-'*82)
    root['air_temperature/inherits'].insertChild(2, again)
    print(root)
    print(again)
    print(dt['air_temperature'])
    print(dt['air_temperature/inherits'])
    print(dt['air_temperature/inherits/again'])
    print(dt)
    # return

    print('-'*82)
    print('copy air_temperature/inherits')
    print('-'*82)
    inherits: XarrayDataTreeItem = root['air_temperature/inherits']
    inherits_copy = inherits.copy()
    print(inherits)
    print(inherits_copy)
    print(inherits.data())
    print(inherits_copy.data())
    print(dt)
    # return


if __name__ == '__main__':
    test_tree()