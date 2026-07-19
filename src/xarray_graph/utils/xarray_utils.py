""" Utility functions for Xarray.
"""

import builtins
from collections.abc import Iterator
import numpy as np
import xarray as xr
from pint import UnitRegistry, Quantity
# from ast import literal_eval
# from asteval import Interpreter


ORDERED_DATA_VARS_KEY = '_XG_ORDERED_DATA_VARS'
INHERITED_DATA_VARS_KEY = '_XG_INHERITED_DATA_VARS'


def ordered_dims_iter(objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> Iterator[str]:
    """ Yield dimensions in the order they appear in the DataArrays for a collection of DataTree, Dataset, and DataArray objects.
    
    Xarray DataTree or Dataset do not have a defined dimension order, whereas DataArray does. This function is useful to work with dims ordered consistently based on DataArrays.
    """
    # keep track of dims already yielded
    yielded_dims: list[str] = []
    # yield dims in the order they appear in the DataArrays, skipping dims already yielded
    for obj in objects:
        if isinstance(obj, xr.DataArray):
            vars = [obj]
        elif isinstance(obj, (xr.DataTree, xr.Dataset)):
            vars = obj.data_vars.values()
        else:
            # ignore objects that aren't DataArrays, Datasets, or DataTrees
            continue
        var: xr.DataArray
        for var in vars:
            for dim in var.dims:
                if dim not in yielded_dims:
                    yield dim
                    yielded_dims.append(dim)


def ordered_coords_iter(node: xr.DataTree, include_inherited: bool = True) -> Iterator[xr.DataArray]:
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


def ordered_node_keys(node: xr.DataTree, include_data_vars: bool = True, include_coords: bool = True, include_inherited_coords: bool = True) -> list[str]:
    """ Return a list of node keys in a defined order (ordered coords, data_vars, children) for a given DataTree.
    """
    keys = []
    if include_coords:
        keys.extend([coord.name for coord in ordered_coords_iter(node, include_inherited=include_inherited_coords)])
    if include_data_vars:
        keys.extend(node.data_vars)
    keys.extend(node.children)
    return keys


def move_item(src_parent_node: xr.DataTree, src_key: str, dst_parent_node: xr.DataTree, dst_key: str) -> bool:
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


def rename_dims(node: xr.DataTree, dims_dict: dict[str, str]) -> None:
    """ Rename dimensions in a branch of aligned nodes.

    The aligned branch includes all descendants of the most distant ancestor aligned with the input node.
    Also renames index coords to match the new dimension names.
    """
    # root of aligned branch to be renamed
    branch_root: xr.DataTree = aligned_root(node)
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


def to_base_units(data: xr.DataArray | xr.Dataset | xr.DataTree, ureg: UnitRegistry) -> xr.DataArray | xr.Dataset | xr.DataTree:
    """ Use pint to convert input data into base units.
    """
    if isinstance(data, xr.DataArray):
        if 'units' not in data.attrs:
            return data
        quantity: Quantity = data.data * ureg(data.attrs['units'])
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


def aligned_root(node: xr.DataTree) -> xr.DataTree:
    """ Return the most distant ancestor aligned with node.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Thus, the branch root is the highest ancestor node that has data (which must be aligned with the input node).
    """
    for ancestor in tuple(reversed(node.parents)):
        if ancestor.has_data:
            return ancestor
    return node


def branch_iter(dt: xr.DataTree) -> Iterator[xr.DataTree]:
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
    yielded_branches: list[xr.DataTree] = []
    # yield the root node for each branch in the subtree
    for leaf in dt.leaves:
        branch_root: xr.DataTree = aligned_root(leaf)
        if branch_root not in yielded_branches:
            yield branch_root
            yielded_branches.append(branch_root)


def index_by_identity(objects: list | tuple, target_obj):
    """
    Returns the index of the first occurrence of target_obj in objects based on identity.
    Returns -1 if the object is not found.
    """
    for i, item in enumerate(objects):
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


def str_to_value(text: str, default_type = None) -> bool | int | float | str | tuple | list | dict | set | np.ndarray:
    """ Convert a string representation of a value into the corresponding Python object.
    
    Handles basic values and containers and numpy arrays (keeps track of array dtype).
    """
    dtype = None
    if text.rstrip().endswith('>'):
        pos = text.rfind('<')
        if pos != -1:
            # assume value <type> format, strip type and parse value
            dtype = text[pos:].strip()[1:-1]
            text = text[:pos].strip()
    if text.lstrip().startswith('(') and text.rstrip().endswith(')') and dtype in [None, 'tuple']:
        # tuple
        inner_text = text.strip()[1:-1]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return tuple(values)
    if text.lstrip().startswith('[') and text.rstrip().endswith(']') and dtype != 'str':
        # list or numpy array
        inner_text = text.strip()[1:-1]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        # if type is specified, assume it is a numpy array and convert to that type
        if dtype:
            values = np.array(values, dtype=dtype)
        elif (default_type is not None) and (default_type is not list):
            values = np.array(values, dtype=default_type)
        return values
    if text.lstrip().startswith('{') and text.rstrip().endswith('}') and dtype in [None, 'dict', 'set']:
        # dict or set
        inner_text = text.strip()[1:-1]
        items = split_text(inner_text)
        if not items:
            # empty dict or set
            if dtype == 'set':
                return set()
            return {}
        if dtype == 'dict' or (dtype is None and ':' in items[0]):
            # dict
            values = {}
            for item in items:
                key, value = item.split(':', 1)
                values[key.strip()] = str_to_value(value.strip())
            return values
        else:
            # set
            values = set()
            for item in items:
                values.add(str_to_value(item))
            return values
    if dtype:
        # if dtype is specified but not a container, try to convert to that type
        py_dtype = getattr(builtins, dtype, None)
        if py_dtype:
            # if dtype is a built-in type, use it directly
            return py_dtype(text)
        # try numpy dtypes
        np_dtype = np.dtype(dtype)
        return np_dtype.type(text)
    try:
        # first try to convert to int
        value = int(text)
        if default_type and issubclass(default_type, np.integer):
            return default_type(value)
        return value
    except ValueError:
        try:
            # next try to convert to float
            value = float(text)
            if default_type and issubclass(default_type, np.floating):
                return default_type(value)
            return value
        except ValueError:
            # if not a number, return as string
            return text


def value_to_str(value, include_type: bool = False, in_array: bool = False) -> str:
    """ Convert a value to its string representation.

    Handles basic values and containers and numpy arrays (keeps track of array dtype).
    """
    if isinstance(value, tuple):
        return '(' + ', '.join([value_to_str(val, include_type=include_type) for val in value]) + ')'
    if isinstance(value, list):
        return '[' + ', '.join([value_to_str(val, include_type=include_type) for val in value]) + ']'
    if isinstance(value, set):
        return '{' + ', '.join([value_to_str(val, include_type=include_type) for val in value]) + '}'
    if isinstance(value, dict):
        return '{' + ', '.join([f'{key}: ' + value_to_str(val, include_type=include_type) for key, val in value.items()]) + '}'
    if isinstance(value, np.ndarray):
        text = '[' + ', '.join([value_to_str(val, include_type=include_type, in_array=True) for val in value]) + ']'
        if include_type and not in_array:
            return f'{text} <{value.dtype}>'
        return text
    if include_type and not in_array:
        dtype = type(value).__name__
        return f'{value} <{dtype}>'
    return str(value)


def split_text(text: str) -> list[str]:
    parts: list[str] = ['']
    grouping: str = ''
    for char in text:
        if char == '(' or char == '[' or char == '{':
            grouping += char
        elif grouping:
            if grouping[-1] == '(' and char == ')':
                grouping = grouping[:-1]
            elif grouping[-1] == '[' and char == ']':
                grouping = grouping[:-1]
            elif grouping[-1] == '{' and char == '}':
                grouping = grouping[:-1]
        if char == ',' and not grouping:
            parts.append('')
        else:
            parts[-1] += char
    parts = [part.strip() for part in parts if part.strip()]
    return parts


def inherit_missing_data_vars(dt: xr.DataTree) -> xr.DataTree:
    """ All tree nodes inherit references (not copies) to any parent data_vars not already existing in the node.

    Returns a new datatree with all inherited data_vars.
    """
    dt = dt.copy(deep=False)
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
    return dt


def remove_inherited_data_vars(dt: xr.DataTree) -> xr.DataTree:
    """ Remove any data_vars in each tree node that are references to data_vars in the parent node.

    Returns a new datatree without any inherited data_vars.
    """
    dt = dt.copy(deep=False)
    # iterate in reverse to ensure reference chains are properly removed
    node: xr.DataTree
    for node in reversed(list(dt.subtree)):
        parent: xr.DataTree = node.parent
        if not parent:
            continue
        to_remove = []
        for name, var in node.data_vars.items():
            if (name in parent.data_vars) and var.identical(parent.data_vars[name]):
                to_remove.append(name)
        if to_remove:
            node.dataset = node.to_dataset().drop_vars(to_remove)
    return dt


def store_inherited_data_vars(dt: xr.DataTree) -> xr.DataTree:
    """ For all tree nodes, store the names of data_vars inherited from the parent node in the node attrs.

    Inherited means the underlying data is a reference to the date in the parent node.
    Returns a new datatree with inherited data_vars defined in the node attrs.
    """
    dt = dt.copy(deep=False)
    node: xr.DataTree
    for node in dt.subtree:
        parent: xr.DataTree = node.parent
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


def restore_inherited_data_vars(dt: xr.DataTree) -> xr.DataTree:
    """ Inherit data_vars from parent nodes as specified in the each node's metadata.

    Returns a new datatree with inherited data_vars.
    """
    dt = dt.copy(deep=False)
    node: xr.DataTree
    for node in dt.subtree:
        parent: xr.DataTree = node.parent
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


def store_ordered_data_vars(dt: xr.DataTree) -> xr.DataTree:
    """ Store the current data_var order in each node's metadata.

    Returns a new datatree with data_var order defined in the node attrs.
    """
    dt = dt.copy(deep=False)
    node: xr.DataTree
    for node in dt.subtree:
        ordered_data_vars: tuple[str] = tuple(node.data_vars)
        if ordered_data_vars:
            node.attrs[ORDERED_DATA_VARS_KEY] = ', '.join(ordered_data_vars)
        elif ORDERED_DATA_VARS_KEY in node.attrs:
            del node.attrs[ORDERED_DATA_VARS_KEY]
    return dt


def restore_ordered_data_vars(dt: xr.DataTree) -> xr.DataTree:
    """ Reorder data_vars in each node according to the order specified in the node's metadata.

    Returns a new datatree with data_var order set as defined in the node attrs.
    """
    dt = dt.copy(deep=False)
    node: xr.DataTree
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
            node.dataset = xr.Dataset(
                data_vars=reordered_data_vars,
                coords=ds.coords,
                attrs=ds.attrs,
            )
    return dt


def store_attrs_objects_as_strings(dt: xr.DataTree) -> xr.DataTree:
    """ Serialize any list, tuple, or dict attr objects into strings.

    e.g., for serialization to HDF5.
    """
    dt = dt.copy(deep=False)
    node: xr.DataTree
    for node in dt.subtree:
        for key, value in node.attrs.items():
            if isinstance(value, (list, tuple, dict)):
                node.attrs[key] = value_to_str(value)
        for var in node.variables.values():
            for key, value in var.attrs.items():
                if isinstance(value, (list, tuple, dict)):
                    var.attrs[key] = value_to_str(value)
    return dt


def restore_attrs_objects_from_strings(dt: xr.DataTree) -> xr.DataTree:
    """ Deserialize any list, tuple, or dict attr objects from strings.

    e.g., for deserialization from HDF5.
    """
    dt = dt.copy(deep=False)
    node: xr.DataTree
    for node in dt.subtree:
        for key, value in node.attrs.items():
            if isinstance(value, str):
                node.attrs[key] = str_to_value(value)
        for var in node.variables.values():
            for key, value in var.attrs.items():
                if isinstance(value, str):
                    var.attrs[key] = str_to_value(value)
    return dt


def prepare_for_serialization(dt: xr.DataTree, flatten_attrs: bool = False) -> xr.DataTree:
    """ Returns a new datatree ready for serialization.
    """
    dt = store_ordered_data_vars(dt)
    dt = store_inherited_data_vars(dt)
    dt = remove_inherited_data_vars(dt)
    if flatten_attrs:
        dt = store_attrs_objects_as_strings(dt)
    return dt


def recover_post_deserialization(dt: xr.DataTree, unflatten_attrs: bool = False) -> xr.DataTree:
    """ Returns a new datatree ready for use post serialization.
    """
    dt = restore_inherited_data_vars(dt)
    dt = restore_ordered_data_vars(dt)
    if unflatten_attrs:
        dt = restore_attrs_objects_from_strings(dt)
    return dt


def test():
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
    print()
    print()
    print(dt)

    # rename_dims(dt['air_temperature/inherits'], {'time': 't'})
    # print()
    # print()
    # print(dt)


def test_ast_str():
    # aeval = Interpreter()
    # aeval("import numpy as np")
    test_values = [
        True,
        False,
        42,
        3.14,
        (1, 2, 3),
        [1, 2, 3],
        {1, 2, 3},
        {"a": 1, "b": 2, "c": np.array([1, 2, 3]), "d": {"nested": 42}, "e": np.int64(42)},
        np.array([1, 2, 3]),
        np.int64(42),
        np.float64(3.14),
        np.array([[1, 2], [3, 4]]),
        np.array([1, 2, 3], dtype=np.float32),
        np.array([1, 2, 3], dtype=np.int32),
    ]
    values_back = []
    for value in test_values:
        s = value_to_str(value, include_type=True)
        value_back = str_to_value(s)
        print(f'{value} <{type(value).__name__}> -> "{s}" -> {value_back} <{type(value_back).__name__}>')
        values_back.append(value_back)
    
    # print(values_back[7]['c'].dtype)
    # print(type(values_back[7]['e']))


if __name__ == '__main__':
    # test()
    test_ast_str()
