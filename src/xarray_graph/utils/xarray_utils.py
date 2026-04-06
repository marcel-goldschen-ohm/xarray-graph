""" Utility functions for Xarray.
"""

from collections.abc import Iterator
# import numpy as np
import xarray as xr
# import pint
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
# import qtawesome as qta


# metadata for serialization/deserialization
ORDERED_DATA_VARS_KEY = '_ORDERED_DATA_VARS'
INHERITED_DATA_VARS_KEY = '_INHERITED_DATA_VARS'


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
    

# def rename_dims(node: xr.DataTree, dims_dict: dict[str, str]) -> None:
#     """ Rename dimensions in the input tree branch.

#     This renames both dims and coords with the same name.
#     Renames are applied to the entire aligned tree branch containing node.

#     !!! This updates the input tree inplace.
#     """
#     branch_root: xr.DataTree = _branch_root(node)
#     branch_root.dataset = branch_root.to_dataset().rename_dims({dim: new_dim for dim, new_dim in dims_dict.items() if dim in branch_root.dims})
#     # rename coords to match dims
#     coord_renames = {dim: new_dim for dim, new_dim in dims_dict.items() if dim in branch_root.coords}
#     if coord_renames:
#         branch_root.dataset = branch_root.to_dataset().rename_vars(coord_renames)
    
#     for node in branch_root.subtree:
#         if node is branch_root:
#             # already handled above
#             continue
#         new_data_vars: dict[str, xr.DataArray] = {}
#         for name, data_var in node.data_vars.items():
#             dim_renames = {dim: new_dim for dim, new_dim in dims_dict.items() if dim in data_var.dims}
#             if dim_renames:
#                 data_var = data_var.swap_dims(dim_renames)
#             new_data_vars[name] = data_var
#         node.dataset = node.to_dataset().assign(new_data_vars)


# def rename_vars(node: xr.DataTree, vars_dict: dict[str, str]) -> None:
#     """ Rename variables in the input tree branch.

#     Renames are applied to node's entire subtree.

#     !!! This updates the input tree inplace.
#     """
#     anode: xr.DataTree
#     for anode in node.subtree:
#         anode_vars_dict = {name: new_name for name, new_name in vars_dict.items() if name in anode.variables}
#         if anode_vars_dict:
#             anode.dataset = anode.to_dataset().rename_vars(anode_vars_dict)


def aligned_root(node: xr.DataTree) -> xr.DataTree:
    """ Return the most distant ancestor aligned with node.

    Xarray DataTree requires that child nodes be aligned with their parent node.
    Thus, we define a branch as a subtree of aligned nodes.
    Thus, the branch root is the highest ancestor node that has data (which must be aligned with the input node).
    """
    for ancestor in node.ancestors:
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
            node.attrs[INHERITED_DATA_VARS_KEY] = inherited
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
            node.attrs[ORDERED_DATA_VARS_KEY] = ordered_data_vars
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


def prepare_for_serialization(dt: xr.DataTree) -> xr.DataTree:
    """ Returns a new datatree ready for serialization.
    """
    dt = store_ordered_data_vars(dt)
    dt = store_inherited_data_vars(dt)
    dt = remove_inherited_data_vars(dt)
    return dt


def recover_post_deserialization(dt: xr.DataTree) -> xr.DataTree:
    """ Returns a new datatree ready for use post serialization.
    """
    dt = restore_inherited_data_vars(dt)
    dt = restore_ordered_data_vars(dt)
    return dt


# def to_base_units(data: xr.DataArray | xr.Dataset | xr.DataTree, ureg: pint.UnitRegistry) -> xr.DataArray | xr.Dataset | xr.DataTree:
#     """ Use pint to convert input data into base units.
#     """
#     if isinstance(data, xr.DataArray):
#         if 'units' not in data.attrs:
#             return data
#         quantity: pint.Quantity = data.values * ureg(data.attrs['units'])
#         quantity = quantity.to_base_units()
#         da = data.copy(data=quantity.magnitude)
#         da.attrs['units'] = str(quantity.units)
#         return da
#     elif isinstance(data, xr.Dataset):
#         return xr.Dataset(
#             data_vars={name: to_base_units(var) for name, var in data.data_vars.items()},
#             coords={name: to_base_units(coord) for name, coord in data.coords.items()},
#             attrs=data.attrs,
#         )
#     elif isinstance(data, xr.DataTree):
#         dt: xr.DataTree = data.copy(deep=False)
#         node: xr.DataTree
#         for node in dt.subtree:
#             node.dataset = to_base_units(node.to_dataset())
#         return dt



# GUI functions


def infoDialog(data: xr.DataTree | xr.Dataset | xr.DataArray | list[xr.DataTree | xr.Dataset | xr.DataArray], parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None, font_size: int = None) -> None:
    text_edit = infoTextEdit(data, font_size=font_size)

    dlg = QDialog(parent)
    if size is not None:
        dlg.resize(size)
    if pos is not None:
        if parent:
            dlg.move(parent.mapToGlobal(pos))
        else:
            dlg.move(pos)
    if title is not None:
        dlg.setWindowTitle(title)
    
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(text_edit)

    dlg.exec()


def infoTextEdit(data: xr.DataTree | xr.Dataset | xr.DataArray | list[xr.DataTree | xr.Dataset | xr.DataArray], text_edit_to_update: QTextEdit = None, font_size: int = None) -> QTextEdit:
    text_edit = text_edit_to_update
    if not isinstance(text_edit, QTextEdit):
        text_edit = QTextEdit()
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if font_size is None:
            # font_size = QFont().pointSize()
            font_size = QFontDatabase.systemFont(QFontDatabase.SmallestReadableFont).pointSize() + 2
        font.setPointSize(font_size)
        text_edit.setFont(font)
    else:
        text_edit.clear()
        if font_size is not None:
            font = text_edit.font()
            font.setPointSize(font_size)
            text_edit.setFont(font)

    if isinstance(data, (xr.DataTree, xr.Dataset, xr.DataArray)):
        text_edit.setPlainText(str(data))
    elif isinstance(data, (list, tuple)):
        sep = False
        for obj in data:
            if sep:
                # TODO: check if this works on Windows (see https://stackoverflow.com/questions/76710833/how-do-i-add-a-full-width-horizontal-line-in-qtextedit)
                text_edit.insertHtml('<br><hr><br>')
            else:
                sep = True
            text_edit.insertPlainText(str(obj))

            # tc = self.result_text_box.textCursor()
            # # move the cursor to the end of the document
            # tc.movePosition(tc.End)
            # # insert an arbitrary QTextBlock that will inherit the previous format
            # tc.insertBlock()
            # # get the block format
            # fmt = tc.blockFormat()
            # # remove the horizontal ruler property from the block
            # fmt.clearProperty(fmt.BlockTrailingHorizontalRulerWidth)
            # # set (not merge!) the block format
            # tc.setBlockFormat(fmt)
            # # eventually, apply the cursor so that editing actually starts at the end
            # self.result_text_box.setTextCursor(tc)
    
    text_edit.setReadOnly(True)
    return text_edit


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


if __name__ == '__main__':
    test()
