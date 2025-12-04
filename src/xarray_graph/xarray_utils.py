""" Utility functions for Xarray.
"""

# import numpy as np
import xarray as xr
import pint
from collections.abc import Iterator


def get_ordered_dims(objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> list[str]:
    """ Get the ordered dimensions from the DataArrays in any DataTrees or Datasets.
    
    This is useful to work with Dataset dims ordered the same as their underlying DataArrays. New dimensions in subsequent objects will be appended to the list of returned dimensions.
    
    This function is useful because Xarray Dataset's do not have a defined dimension order, whereas DataArray's do.
    This is because Datasets can contain multiple DataArrays with different dimensions.
    """
    dims: list[str] = []
    for obj in objects:
        if isinstance(obj, xr.DataArray):
            vars = [obj]
        else:
            # assume DataTree or Dataset
            vars = obj.data_vars.values()
    
        var: xr.DataArray
        for var in vars:
            for dim in var.dims:
                if dim not in dims:
                    dims.append(dim)
    return dims


def rename_dims(node: xr.DataTree, dims_dict: dict[str, str]) -> None:
    """ Rename dimensions in the input tree branch.

    This renames both dims and coords with the same name.
    Renames are applied to the entire aligned tree branch containing node.

    !!! This updates the input tree inplace.
    """
    for dim, new_dim in dims_dict.items():
        # rename dim along with coord of same name in aligned branch
        # branch starts from furthest ancestor that contains the dim as an index coord
        root = node
        for ancestor in node.parents:
            if dim in ancestor.xindexes:
                root = ancestor
            else:
                break
        root.dataset = root.to_dataset().rename_dims({dim: new_dim})
        # rename coord to match dim
        root.dataset = root.to_dataset().rename_vars({dim: new_dim})
        # the above does not rename dims in data_vars of child nodes, so do that here
        for child in root.subtree:
            if child is root:
                # already handled above
                continue
            for name, data_var in child.data_vars.items():
                if dim in data_var.dims:
                    new_data_var = data_var.swap_dims({dim: new_dim})
                    child.dataset = child.to_dataset().assign({name: new_data_var})


def subtree_depth_first_iter(node: xr.DataTree) -> Iterator[xr.DataTree]:
    """ Iterate over subtree nodes in depth-first order.

    Note: dt.subtree iterates in breadth-first order.
    """
    while node is not None:
        yield node
        node = _next_depth_first(node)


def subtree_reverse_depth_first_iter(node: xr.DataTree) -> Iterator[xr.DataTree]:
    """ Iterate over subtree nodes in reversed depth-first order.
    """
    start = _last_depth_first(node)
    stop = _prev_depth_first(node)
    node = start
    while node is not stop:
        yield node
        node = _prev_depth_first(node)


def subtree_leaf_iter(node: xr.DataTree) -> Iterator[xr.DataTree]:
    """ Iterate over subtree leaves.
    """
    start = _first_leaf(node)
    stop = _next_leaf(_last_leaf(node))
    node = start
    while node is not stop:
        yield node
        node = _next_leaf(node)


def subtree_reverse_leaf_iter(node: xr.DataTree) -> Iterator[xr.DataTree]:
    """ Iterate over subtree leaves.
    """
    start = _last_leaf(node)
    stop = _prev_leaf(_first_leaf(node))
    node = start
    while node is not stop:
        yield node
        node = _prev_leaf(node)


def subtree_branch_roots(dt: xr.DataTree) -> list[xr.DataTree]:
    """ Find branch root nodes for all aligned branches in the tree.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Here, we find and return all unique branch roots in the tree.
    """
    if dt.has_data:
        return [dt]
    
    # find the branch root for each leaf node
    branch_roots: list[xr.DataTree] = []
    leaf: xr.DataTree
    for leaf in subtree_leaf_iter(dt):
        branch_root: xr.DataTree = _branch_root(leaf)
        if branch_root not in branch_roots:
            branch_roots.append(branch_root)
    return branch_roots


def _first_child(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the first child of the input node.

    Returns None if there are no children.
    """
    if node.children:
        return list(node.children.values())[0]
    return None


def _last_child(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the last child of the input node.

    Returns None if there are no children.
    """
    if node.children:
        return list(node.children.values())[-1]
    return None


def _next_sibling(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the next sibling of the input node.

    Returns None if there is no next sibling.
    """
    parent: xr.DataTree = node.parent
    if parent is None:
        return None
    siblings = list(parent.children.values())
    index = index_by_identity(siblings, node)
    if 0 < index + 1 < len(siblings):
        return siblings[index + 1]
    else:
        return None


def _prev_sibling(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the previous sibling of the input node.

    Returns None if there is no previous sibling.
    """
    parent: xr.DataTree = node.parent
    if parent is None:
        return None
    siblings = list(parent.children.values())
    index = index_by_identity(siblings, node)
    if 0 <= index - 1 < len(siblings) - 1:
        return siblings[index - 1]
    else:
        return None


def _last_depth_first(node: xr.DataTree) -> xr.DataTree:
    """ Get the last node in depth-first order in the subtree rooted at the input node.
    """
    while node.children:
        node = _last_child(node)
    return node


def _next_depth_first(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the next node in depth-first order.

    Returns None if there is no next node.
    """
    if node.children:
        return _first_child(node)
    
    # no children, so go up until we can go right
    while node is not None:
        parent = node.parent
        if parent is None:
            return None
        next_sibling = _next_sibling(node)
        if next_sibling is not None:
            return next_sibling
        node = parent
    
    return None


def _prev_depth_first(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the previous node in depth-first order.

    Returns None if there is no previous node.
    """
    parent: xr.DataTree = node.parent
    if parent is None:
        return None
    prev_sibling = _prev_sibling(node)
    if prev_sibling is not None:
        return _last_depth_first(prev_sibling)
    return parent


def _first_leaf(node: xr.DataTree) -> xr.DataTree:
    """ Get the first leaf node.
    """
    while node.children:
        node = _first_child(node)
    return node


def _last_leaf(node: xr.DataTree) -> xr.DataTree:
    """ Get the last leaf node.
    """
    while node.children:
        node = _last_child(node)
    return node


def _next_leaf(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the next leaf node.

    Returns None if there is no next leaf.
    """
    if node.is_leaf:
        node = _next_depth_first(node)
        if node is None:
            return None
    return _first_leaf(node)


def _prev_leaf(node: xr.DataTree) -> xr.DataTree | None:
    """ Get the previous leaf node.

    Returns None if there is no previous leaf.
    """
    if node.is_leaf:
        node = _prev_depth_first(node)
        if node is None:
            return None
    while (node is not None) and (not node.is_leaf):
        node = _prev_depth_first(node)
    return node


def _branch_root(node: xr.DataTree) -> xr.DataTree:
    """ Find root node for the aligned data in the input node's branch.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Thus, the branch root is the highest ancestor node that has data (which must be aligned with the input node).
    """
    for ancestor in node.ancestors:
        if ancestor.has_data:
            return ancestor
    return node


def index_by_identity(lst, target_obj):
    """
    Returns the index of the first occurrence of target_obj in lst based on identity.
    Returns -1 if the object is not found.
    """
    for i, item in enumerate(lst):
        if item is target_obj:
            return i
    return -1


def unique_name(name: str, names: list[str], unique_counter_start: int = 1) -> str:
    """ Return name_1, or name_2, etc. until a unique name is found that does not exist in names.
    """
    if name not in names:
        return name
    base_name = name
    i = unique_counter_start
    name = f'{base_name}_{i}'
    while name in names:
        i += 1
        name = f'{base_name}_{i}'
    return name


# ----------------------------------------------------------


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
    

def get_copy_of_inherited_coords(node: xr.DataTree) -> dict[str, xr.DataArray]:
    """ Get a deep copy of all inherited coordinates.
    """
    if not node.parent:
        return {}

    return {name: node.parent.coords[name].copy(deep=True) for name in node._inherited_coords_set()}


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
