""" Functions for use with Xarray. """

import numpy as np
import xarray as xr
import pint


ORDERED_DATA_VARS_KEY = '_XG_ordered_data_vars_'
INHERITED_DATA_VARS_KEY = '_XG_inherited_data_vars_'


def prepare_datatree_for_serialization(dt: xr.DataTree) -> None:
    store_ordered_data_vars(dt)
    store_inherited_data_vars(dt)
    remove_inherited_data_vars(dt)


def recover_datatree_post_serialization(dt: xr.DataTree) -> None:
    restore_inherited_data_vars(dt)
    restore_ordered_data_vars(dt)


def inherit_missing_data_vars(dt: xr.DataTree) -> None:
    """ All tree nodes inherit references (not copies) to any parent data_vars not already existing in the node.

    This updates the input tree inplace.
    """
    # # copy tree but not underlying data
    # dt = dt.copy(deep=False)

    # inherit missing data_vars from parent
    node: xr.DataTree
    for node in dt.subtree:
        parent: xr.DataTree = node.parent
        if not parent:
            continue
        to_inherit = {}
        for name, var in parent.data_vars.items():
            if name not in node.data_vars:
                to_inherit[name] = var
        if to_inherit:
            node.dataset = node.to_dataset().assign(to_inherit)
    
    # # return new tree with inherited data_vars
    # return dt


def remove_inherited_data_vars(dt: xr.DataTree) -> None:
    """ Remove any data_vars in each tree node that are references to data_vars in the parent node.

    This updates the input tree inplace.
    """
    # # copy tree but not underlying data
    # dt = dt.copy(deep=False)

    # remove inherited data_vars from parent
    # iterate in reverse to ensure reference chains are properly removed
    node: xr.DataTree
    for node in reversed(list(dt.subtree)):
        parent: xr.DataTree = node.parent
        if not parent:
            continue
        to_remove = []
        for name, var in parent.data_vars.items():
            if name in node.data_vars:
                if node.data_vars[name].values is var.values:
                    to_remove.append(name)
        if to_remove:
            node.dataset = node.to_dataset().drop_vars(to_remove)
    
    # # return new tree without any inherited data_vars
    # return dt


def store_inherited_data_vars(dt: xr.DataTree) -> None:
    """ For all tree nodes, store the names of data_vars inherited from the parent node in the node.attrs.

    Inherited means the underlying data is a reference to the date in the parent node.
    This updates the input tree inplace.
    """
    node: xr.DataTree
    for node in dt.subtree:
        parent: xr.DataTree = node.parent
        if not parent:
            continue
        inherited = []
        for name, var in node.data_vars.items():
            if (name in parent.data_vars) and (var.values is parent.data_vars[name].values):
                inherited.append(name)
        if inherited:
            node.attrs[INHERITED_DATA_VARS_KEY] = inherited
        elif INHERITED_DATA_VARS_KEY in node.attrs:
            del node.attrs[INHERITED_DATA_VARS_KEY]


def restore_inherited_data_vars(dt: xr.DataTree) -> None:
    """ Inherit data_vars from parent nodes as specified in the each node's metadata.

    This updates the input tree inplace.
    """
    node: xr.DataTree
    for node in dt.subtree:
        parent: xr.DataTree = node.parent
        if not parent:
            continue
        inherited = node.attrs.get(INHERITED_DATA_VARS_KEY, None)
        if inherited is None:
            continue
        to_inherit = {name: parent.data_vars[name] for name in inherited if name in parent.data_vars and name not in node.data_vars}
        if to_inherit:
            node.dataset = node.to_dataset().assign(to_inherit)


def store_ordered_data_vars(dt: xr.DataTree) -> None:
    """ Store the current data_var order in each node's metadata.

    This updates the input tree inplace.
    """
    node: xr.DataTree
    for node in dt.subtree:
        ordered_data_vars: tuple[str] = tuple(node.data_vars)
        if ordered_data_vars:
            node.attrs[ORDERED_DATA_VARS_KEY] = ordered_data_vars
        elif ORDERED_DATA_VARS_KEY in node.attrs:
            del node.attrs[ORDERED_DATA_VARS_KEY]


