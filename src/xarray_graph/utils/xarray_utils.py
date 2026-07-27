""" Utility functions for Xarray.
"""

from collections.abc import Iterator
from xarray import DataArray, Dataset, DataTree
from pint import UnitRegistry


ORDERED_DATA_VARS_KEY = '_XG_ORDERED_DATA_VARS'
INHERITED_DATA_VARS_KEY = '_XG_INHERITED_DATA_VARS'


def ordered_dims_iter(objects: list[DataTree | Dataset | DataArray]) -> Iterator[str]:
    """ Yield dimensions in the order they appear in the DataArrays for a collection of DataTree, Dataset, and DataArray objects.
    
    Xarray DataTree or Dataset do not have a defined dimension order, whereas DataArray does. This function is useful to work with dims ordered consistently based on DataArrays.
    """
    # keep track of dims already yielded
    yielded_dims: list[str] = []
    # yield dims in the order they appear in the DataArrays, skipping dims already yielded
    for obj in objects:
        if isinstance(obj, DataArray):
            vars = [obj]
        elif isinstance(obj, (DataTree, Dataset)):
            vars = obj.data_vars.values()
        else:
            # ignore objects that aren't DataArrays, Datasets, or DataTrees
            continue
        var: DataArray
        for var in vars:
            for dim in var.dims:
                if dim not in yielded_dims:
                    yield dim
                    yielded_dims.append(dim)


def ordered_coords_iter(node: DataTree, include_inherited: bool = True) -> Iterator[DataArray]:
    """ Yield coords in a defined order (index coords in dim order, then non-index coords) for a given DataTree.
    """
    if not include_inherited:
        inherited_coord_names: set[str] = node._inherited_coords_set()
    ordered_dims: tuple[str] = tuple(ordered_dims_iter([node]))
    # keep track of coords already yielded
    yielded_coord_names: list[str] = []
    # first yield index coords in dim order
    for dim in ordered_dims:
        if dim not in node.xindexes:
            continue
        if include_inherited or (dim not in inherited_coord_names):
            yield node.coords[dim]
            yielded_coord_names.append(dim)
    # next yield non-index coords
    for name, coord in node.coords.items():
        if name in yielded_coord_names:
            continue
        if include_inherited or (name not in inherited_coord_names):
            yield coord


def ordered_node_keys(node: DataTree, include_data_vars: bool = True, include_coords: bool = True, include_inherited_coords: bool = True) -> list[str]:
    """ Return a list of node keys in a defined order (ordered coords, data_vars, children) for a given DataTree.
    """
    keys = []
    if include_coords:
        keys.extend([coord.name for coord in ordered_coords_iter(node, include_inherited=include_inherited_coords)])
    if include_data_vars:
        keys.extend(node.data_vars)
    keys.extend(node.children)
    return keys


def move_item(src_parent_node: DataTree, src_key: str, dst_parent_node: DataTree, dst_key: str) -> bool:
    try:
        # test move in a copy
        src_parent_node_copy = src_parent_node.copy(deep=False)
        dst_parent_node_copy = dst_parent_node.copy(deep=False)
        dst_parent_node_copy[dst_key] = src_parent_node_copy[src_key]
        src_parent_node_copy = src_parent_node_copy.drop(src_key)
        # if successful, perform move on original nodes
        dst_parent_node[dst_key] = src_parent_node[src_key]
        src_parent_node.drop(src_key, inplace=True)
    except Exception:
        return False
    return True


def rename_dims(node: DataTree, dims_dict: dict[str, str]) -> None:
    """ Rename dimensions in a branch of aligned nodes.

    The aligned branch includes all descendants of the most distant ancestor aligned with the input node.
    Also renames index coords to match the new dimension names.
    """
    # root of aligned branch to be renamed
    branch_root: DataTree = aligned_root(node)
    # rename dims in branch
    branch_root.dataset = branch_root.to_dataset().rename_dims(dims_dict)
    for node in branch_root.descendants:
        node.dataset = node.to_dataset().swap_dims(dims_dict)
    # rename index coords to match new dims
    for node in branch_root.subtree:
        old_index_names = [name for name in node.xindexes if name in dims_dict and name not in node._inherited_coords_set()]
        if not old_index_names:
            continue
        new_index_coords = {dims_dict[old_name]: node.coords[old_name].copy(deep=False) for old_name in old_index_names}
        node.dataset = node.to_dataset().reindex(new_index_coords, copy=False).drop_indexes(old_index_names).reset_coords(old_index_names, drop=True)
        for child in node.descendants:
            old_names = [name for name in old_index_names if name in child.coords]
            if old_names:
                child.dataset = child.to_dataset().reset_coords(old_names, drop=True)


