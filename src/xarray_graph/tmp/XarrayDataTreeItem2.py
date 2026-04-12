""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- moveRows: merge items?
- should we ask before removing inherited coords in descendents when moving a coord?
- enforce coord order at all times? note: this currently happens when refreshing the tree, but not otherwise.
"""

from __future__ import annotations
from enum import Enum
import xarray as xr
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import AbstractTreeItem
# import cmap


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

    def __init__(self, datatree: xr.DataTree, path: str = '', parent: XarrayDataTreeItem = None, sibling_index: int = None):
        # root datatree
        self._datatree = datatree
        # absolute path to this item in the datatree (e.g. '/air_temperature/air')
        if not path.startswith('/'):
            if parent is None:
                raise ValueError('Path must be absolute (start with /) if parent is None')
            # absolute path = parent absolute path + relative path
            path = parent.datapath() + '/' + path.strip('/')
        self._datapath = '/' + path.strip('/')
        super().__init__(parent, sibling_index)
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.
        """
        return self._tree_repr(lambda item: item.datapath())
    
    def datatree(self) -> xr.DataTree:
        """ Returns the absolute path to this item in the datatree (e.g. '/air_temperature/air').
        """
        return self._datatree
    
    def datapath(self) -> str:
        """ Returns the absolute path to this item in the datatree (e.g. '/air_temperature/air').
        """
        return '/' + self._datapath.strip('/')
    
    def data(self) -> xr.DataTree | xr.DataArray:
        return self._datatree[self._datapath]
    
    def parentNode(self) -> xr.DataTree | None:
        if '/' not in self._datapath.strip('/'):
            if self.isVariable():
                return self.datatree()
            return None
        parent_path = self._datapath.rsplit('/', 1)[0]
        return self._datatree[parent_path]
    
    def isDatatree(self) -> bool:
        return self.data() is self.datatree()
    
    def isNode(self) -> bool:
        return isinstance(self.data(), xr.DataTree)
    
    def isVariable(self) -> bool:
        return isinstance(self.data(), xr.DataArray)
    
    def isDataVar(self) -> bool:
        data: xr.DataTree | xr.DataArray = self.data()
        if not isinstance(data, xr.DataArray):
            return False
        return data.name in self.parentNode().data_vars
    
    def isCoord(self) -> bool:
        data: xr.DataTree | xr.DataArray = self.data()
        if not isinstance(data, xr.DataArray):
            return False
        return data.name in self.parentNode().coords

    def isIndexCoord(self) -> bool:
        data: xr.DataTree | xr.DataArray = self.data()
        if not isinstance(data, xr.DataArray):
            return False
        return data.name in self.parentNode().xindexes

    def isInheritedCoord(self) -> bool:
        data: xr.DataTree | xr.DataArray = self.data()
        if not isinstance(data, xr.DataArray):
            return False
        return data.name in self.parentNode()._inherited_coords_set()

    def updateSubtree(self, include_data_vars: bool = True, include_coords: bool = True, include_inherited_coords: bool = True, data_type_order: tuple[XarrayDataTreeType] = (COORD, DATA_VAR, NODE)) -> None:
        node: xr.DataTree = self.data()
        if not isinstance(node, xr.DataTree):
            return
        datatree = self.datatree()
        self.children = []
        for data_type in data_type_order:
            if data_type == COORD:
                if include_coords:
                    for coord in xarray_utils.ordered_coords_iter(node, include_inherited_coords):
                        path = f'/{node.path.strip('/')}/{coord.name}'
                        XarrayDataTreeItem(datatree, path, parent=self)
            elif data_type == DATA_VAR:
                if include_data_vars:
                    for var in node.data_vars.values():
                        path = f'/{node.path.strip('/')}/{var.name}'
                        XarrayDataTreeItem(datatree, path, parent=self)
            elif data_type == NODE:
                for child_node in node.children.values():
                    child_item = XarrayDataTreeItem(datatree, child_node.path, parent=self)
                    child_item.updateSubtree(include_data_vars, include_coords, include_inherited_coords, data_type_order)
    
    def name(self) -> str:
        return self.data().name
    
    def setName(self, name: str) -> None:
        if self.isDatatree():
            self._datatree.name = name
            return
        parent_node = self.parentNode()
        if parent_node and name in parent_node:
            raise ValueError(f'Name conflict: parent node already has an item named {name}')
        old_path = self.datapath()
        new_path = old_path.rsplit('/', 1)[0] + '/' + name if '/' in old_path else name
        # update datatree
        datatree = self.datatree()
        datatree[new_path] = datatree[old_path]
        del datatree[old_path]
        # update itemtree
        item: XarrayDataTreeItem
        for item in self.subtree_depth_first():
            item._datapath = item._datapath.replace(old_path, new_path, 1)
    
    def orphan(self) -> None:
        # remove data from existing datatree and put into new datatree
        data = self.data()
        if self.datatree() is data:
            return
        if isinstance(data, xr.DataTree):
            if not data.parent:
                if self.parent is not None:
                    raise ValueError('Error: Data is orphaned but item has parent')
                return # already orphaned
            new_datatree = data.copy(inherit=True, deep=False)
            new_datapath = f'/'
            data.orphan()
        elif isinstance(data, xr.DataArray):
            parent_node = self.parentNode()
            if data.name in parent_node.data_vars:
                new_datatree = xr.DataTree(
                    dataset=xr.Dataset(
                        data_vars={data.name: data}
                    ),
                )
            elif data.name in parent_node.coords:
                new_datatree = xr.DataTree(
                    dataset=xr.Dataset(
                        coords={data.name: data}
                    ),
                )
            new_datapath = f'/{data.name}'
            parent_node.dataset = parent_node.to_dataset().drop_vars(data.name)
        
        # update itemtree
        old_datapath = self._datapath
        item: XarrayDataTreeItem
        for item in self.subtree_depth_first():
            item._datatree = new_datatree
            item._datapath = item._datapath.replace(old_datapath, new_datapath, 1)
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None
    
    def insertChild(self, index: int, child_item: XarrayDataTreeItem) -> None:
        node: xr.DataTree = self.data()
        if not isinstance(node, xr.DataTree):
            raise TypeError('Cannot insert child into non-node item')
        child_name = child_item.name()
        if child_name in node:
            raise ValueError(f'Name conflict: node already has a child named {child_name}')
        
        # update datatree
        datatree = self.datatree()
        child_data = child_item.copy().data() # copy just in case child is not an orphan
        old_child_path = child_item._datapath
        new_child_path = f'/{node.path.strip('/')}/{child_name}'
        if child_item.isCoord():
            node.dataset = node.to_dataset().assign_coords({child_name: child_data})
        else:
            datatree[new_child_path] = child_data
        
        # update itemtree
        child_item._datatree = datatree
        item: XarrayDataTreeItem
        for item in child_item.subtree_depth_first():
            item._datapath = item._datapath.replace(old_child_path, new_child_path, 1)
        self.children.insert(index, child_item)
        child_item.parent = self
    
    def copy(self, deep: bool = True) -> XarrayDataTreeItem:
        """ Returns an orphaned copy of this item.
        """
        # copy data as new datatree
        data = self.data()
        if isinstance(data, xr.DataTree):
            new_datatree = data.copy(inherit=True, deep=False)
        elif isinstance(data, xr.DataArray):
            parent_node = self.parentNode()
            if data.name in parent_node.data_vars:
                new_datatree = xr.DataTree(
                    dataset=xr.Dataset(
                        data_vars={data.name: data}
                    ),
                )
            elif data.name in parent_node.coords:
                new_datatree = xr.DataTree(
                    dataset=xr.Dataset(
                        coords={data.name: data}
                    ),
                )
        return XarrayDataTreeItem(new_datatree, f'/{data.name}')


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

    # print(dt.path)
    # print(dt['/'].path)
    # print(dt['air_temperature'].path)
    # print(dt['air_temperature/inherits'].path)
    # return

    root = XarrayDataTreeItem(dt)
    root.updateSubtree()

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
    print([child.name() for child in inherits.children])
    print(again._datapath)
    print(again._datatree)
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
    print(air.data)
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
    print(again.data)
    again.orphan()
    print(root)
    print(again)
    print(again.data)
    print(dt)
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
    return


if __name__ == '__main__':
    test_tree()