def restore_ordered_data_vars(dt: xr.DataTree) -> None:
    """ Reorder data_vars in each node according to the order specified in the node's metadata.

    This updates the input tree inplace.
    """
    node: xr.DataTree
    for node in dt.subtree:
        ordered_data_vars = node.attrs.get(ORDERED_DATA_VARS_KEY, None)
        if ordered_data_vars is None:
            continue
        ds = node.to_dataset()
        node.dataset = xr.Dataset(
            data_vars={key: ds.data_vars[key] for key in ordered_data_vars if key in ds.data_vars},
            coords=ds.coords,
            attrs=ds.attrs,
        )
    

def get_ordered_dims(objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> list[str]:
    """ Get the ordered dimensions from the DataArrays in any DataTrees or Datasets.
    
    New dimensions in subsequent objects will be append to the list of returned dimensions.
    This function is necessary because Xarray Dataset's do not have a defined dimension order (completely stupid in my opinion), whereas DataArray's do (as it should be).
    """
    dims: list[str] = []
    for obj in objects:
        if isinstance(obj, xr.DataTree) or isinstance(obj, xr.Dataset):
            arrays = obj.data_vars.values()
        elif isinstance(obj, xr.DataArray):
            arrays = [obj]
        
        array: xr.DataArray
        for array in arrays:
            for dim in array.dims:
                if dim not in dims:
                    dims.append(dim)
    return dims


def find_branch_root(node: xr.DataTree) -> xr.DataTree:
    """ Find root node for the aligned data in this node's branch.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Here, we search up the chain of parent nodes and return the last node with data aligned to the input node (i.e., the root of the branch).
    """
    while node.parent is not None:
        parent: xr.DataTree = node.parent
        # if not parent.has_data:
        #     break
        # # if the parent node has data, it must be aligned according to Xarray's DataTree rules
        # node = parent
        try:
            xr.align(node.dataset, parent.dataset, join='exact')
            node = parent
        except:
            return node
    return node


def find_subtree_branch_roots(dt: xr.DataTree) -> list[xr.DataTree]:
    """ Find root nodes for all aligned branches in the tree.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Here, we find and return all unique branch roots in the tree.
    """

    # if the root tree node has data, all descendents must be aligned with it
    if dt.has_data:
        return [dt]
    
    # find the branch root for each leaf node
    branch_roots: list[xr.DataTree] = []
    node: xr.DataTree
    for node in dt.leaves:
        # if not node.has_data:
        #     continue
        branch_root: xr.DataTree = find_branch_root(node)
        if branch_root not in branch_roots:
            branch_roots.append(branch_root)
    return branch_roots


def to_base_units(data: xr.DataArray | xr.Dataset | xr.DataTree, ureg: pint.UnitRegistry) -> xr.DataArray | xr.Dataset | xr.DataTree:
    """ Use pint to convert input data into base units.
    """
    if isinstance(data, xr.DataArray):
        if 'units' not in data.attrs:
            return data
        quantity: pint.Quantity = data.values * ureg(data.attrs['units'])
        quantity = quantity.to_base_units()
        da = data.copy(data=quantity.magnitude)
        da.attrs['units'] = str(quantity.units)
        return da
    elif isinstance(data, xr.Dataset):
        return xr.Dataset(
            data_vars={name: to_base_units(var) for name, var in data.data_vars.items()},
            coords={name: to_base_units(coord) for name, coord in data.coords.items()},
            attrs=data.attrs,
        )
    elif isinstance(data, xr.DataTree):
        dt: xr.DataTree = data.copy(deep=False)
        node: xr.DataTree
        for node in dt.subtree:
            node.dataset = to_base_units(node.to_dataset())
        return dt