def to_base_units(data: DataArray | Dataset | DataTree, ureg: UnitRegistry) -> DataArray | Dataset | DataTree:
    """ Use pint to convert input data into base units.
    """
    from pint import Quantity
    if isinstance(data, DataArray):
        if 'units' not in data.attrs:
            return data
        quantity: Quantity = data.data * ureg(data.attrs['units'])
        quantity = quantity.to_base_units()
        da = data.copy(data=quantity.magnitude)
        da.attrs['units'] = str(quantity.units)
        return da
    elif isinstance(data, Dataset):
        return Dataset(
            data_vars={name: to_base_units(var) for name, var in data.data_vars.items()},
            coords={name: to_base_units(coord) for name, coord in data.coords.items()},
            attrs=data.attrs,
        )
    elif isinstance(data, DataTree):
        dt: DataTree = data.copy(deep=False)
        node: DataTree
        for node in dt.subtree:
            node.dataset = to_base_units(node.to_dataset())
        return dt


def aligned_root(node: DataTree) -> DataTree:
    """ Return the most distant ancestor aligned with node.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Thus, the branch root is the highest ancestor node that has data (which must be aligned with the input node).
    """
    for ancestor in tuple(reversed(node.parents)):
        if ancestor.has_data:
            return ancestor
    return node


def branch_iter(dt: DataTree) -> Iterator[DataTree]:
    """ Yield the branch root nodes for all aligned branches in the tree.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Here, we find and return all unique branch roots in the tree.
    """
    if dt.has_data:
        # if the root node has data, then the entire tree is one aligned branch
        if dt.parent and dt.parent.has_data:
            raise ValueError('Subtree does not contain any branch roots.')
        yield dt
        return
    
    # keep track of branch roots already yielded
    yielded_branches: list[DataTree] = []
    # yield the root node for each branch in the subtree
    for leaf in dt.leaves:
        branch_root: DataTree = aligned_root(leaf)
        if branch_root not in yielded_branches:
            yield branch_root
            yielded_branches.append(branch_root)


def inherit_missing_data_vars(dt: DataTree) -> DataTree:
    """ All tree nodes inherit references (not copies) to any parent data_vars not already existing in the node.

    Returns a new datatree with all inherited data_vars.
    """
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        parent: DataTree = node.parent
        if not parent:
            continue
        to_inherit = {}
        for name, var in parent.data_vars.items():
            if name not in node.data_vars:
                to_inherit[name] = var
        if to_inherit:
            node.dataset = node.to_dataset().assign(to_inherit)
    return dt


def remove_inherited_data_vars(dt: DataTree) -> DataTree:
    """ Remove any data_vars in each tree node that are references to data_vars in the parent node.

    Returns a new datatree without any inherited data_vars.
    """
    dt = dt.copy(deep=False)
    # iterate in reverse to ensure reference chains are properly removed
    node: DataTree
    for node in reversed(list(dt.subtree)):
        parent: DataTree = node.parent
        if not parent:
            continue
        to_remove = []
        for name, var in node.data_vars.items():
            if (name in parent.data_vars) and var.identical(parent.data_vars[name]):
                to_remove.append(name)
        if to_remove:
            node.dataset = node.to_dataset().drop_vars(to_remove)
    return dt


def store_inherited_data_vars(dt: DataTree) -> DataTree:
    """ For all tree nodes, store the names of data_vars inherited from the parent node in the node attrs.

    Inherited means the underlying data is a reference to the date in the parent node.
    Returns a new datatree with inherited data_vars defined in the node attrs.
    """
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        parent: DataTree = node.parent
        if not parent:
            continue
        inherited = []
        for name, var in node.data_vars.items():
            if (name in parent.data_vars) and var.identical(parent.data_vars[name]):
                inherited.append(name)
        if inherited:
            node.attrs[INHERITED_DATA_VARS_KEY] = ', '.join(inherited)
        elif INHERITED_DATA_VARS_KEY in node.attrs:
            del node.attrs[INHERITED_DATA_VARS_KEY]
    return dt


def restore_inherited_data_vars(dt: DataTree) -> DataTree:
    """ Inherit data_vars from parent nodes as specified in the each node's metadata.

    Returns a new datatree with inherited data_vars.
    """
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        parent: DataTree = node.parent
        if not parent:
            continue
        inherited = node.attrs.get(INHERITED_DATA_VARS_KEY, None)
        if inherited is None:
            continue
        inherited = [name.strip() for name in inherited.split(',')]
        to_inherit = {name: parent.data_vars[name] for name in inherited if name in parent.data_vars and name not in node.data_vars}
        if to_inherit:
            node.dataset = node.to_dataset().assign(to_inherit)
    return dt


def store_ordered_data_vars(dt: DataTree) -> DataTree:
    """ Store the current data_var order in each node's metadata.

    Returns a new datatree with data_var order defined in the node attrs.
    """
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        ordered_data_vars: tuple[str] = tuple(node.data_vars)
        if ordered_data_vars:
            node.attrs[ORDERED_DATA_VARS_KEY] = ', '.join(ordered_data_vars)
        elif ORDERED_DATA_VARS_KEY in node.attrs:
            del node.attrs[ORDERED_DATA_VARS_KEY]
    return dt


def restore_ordered_data_vars(dt: DataTree) -> DataTree:
    """ Reorder data_vars in each node according to the order specified in the node's metadata.

    Returns a new datatree with data_var order set as defined in the node attrs.
    """
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        ordered_data_vars = node.attrs.get(ORDERED_DATA_VARS_KEY, None)
        if ordered_data_vars is None:
            continue
        ordered_data_vars = [name.strip() for name in ordered_data_vars.split(',')]
        ds = node.to_dataset()
        reordered_data_vars = {name: ds.data_vars[name] for name in ordered_data_vars if name in ds.data_vars}
        for name in ds.data_vars:
            if name not in reordered_data_vars:
                reordered_data_vars[name] = ds.data_vars[name]
        if tuple(ds.data_vars) != tuple(reordered_data_vars):
            node.dataset = Dataset(
                data_vars=reordered_data_vars,
                coords=ds.coords,
                attrs=ds.attrs,
            )
    return dt


def store_attrs_objects_as_strings(dt: DataTree) -> DataTree:
    """ Serialize any list, tuple, or dict attr objects into strings.

    e.g., for serialization to HDF5.
    """
    from xarray_graph.utils.utils import value_to_str
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        for key, value in node.attrs.items():
            if isinstance(value, (list, tuple, dict)):
                node.attrs[key] = value_to_str(value)
        for var in node.variables.values():
            for key, value in var.attrs.items():
                if isinstance(value, (list, tuple, dict)):
                    var.attrs[key] = value_to_str(value)
    return dt


def restore_attrs_objects_from_strings(dt: DataTree) -> DataTree:
    """ Deserialize any list, tuple, or dict attr objects from strings.

    e.g., for deserialization from HDF5.
    """
    from xarray_graph.utils.utils import str_to_value
    dt = dt.copy(deep=False)
    node: DataTree
    for node in dt.subtree:
        for key, value in node.attrs.items():
            if isinstance(value, str):
                node.attrs[key] = str_to_value(value)
        for var in node.variables.values():
            for key, value in var.attrs.items():
                if isinstance(value, str):
                    var.attrs[key] = str_to_value(value)
    return dt


def prepare_for_serialization(dt: DataTree, flatten_attrs: bool = False) -> DataTree:
    """ Returns a new datatree ready for serialization.
    """
    dt = store_ordered_data_vars(dt)
    dt = store_inherited_data_vars(dt)
    dt = remove_inherited_data_vars(dt)
    if flatten_attrs:
        dt = store_attrs_objects_as_strings(dt)
    return dt


def recover_post_deserialization(dt: DataTree, unflatten_attrs: bool = False) -> DataTree:
    """ Returns a new datatree ready for use post serialization.
    """
    dt = restore_inherited_data_vars(dt)
    dt = restore_ordered_data_vars(dt)
    if unflatten_attrs:
        dt = restore_attrs_objects_from_strings(dt)
    return dt


def test():
    from xarray.tutorial import load_dataset
    dt = DataTree()
    dt['air_temperature'] = load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = load_dataset('air_temperature')
    dt['child/grandchild/greatgrandchild'] = DataTree()
    dt['child/grandchild/tiny'] = load_dataset('tiny')
    dt['child/grandchild/rasm'] = load_dataset('rasm')
    dt['rasm'] = load_dataset('rasm')
    dt['air_temperature_gradient'] = load_dataset('air_temperature_gradient')
    print()
    print()
    print(dt)

    # rename_dims(dt['air_temperature/inherits'], {'time': 't'})
    # print()
    # print()
    # print(dt)


if __name__ == '__main__':
    test()
