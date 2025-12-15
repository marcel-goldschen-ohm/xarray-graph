""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- setData: rename index coord -> rename dimension
- moveRows: merge items?
- transferItems
- moved inherited coords currently become regular coords but share the same underlying data as before. should we copy the data?
- should we ask before removing inherited coords in descendents when moving a coord?
- enforce coord order? note: this currently happens when refreshing the tree, but not otherwise.
- test all tree manipulations
- test all conflict handling
"""

from __future__ import annotations
from collections.abc import Iterator
from enum import Enum
from copy import copy
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph import xarray_utils, AbstractTreeItem, AbstractTreeModel, AbstractTreeMimeData
import cmap


class XarrayDataTreeType(Enum):
    GROUP = 1
    DATA_VAR = 2
    COORD = 3

# for convenience in this file
GROUP, DATA_VAR, COORD = list(XarrayDataTreeType)


class XarrayDataTreeItem(AbstractTreeItem):
    """ Tree item wrapper for xarray groups and variables in XarrayDataTreeModel.

    This isn't strictly necessary, but it speeds object access and thus tree UI performance as compared to using paths to access the underlying datatree objects, and it also provides a consistent interface to all tree models using AbstractTreeItem to interface with their data.
    """

    def __init__(self, data: xr.DataTree | xr.DataArray, data_type: XarrayDataTreeType = DATA_VAR, parent: XarrayDataTreeItem = None, sibling_index: int = -1):
        # tree linkage
        super().__init__(parent, sibling_index)

        # item data
        self.data: xr.DataTree | xr.DataArray = data

        # Useful when working with orphaned items associated with DataArrays as otherwise wether those items refer to data_vars or coords is indeterminate (e.g., see `insertItems`).
        # Note: It is up to you to ensure this remains valid in those few cases where you need it.
        self._data_type: XarrayDataTreeType = GROUP if isinstance(data, xr.DataTree) else data_type
    
    def __str__(self) -> str:
        """ Returns a multi-line string representation of this item's tree branch.

        Each item is described by its name.
        """
        return self._tree_repr(lambda item: item.data.name or '/')
    
    @property
    def name(self) -> str:
        return self.data.name or '/'
    
    @property
    def path(self) -> str:
        if self.parent is None:
            return '/'
        parent_node: xr.DataTree = self.parent.data
        return parent_node.path.rstrip('/') + f'/{self.data.name}'
    
    @property
    def data_type(self) -> XarrayDataTreeType:
        if self.is_group:
            return GROUP
        elif self.is_data_var:
            return DATA_VAR
        elif self.is_coord:
            return COORD
    
    @property
    def is_group(self) -> bool:
        return isinstance(self.data, xr.DataTree)
    
    @property
    def is_variable(self) -> bool:
        return isinstance(self.data, xr.DataArray)
    
    @property
    def is_data_var(self) -> bool:
        if not isinstance(self.data, xr.DataArray):
            return False
        if self.parent:
            return self.data.name in self.parent.data.data_vars
        return self._data_type == DATA_VAR
    
    @property
    def is_coord(self) -> bool:
        if not isinstance(self.data, xr.DataArray):
            return False
        if self.parent:
            return self.data.name in self.parent.data.coords
        return self._data_type == COORD
    
    @property
    def is_index_coord(self) -> bool:
        return self.is_coord and self.data.name in self.parent.data.xindexes
    
    @property
    def is_inherited_coord(self) -> bool:
        return self.is_coord and self.data.name in self.parent.data._inherited_coords_set()


class XarrayDataTreeModel(AbstractTreeModel):
    """ PyQt tree model interface for a Xarray DataTree.
    """

    _data_type_order: tuple[XarrayDataTreeType] = (COORD, DATA_VAR, GROUP)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['DataTree', 'Details']

        # parts of datatree to show
        self._is_data_vars_visible: bool = True
        self._is_coords_visible: bool = False
        self._is_inherited_coords_visible: bool = False
        self._is_details_column_visible: bool = False
        self._is_shared_data_highlighted: bool = False
        self._is_debug_info_visible: bool = False

        # icons
        self._group_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')

        # colors
        self._shared_data_colormap: dict[int, QColor] = {}

        # setup item tree
        datatree: xr.DataTree = xr.DataTree()
        self._root_item = XarrayDataTreeItem(datatree)
        self._updateItemSubtree(self._root_item)
    
    def datatree(self) -> xr.DataTree:
        """ Get the model's current datatree.
        """
        root_item: XarrayDataTreeItem = self.rootItem()
        return root_item.data
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        """ Reset the model to the input datatree.
        """
        root_item = XarrayDataTreeItem(datatree)
        self.setRootItem(root_item)
    
    def _onReset(self):
        self._updateItemSubtree(self._root_item)
        if self._is_shared_data_highlighted:
            self._updateSharedDataColors()
    
    def _updateItemSubtree(self, item: XarrayDataTreeItem) -> None:
        if not item.is_group:
            return
        item.children = [] # will repopulate below
        dtype: XarrayDataTreeType
        for dtype in self._data_type_order:
            if dtype == GROUP:
                group: xr.DataTree
                for group in item.data.children.values():
                    child_item = XarrayDataTreeItem(group, data_type=GROUP, parent=item)
                    self._updateItemSubtree(child_item)
            elif dtype == DATA_VAR:
                if self.isDataVarsVisible():
                    data_var: xr.DataArray
                    for data_var in item.data.data_vars.values():
                        child_item = XarrayDataTreeItem(data_var, data_type=DATA_VAR, parent=item)
            elif dtype == COORD:
                if self.isCoordsVisible():
                    coord: xr.DataArray
                    for coord in self._orderedCoords(item.data):
                        child_item = XarrayDataTreeItem(coord, data_type=COORD, parent=item)
    
    def _orderedCoords(self, group: xr.DataTree) -> Iterator[xr.DataArray]:
        if not self.isInheritedCoordsVisible():
            inherited_coord_names: set[str] = group._inherited_coords_set()
        ordered_dims: tuple[str] = tuple(xarray_utils.get_ordered_dims([group]))
        traversed_coord_names: list[str] = []
        dim: str
        for dim in ordered_dims:
            if dim not in group.indexes:
                continue
            if self.isInheritedCoordsVisible() or (dim not in inherited_coord_names):
                yield group.coords[dim]
                traversed_coord_names.append(dim)
        coord: xr.DataArray
        for coord in group.coords.values():
            if coord.name in traversed_coord_names:
                continue
            if self.isInheritedCoordsVisible() or (coord.name not in inherited_coord_names):
                yield coord
    
    def _visibleRowNames(self, group: xr.DataTree) -> list[str]:
        names: list[str] = []
        dtype: XarrayDataTreeType
        for dtype in self._data_type_order:
            if dtype == GROUP:
                names += list(group.children)
            elif dtype == DATA_VAR:
                if self.isDataVarsVisible():
                    names += list(group.data_vars)
            elif dtype == COORD:
                if self.isCoordsVisible():
                    names += [coord.name for coord in self._orderedCoords(group)]
        return names
    
    def isDataVarsVisible(self) -> bool:
        return self._is_data_vars_visible
    
    def setDataVarsVisible(self, visible: bool) -> None:
        if visible == self.isDataVarsVisible():
            return

        self.beginResetModel()
        self._is_data_vars_visible = visible
        self._updateItemSubtree(self._root_item)
        self.endResetModel()
    
    def isCoordsVisible(self) -> bool:
        return self._is_coords_visible
    
    def setCoordsVisible(self, visible: bool) -> None:
        if visible == self.isCoordsVisible():
            return
        
        self.beginResetModel()
        self._is_coords_visible = visible
        self._updateItemSubtree(self._root_item)
        self.endResetModel()
    
    def isInheritedCoordsVisible(self) -> bool:
        return self._is_inherited_coords_visible
    
    def setInheritedCoordsVisible(self, visible: bool) -> None:
        if visible == self.isInheritedCoordsVisible():
            return
        
        self.beginResetModel()
        self._is_inherited_coords_visible = visible
        self._updateItemSubtree(self._root_item)
        self.endResetModel()
    
    def isDetailsColumnVisible(self) -> bool:
        return self._is_details_column_visible
    
    def setDetailsColumnVisible(self, visible: bool) -> None:
        if visible == self.isDetailsColumnVisible():
            return
        
        if visible:
            self.beginInsertColumns(QModelIndex(), 1, 1)
            self._is_details_column_visible = visible
            self.endInsertColumns()
        else:
            self.beginRemoveColumns(QModelIndex(), 1, 1)
            self._is_details_column_visible = visible
            self.endRemoveColumns()
    
    def isSharedDataHighlighted(self) -> bool:
        return self._is_shared_data_highlighted
    
    def setSharedDataHighlighted(self, highlighted: bool) -> None:
        if highlighted == self.isSharedDataHighlighted():
            return

        if highlighted:
            self._updateSharedDataColors()

        self.beginResetModel()
        self._is_shared_data_highlighted = highlighted
        self.endResetModel()
    
    def isDebugInfoVisible(self) -> bool:
        return self._is_debug_info_visible
    
    def setDebugInfoVisible(self, visible: bool) -> None:
        if visible == self.isDebugInfoVisible():
            return

        self.beginResetModel()
        self._is_debug_info_visible = visible
        self.endResetModel()
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        if self.isDetailsColumnVisible():
            return 2
        return 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """ Default item flags.
        
        Supports drag-and-drop if it is enabled in `supportedDropActions`.
        """
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        
        item: XarrayDataTreeItem = self.itemFromIndex(index)
        if item.is_inherited_coord:
            return Qt.ItemFlag.ItemIsEnabled
        
        if index.column() == 0:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        elif index.column() == 1:
            # cannot edit details column
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            if item.is_group:
                # can drag and drop onto DataTree items
                flags |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
            else:
                # can drag but not drop onto DataArray items
                flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            if index.column() == 0:
                # main column
                return item.data.name
            elif index.column() == 1:
                # details column
                if item.is_group:
                    sizes_str = ', '.join([f'{dim}: {size}' for dim, size in item.data.dataset.sizes.items()])
                    rep = f'({sizes_str})'
                    if self._is_debug_info_visible:
                        rep = f'<id={id(item.data)}> ' + rep
                    return rep
                elif item.is_data_var:
                    parent_group: xr.DataTree = item.parent.data
                    rep = str(parent_group.dataset)
                    i = rep.find('Data variables:')
                    i = rep.find(f' {item.data.name} ', i)  # find data_var
                    i = rep.find('(', i)  # skip data_var name
                    j = rep.find('\n', i)
                    rep = rep[i:j] if j > 0 else rep[i:]
                    if self._is_debug_info_visible:
                        rep = f'<id={id(item.data.data)}> ' + rep
                    return rep
                elif item.is_coord:
                    parent_group: xr.DataTree = item.parent.data
                    rep = str(parent_group.dataset)
                    i = rep.find('Coordinates:')
                    i = rep.find(f' {item.data.name} ', i)  # find coord
                    i = rep.find('(', i)  # skip coord name
                    j = rep.find('\n', i)
                    rep = rep[i:j] if j > 0 else rep[i:]
                    if item.is_index_coord:
                        rep = '* ' + rep
                    if self._is_debug_info_visible:
                        rep = f'<id={id(item.data.data)}> ' + rep
                    return rep
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: XarrayDataTreeItem = self.itemFromIndex(index)
                if item.is_group:
                    return self._group_icon
                elif item.is_data_var:
                    return self._data_var_icon
                elif item.is_coord:
                    return self._coord_icon
        elif role == Qt.ItemDataRole.ForegroundRole:
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            if self._is_shared_data_highlighted and item.is_variable:
                mem = id(item.data.values)
                color = self._shared_data_colormap.get(mem, None)
                if color is not None:
                    if item.is_inherited_coord:
                        color = copy(color)
                        color.setAlpha(128)
                    return color
            if item.is_inherited_coord:
                color: QColor = QApplication.palette().color(QPalette.ColorRole.Text)
                color.setAlpha(128)
                return color

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        """ This amounts to just renaming items.
        """
        if not index.isValid():
            return False
        if index.column() != 0:
            # only allow editing the names in the tree column 0
            # cannot edit details column 1
            return False
        if role == Qt.ItemDataRole.EditRole:
            # rename object
            new_name: str = value.strip()
            if not new_name or '/' in new_name:
                parent_widget: QWidget = QApplication.focusWidget()
                title='Invalid Name'
                text = f'"{new_name}" is not a valid DataTree key. Must be a non-empty string without any path separators "/".'
                QMessageBox.warning(parent_widget, title, text)
                return False
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            old_name = item.data.name
            if new_name == old_name:
                # nothing to do
                return False
            parent_item: XarrayDataTreeItem = item.parent
            parent_group: xr.DataTree = parent_item.data
            parent_keys: list[str] = list(parent_group.keys())
            if new_name in parent_keys:
                parent_widget: QWidget = QApplication.focusWidget()
                title='Existing Name'
                text = f'"{new_name}" already exists in parent DataTree.'
                QMessageBox.warning(parent_widget, title, text)
                return False
            if item.is_group:
                # rename group
                try:
                    parent_group.children = {name if name != old_name else new_name: child for name, child in parent_group.children.items()}
                    self.dataChanged.emit(index, index)
                    return True
                except Exception as err:
                    from warnings import warn
                    warn(err)
                    return False
            elif item.is_data_var:
                # rename data_var
                try:
                    parent_dataset: xr.Dataset = parent_group.to_dataset()
                    renamed_data_vars = {name if name != old_name else new_name: data_var for name, data_var in parent_dataset.data_vars.items()}
                    new_parent_dataset = xr.Dataset(
                        data_vars=renamed_data_vars,
                        coords=parent_dataset.coords,
                        attrs=parent_dataset.attrs,
                    )
                    parent_group.dataset = new_parent_dataset
                    item.data = new_parent_dataset.data_vars[new_name]
                    self.dataChanged.emit(index, index)
                    return True
                except Exception as err:
                    from warnings import warn
                    warn(err)
                    return False
            elif item.is_coord:
                # rename coord
                try:
                    parent_dataset: xr.Dataset = parent_group.to_dataset()
                    new_parent_dataset: xr.Dataset = parent_dataset.assign_coords({new_name: parent_dataset.coords[old_name]}).drop_vars([old_name])
                    new_coord_names = [name if name != old_name else new_name for name in parent_dataset.coords]
                    renamed_coords = {name: new_parent_dataset.coords[name] for name in new_coord_names}
                    new_parent_dataset = xr.Dataset(
                        data_vars=new_parent_dataset.data_vars,
                        coords=renamed_coords,
                        attrs=parent_dataset.attrs,
                    )
                    parent_group.dataset = new_parent_dataset
                    item.data = new_parent_dataset.coords[new_name]
                    for item in parent_item.children:
                        if item.is_data_var:
                            item.data = new_parent_dataset.data_vars[item.name]
                    self.dataChanged.emit(index, index)
                    self._updateSubtreeCoordItems(parent_item)
                    # TODO: rename coord and also dimension if coord is an index coord
                    return True
                except Exception as err:
                    from warnings import warn
                    warn(err)
                    return False
        return False

    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        if count <= 0:
            return False
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row + count > num_rows):
            return False
        
        parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)
        items: list[XarrayDataTreeItem] = parent_item.children[row: row + count]
        group_items: list[XarrayDataTreeItem] = [item for item in items if item.is_group]
        data_var_items: list[XarrayDataTreeItem] = [item for item in items if item.is_data_var]
        coord_items: list[XarrayDataTreeItem] = [item for item in items if item.is_coord and not item.is_inherited_coord]
        var_items: list[XarrayDataTreeItem] = data_var_items + coord_items

        parent_node: xr.DataTree = parent_item.data
        
        # remove any inherited coord items in descendents
        # note that coord_items only contains non-inherited coords
        if self.isInheritedCoordsVisible() and coord_items:
            coord_names: list[str] = [item.name for item in coord_items]
            item: XarrayDataTreeItem
            for item in parent_item.subtree_reverse_depth_first():
                if item is parent_item or not item.is_group:
                    continue
                group: xr.DataTree = item.data
                inherited_coord_names: set[str] = group._inherited_coords_set()
                inherited_coord_names_to_remove: list[str] = [name for name in inherited_coord_names if name in coord_names]
                if inherited_coord_names_to_remove:
                    inherited_coord_items_to_remove: list[XarrayDataTreeItem] = [child for child in item.children if child.is_inherited_coord and child.name in inherited_coord_names_to_remove]
                    if inherited_coord_items_to_remove:
                        self.removeItems(inherited_coord_items_to_remove)
        
        # remove items
        self.beginRemoveRows(parent_index, row, row + count - 1)
        
        # update datatree
        item: XarrayDataTreeItem
        for item in group_items:
            group: xr.DataTree = item.data
            group.orphan()
        if var_items:
            var_names: list[str] = [item.name for item in var_items]
            parent_node.dataset = parent_node.to_dataset().drop_vars(var_names)
        
        # update itemtree
        # note: this will still remove any inherited coord items in the item block
        for child in parent_item.children[row: row + count]:
            child.parent = None
        del parent_item.children[row: row + count]

        self.endRemoveRows()
        
        return True
    
    def removeItems(self, items: list[XarrayDataTreeItem]) -> None:
        if not items:
            return
        
        # discard items that are descendents of other items to be removed
        for item in tuple(items):
            for other_item in items:
                if other_item is item:
                    continue
                if item.has_ancestor(other_item):
                    # item is a descendent of other_item, so removing other_item will automatically remove item too
                    items.remove(item)
                    break
        
        if len(items) == 1:
            item: XarrayDataTreeItem = items[0]
            row: int = item.row
            parent_index: QModelIndex = self.indexFromItem(item.parent)
            self.removeRows(row, 1, parent_index)
            return
        
        # group items into blocks by parent and contiguous rows
        # note: we don't have to separate items by data type
        item_blocks: list[list[XarrayDataTreeItem]] = self._itemBlocks(items, split_data_types=False)
        
        # remove each item block
        # note: blocks are in depth-first order, so remove in reverse order to ensure row indices remain valid after removing each block
        for block in reversed(item_blocks):
            row: int = block[0].row
            count: int = len(block)
            parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            self.removeRows(row, count, parent_index)
        
        # !!! this is not efficient
        if self._highlight_shared_data:
            self.beginResetModel()
            self._updateSharedDataColors()
            self.endResetModel()
    
    def insertRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        """ Defaults to inserting new empty auto-named groups. For anything else, see `insertItems` instead.
        """
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row > num_rows):
            return False
        
        parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)
        
        # can only insert children in a group
        if not parent_item.is_group:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'"Cannot insert items in non-group {parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False

        parent_group: xr.DataTree = parent_item.data

        # new group names
        parent_group_keys: list[str] = list(parent_group.keys())
        new_group_names: list[str] = []
        for _ in range(count):
            name: str = xarray_utils.unique_name('Group', parent_group_keys)
            new_group_names.append(name)
            parent_group_keys.append(name)

        # insertion rows
        first: int = self._insertionRow(parent_item, GROUP, row)
        last: int = first + count - 1

        # final ordered group names after insertion
        pre_insertion_group_names: list[str] = [item.name for item in parent_item.children[:first] if item.data_type == GROUP]
        post_insertion_group_names: list[str] = [item.name for item in parent_item.children[first:] if item.data_type == GROUP]
        final_group_names: list[str] = pre_insertion_group_names + new_group_names + post_insertion_group_names
        
        # insert new empty groups
        try:
            # assign new groups to orphaned copy of parent_group (this does not affect the current datatree)
            new_parent_group = parent_group.assign({name: xr.DataTree() for name in new_group_names})

            # order the groups
            new_parent_group.children = {name: new_parent_group.children[name] for name in final_group_names}
            
            # if all good, then update the datatree and itemtree
            self.beginInsertRows(parent_index, first, last)

            print()
            print('datatree pre insert empty groups:')
            print(self.datatree())
            # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            #     print('\t' * group.level, group.path + f' <{id(group)}>')
            print()

            print()
            print('itemtree pre insert empty groups:')
            print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            print()
                
            # update datatree
            if not parent_group.is_root:
                dt: xr.DataTree = self.datatree()
                dt[parent_group.path] = new_parent_group
            
            # update parent_item
            parent_item.data = new_parent_group

            # add new child group items
            for i, name in enumerate(new_group_names):
                XarrayDataTreeItem(new_parent_group.children[name], data_type=GROUP, parent=parent_item, sibling_index=first + i)
            
            # update subtree data refs
            item: XarrayDataTreeItem
            for item in parent_item.subtree_depth_first():
                if item.is_root:
                    continue
                parent_group: xr.DataTree = item.parent.data
                if item.is_group:
                    item.data = parent_group.children[item.name]
                elif item.is_data_var:
                    item.data = parent_group.data_vars[item.name]
                elif item.is_coord:
                    item.data = parent_group.coords[item.name]

            print()
            print('datatree post insert empty groups:')
            print(self.datatree())
            # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            #     print('\t' * group.level, group.path + f' <{id(group)}>')
            print()

            print()
            print('itemtree post insert empty groups:')
            print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            print()
            
            self.endInsertRows()

            # update inherited coord items in descendents of parent item
            if self.isCoordsVisible() and self.isInheritedCoordsVisible():
                self._updateSubtreeCoordItems(parent_item)
        
        except error:
            # !!! This should never happen
            from warnings import warn
            text = f'"ERROR: Failed to insert new GROUP items in {parent_item.path}" with error: "{error}". This should never happen!'
            warn(text)
            return False
        
        return True
    
    def insertItems(self, name_item_map: dict[str, XarrayDataTreeItem], row: int, parent_item: XarrayDataTreeItem) -> None:
        # print(f'insertItems(items_map={list(items_map)}, parent_item={parent_item.name}, row={row})')
        num_rows: int = len(parent_item.children)
        if row < 0:
            # negative indexing
            row += num_rows
        if (row < 0) or (row > num_rows):
            return False
        
        # can only insert children in a group
        if not parent_item.is_group:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot insert items in non-group "{parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False
        
        # handle conflicts
        name_item_map = self._handleInsertionConflicts(name_item_map, parent_item, orphan_only=True)
        if not name_item_map:
            # no non-conflicting items remaining
            return False
        
        # group items by data type and put groups in reverse tree order
        name_item_maps: list[dict[str, XarrayDataTreeItem]] = []
        dtype: XarrayDataTreeType
        for dtype in reversed(self._data_type_order):
            name_item_map_for_dtype: dict[str, XarrayDataTreeItem] = {name: item for name, item in name_item_map.items() if item.data_type == dtype}
            if name_item_map_for_dtype:
                name_item_maps.append(name_item_map_for_dtype)
        
        # insert item groups
        parent_index: QModelIndex = self.indexFromItem(parent_item)
        parent_group: xr.DataTree = parent_item.data
        name_item_map: dict[str, XarrayDataTreeItem] # this will now refer to each group as opposed to the input map
        for name_item_map in name_item_maps:
            first_item: XarrayDataTreeItem = next(iter(name_item_map.values()))
            dtype: XarrayDataTreeType = first_item.data_type

            # perform insertion in a copy of the parent group or dataset
            # if everything is ok, we'll apply it to the original datatree and itemtree
            name_data_map: dict[str, xr.DataTree | xr.DataArray] = {name: item.data for name, item in name_item_map.items()}
            try:
                if dtype == GROUP:
                    new_parent_group: xr.DataTree = parent_group.assign(name_data_map)
            
                elif dtype == DATA_VAR:
                    new_parent_dataset: xr.Dataset = parent_group.to_dataset().assign(name_data_map)
                
                elif dtype == COORD:
                    new_parent_dataset: xr.Dataset = parent_group.to_dataset().assign_coords(name_data_map)

            except error:
                parent_widget: QWidget = QApplication.focusWidget()
                title = 'Failed Insertion'
                text = f'Failed to insert {dtype.name} items in "{parent_item.path}" with error: {error}'
                QMessageBox.warning(parent_widget, title, text)
                from warnings import warn
                warn(text)
                # still try to insert remaining item maps
                continue

            # if we got here, should be all good. let's update the datatree and itemtree

            # remove items that are being overwritten
            # we just remove the items without touching the underlying datatree data as that will be updated during insertion below
            items_being_overwritten: list[XarrayDataTreeItem] = [item for item in parent_item.children if item.name in name_item_map]
            for item in items_being_overwritten:
                print('overwriting', item.name)
                self.beginRemoveRows(parent_index, item.row, item.row)
                item.orphan()
                self.endRemoveRows()

            # insertion rows
            first: int = self._insertionRow(parent_item, dtype, row)
            last: int = first + len(name_item_map) - 1

            # final ordered dtype names after insertion
            pre_insertion_dtype_names: list[str] = [item.name for item in parent_item.children[:first] if item.data_type == dtype]
            post_insertion_dtype_names: list[str] = [item.name for item in parent_item.children[first:] if item.data_type == dtype]
            final_dtype_names: list[str] = pre_insertion_dtype_names + list(name_item_map) + post_insertion_dtype_names

            # insert items
            self.beginInsertRows(parent_index, first, last)

            print()
            print('datatree pre insert:')
            print(self.datatree())
            # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            #     print('\t' * group.level, group.path + f' <{id(group)}>')
            print()

            print()
            print('itemtree pre insert:')
            print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            print()
            
            if dtype == GROUP:
                # order the groups
                new_parent_group.children = {name: new_parent_group.children[name] for name in final_dtype_names}
                
                # update datatree
                if not parent_group.is_root:
                    dt: xr.DataTree = self.datatree()
                    dt[parent_group.path] = new_parent_group
                    
                # update itemtree
                parent_item.data = new_parent_group
                for i, (name, item) in enumerate(name_item_map.items()):
                    item.data = new_parent_group.children[name]
                    parent_item.insert_child(first + i, item)
            
                # update subtree data refs
                item: XarrayDataTreeItem
                for item in parent_item.subtree_depth_first():
                    if item.is_root:
                        continue
                    parent_group: xr.DataTree = item.parent.data
                    if item.is_group:
                        item.data = parent_group.children[item.name]
                    elif item.is_data_var:
                        item.data = parent_group.data_vars[item.name]
                    elif item.is_coord:
                        item.data = parent_group.coords[item.name]
            
                # reset parent_group reference
                parent_group = new_parent_group
        
            elif dtype == DATA_VAR:
                # order the data_vars
                new_parent_dataset = new_parent_dataset.assign({name: new_parent_dataset.data_vars[name] for name in final_dtype_names})
                
                # update datatree
                parent_group.dataset = new_parent_dataset
                
                # update itemtree
                for i, (name, item) in enumerate(name_item_map.items()):
                    item.data = parent_group.data_vars[name]
                    parent_item.insert_child(first + i, item)
            
            elif dtype == COORD:
                # order the coords
                new_parent_dataset = new_parent_dataset.assign({name: new_parent_dataset.coords[name] for name in final_dtype_names})
                
                # update datatree
                parent_group.dataset = new_parent_dataset
                
                # update itemtree
                for i, (name, item) in enumerate(name_item_map.items()):
                    item.data = parent_group.coords[name]
                    parent_item.insert_child(first + i, item)
            
            self.endInsertRows()

            # for any newly inserted index coords, insert inherited coord items in descendents of parent_item
            if (dtype == COORD) and self.isCoordsVisible() and self.isInheritedCoordsVisible():
                self._updateSubtreeCoordItems(parent_item)

            print()
            print('datatree post insert:')
            print(self.datatree())
            # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            #     print('\t' * group.level, group.path + f' <{id(group)}>')
            print()

            print()
            print('itemtree post insert:')
            print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            print()
        
        # end for name_item_map in name_item_maps:
        
        # !!! this is not efficient
        if self._highlight_shared_data:
            self.beginResetModel()
            self._updateSharedDataColors()
            self.endResetModel()
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        # print(f'moveRows(src_row={src_row}, count={count}, dst_row={dst_row})...')
        if count <= 0:
            return False
        num_src_rows: int = self.rowCount(src_parent_index)
        if (src_row < 0) or (src_row + count > num_src_rows):
            return False
        num_dst_rows: int = self.rowCount(dst_parent_index)
        if (dst_row < 0) or (dst_row > num_dst_rows):
            return False
        
        src_parent_item: XarrayDataTreeItem = self.itemFromIndex(src_parent_index)
        dst_parent_item: XarrayDataTreeItem = self.itemFromIndex(dst_parent_index)

        if src_parent_item is dst_parent_item:
            if src_row <= dst_row <= src_row + count:
                # nothing moved
                return False
        
        # can only move items to a group
        if not dst_parent_item.is_group:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot move items to non-group "{dst_parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False
        
        src_parent_group: xr.DataTree = src_parent_item.data
        dst_parent_group: xr.DataTree = dst_parent_item.data
        
        src_parent_path: str = src_parent_group.path
        dst_parent_path: str = dst_parent_group.path

        src_parent_in_dst_parent_subtree: bool = src_parent_path.startswith(dst_parent_path)
        dst_parent_in_src_parent_subtree: bool = dst_parent_path.startswith(src_parent_path)
        
        # items to move
        name_item_map: dict[str, XarrayDataTreeItem] = {item.name: item for item in src_parent_item.children[src_row: src_row + count]}

        # reorder items within group?
        if src_parent_group is dst_parent_group:
            if src_row <= dst_row <= src_row + count:
                # nothing moved
                return False
            
            first_item: XarrayDataTreeItem = next(iter(name_item_map.values()))
            dtype: XarrayDataTreeType = first_item.data_type

            # move rows
            src_first: int = first_item.row
            src_last: int = src_first + len(name_item_map) - 1
            dst_first: int = self._insertionRow(dst_parent_item, dtype, dst_row)
            if src_first <= dst_first <= src_last + 1:
                # nothing moved
                return False

            # final reordered dtype names
            pre_insertion_dtype_names: list[str] = [item.name for item in dst_parent_item.children[:dst_first] if item.data_type == dtype and item not in name_item_map.values()]
            post_insertion_dtype_names: list[str] = [item.name for item in dst_parent_item.children[dst_first:] if item.data_type == dtype and item not in name_item_map.values()]
            final_dtype_names: list[str] = pre_insertion_dtype_names + list(name_item_map) + post_insertion_dtype_names

            self.beginMoveRows(src_parent_index, src_first, src_last, dst_parent_index, dst_first)

            # print()
            # print('datatree pre reorder:')
            # print(self.datatree())
            # # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            # #     print('\t' * group.level, group.path + f' <{id(group)}>')
            # print()

            # print()
            # print('itemtree pre reorder:')
            # print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            # print()

            # update datatree
            if dtype == GROUP:
                dst_parent_group.children = {name: dst_parent_group.children[name] for name in final_dtype_names}
        
            elif dtype == DATA_VAR:
                dst_parent_dataset: xr.Dataset = dst_parent_group.to_dataset()
                new_dst_parent_dataset = xr.Dataset(
                    data_vars={name: dst_parent_dataset.data_vars[name] for name in final_dtype_names},
                    coords=dst_parent_dataset.coords,
                    attrs=dst_parent_dataset.attrs,
                )
                dst_parent_group.dataset = new_dst_parent_dataset
            
            elif dtype == COORD:
                dst_parent_dataset: xr.Dataset = dst_parent_group.to_dataset()
                new_dst_parent_dataset = xr.Dataset(
                    data_vars=dst_parent_dataset.data_vars,
                    coords={name: dst_parent_dataset.coords[name] for name in final_dtype_names},
                    attrs=dst_parent_dataset.attrs,
                )
                dst_parent_group.dataset = new_dst_parent_dataset
            
            # update itemtree
            item: XarrayDataTreeItem
            for i, item in enumerate(name_item_map.values()):
                offset: int = -1 if item.row < dst_first else 0
                dst_parent_item.children.insert(dst_first + offset, dst_parent_item.children.pop(item.row))

            # update data_var and coord item refs
            if dtype != GROUP:
                child: XarrayDataTreeItem
                for child in dst_parent_item.children:
                    if child.data_type == dtype:
                        if dtype == DATA_VAR:
                            child.data = dst_parent_group.data_vars[child.name]
                        elif dtype == COORD:
                            child.data = dst_parent_group.coords[child.name]

            # print()
            # print('datatree post reorder:')
            # print(self.datatree())
            # # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            # #     print('\t' * group.level, group.path + f' <{id(group)}>')
            # print()

            # print()
            # print('itemtree post reorder:')
            # print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            # print()
            
            self.endMoveRows()
            
            return True
        
        # handle conflicts
        name_item_map = self._handleInsertionConflicts(name_item_map, dst_parent_item)
        if not name_item_map:
            # no non-conflicting items remaining
            return False
        
        # regroup items into blocks (in case conflict split this block)
        name_item_maps: list[dict[str, XarrayDataTreeItem]] = self._itemMapBlocks(name_item_map)

        # insert item blocks
        name_item_map: dict[str, XarrayDataTreeItem] # this will now refer to each block
        for name_item_map in name_item_maps:
            first_item: XarrayDataTreeItem = next(iter(name_item_map.values()))
            dtype: XarrayDataTreeType = first_item.data_type

            # perform move in a copy of the parent groups or datasets
            # if everything is ok, we'll apply it to the original datatree and itemtree
            name_data_map: dict[str, xr.DataTree | xr.DataArray] = {name: item.data for name, item in name_item_map.items()}
            original_names: list[str] = [item.name for item in name_item_map.values()]
            try:
                if dtype == GROUP:
                    new_dst_parent_group: xr.DataTree = dst_parent_group.assign(name_data_map)
                    new_src_parent_group: xr.DataTree = src_parent_group.drop_nodes(original_names)
            
                elif dtype == DATA_VAR:
                    new_dst_parent_dataset: xr.Dataset = dst_parent_group.to_dataset().assign(name_data_map)
                    new_src_parent_dataset: xr.Dataset = src_parent_group.to_dataset().drop_vars(original_names)
                
                elif dtype == COORD:
                    new_dst_parent_dataset: xr.Dataset = dst_parent_group.to_dataset().assign_coords(name_data_map)
                    new_src_parent_dataset: xr.Dataset = src_parent_group.to_dataset().drop_vars(original_names)

            except Exception as error:
                parent_widget: QWidget = QApplication.focusWidget()
                title = 'Failed Insertion'
                text = f'Failed to move {dtype.name} items from "{src_parent_item.path}" to "{dst_parent_item.path}" with error: {error}'
                QMessageBox.warning(parent_widget, title, text)
                from warnings import warn
                warn(text)
                # still try to move remaining item blocks
                continue

            # if we got here, should be all good. let's update the datatree and itemtree

            # remove items that are being overwritten
            # we just remove the items without touching the underlying datatree data as that will be updated during insertion below
            items_being_overwritten: list[XarrayDataTreeItem] = [item for item in dst_parent_item.children if item.name in name_item_map]
            for item in items_being_overwritten:
                self.beginRemoveRows(dst_parent_index, item.row, item.row)
                item.orphan()
                self.endRemoveRows()

            # move rows
            src_first: int = first_item.row
            src_last: int = src_first + len(name_item_map) - 1
            dst_first: int = self._insertionRow(dst_parent_item, dtype, dst_row)

            # final ordered dtype names after insertion
            pre_insertion_dtype_names: list[str] = [item.name for item in dst_parent_item.children[:dst_first] if item.data_type == dtype and item not in name_item_map.values()]
            post_insertion_dtype_names: list[str] = [item.name for item in dst_parent_item.children[dst_first:] if item.data_type == dtype and item not in name_item_map.values()]
            final_dtype_names: list[str] = pre_insertion_dtype_names + list(name_item_map) + post_insertion_dtype_names

            # move item block
            self.beginMoveRows(src_parent_index, src_first, src_last, dst_parent_index, dst_first)

            # print()
            # print('datatree pre move:')
            # print(self.datatree())
            # # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            # #     print('\t' * group.level, group.path + f' <{id(group)}>')
            # print()

            # print()
            # print('itemtree pre move:')
            # print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            # print()
            
            if dtype == GROUP:
                # order the groups
                new_dst_parent_group.children = {name: new_dst_parent_group.children[name] for name in final_dtype_names}
                
                # update datatree
                dt: xr.DataTree = self.datatree()
                if dst_parent_group.is_root:
                    dt = new_dst_parent_group
                elif src_parent_group.is_root:
                    dt = new_src_parent_group
                if src_parent_in_dst_parent_subtree:
                    # update dst_parent and then src_parent
                    if not dst_parent_group.is_root:
                        dt[dst_parent_path] = new_dst_parent_group
                    dt[src_parent_path] = new_src_parent_group
                else:
                    # update src_parent and then dst_parent
                    if not src_parent_group.is_root:
                        dt[src_parent_path] = new_src_parent_group
                    if not dst_parent_group.is_root:
                        dt[dst_parent_path] = new_dst_parent_group
                
                # update itemtree
                dst_parent_item.data = new_dst_parent_group
                src_parent_item.data = new_src_parent_group
                # update moved items
                name: str
                item: XarrayDataTreeItem
                for i, (name, item) in enumerate(name_item_map.items()):
                    item.orphan()
                    item.data = new_dst_parent_group.children[name]
                    dst_parent_item.insert_child(dst_first + i, item)
                # update subtree data refs
                branch_root_items: list[XarrayDataTreeItem] = []
                if src_parent_in_dst_parent_subtree:
                    branch_root_items = [dst_parent_item]
                elif dst_parent_in_src_parent_subtree:
                    branch_root_items = [src_parent_item]
                else:
                    branch_root_items = [dst_parent_item, src_parent_item]
                branch_root_item: XarrayDataTreeItem
                for branch_root_item in branch_root_items:
                    for item in branch_root_item.subtree_depth_first():
                        if item.is_root:
                            continue
                        parent_group: xr.DataTree = item.parent.data
                        if item.is_group:
                            item.data = parent_group.children[item.name]
                        elif item.is_data_var:
                            item.data = parent_group.data_vars[item.name]
                        elif item.is_coord:
                            item.data = parent_group.coords[item.name]
            
                # reset src_parent_group and dst_parent_group references
                src_parent_group = new_src_parent_group
                dst_parent_group = new_dst_parent_group
        
            elif dtype == DATA_VAR:
                # order the data_vars
                new_dst_parent_dataset = new_dst_parent_dataset.assign({name: new_dst_parent_dataset.data_vars[name] for name in final_dtype_names})
                
                # update datatree
                src_parent_group.dataset = new_src_parent_dataset
                dst_parent_group.dataset = new_dst_parent_dataset
                
                # update itemtree
                for i, (name, item) in enumerate(name_item_map.items()):
                    item.orphan()
                    item.data = dst_parent_group.data_vars[name]
                    dst_parent_item.insert_child(dst_first + i, item)
            
            elif dtype == COORD:
                # order the coords
                new_dst_parent_dataset = new_dst_parent_dataset.assign({name: new_dst_parent_dataset.coords[name] for name in final_dtype_names})
                
                # update datatree
                src_parent_group.dataset = new_src_parent_dataset
                dst_parent_group.dataset = new_dst_parent_dataset
                
                # update itemtree
                for i, (name, item) in enumerate(name_item_map.items()):
                    item.orphan()
                    item.data = dst_parent_group.coords[name]
                    dst_parent_item.insert_child(dst_first + i, item)
            
            self.endMoveRows()

            # for any moved coords, update inherited coord items in descendents of src and dst parent items
            if self.isCoordsVisible() and self.isInheritedCoordsVisible():
                if src_parent_in_dst_parent_subtree:
                    self._updateSubtreeCoordItems(dst_parent_item)
                elif dst_parent_in_src_parent_subtree:
                    self._updateSubtreeCoordItems(src_parent_item)
                else:
                    self._updateSubtreeCoordItems(dst_parent_item)
                    self._updateSubtreeCoordItems(src_parent_item)

            # print()
            # print('datatree post move:')
            # print(self.datatree())
            # # for group in xarray_utils.subtree_depth_first_iter(self.datatree()):
            # #     print('\t' * group.level, group.path + f' <{id(group)}>')
            # print()

            # print()
            # print('itemtree post move:')
            # print(self._root_item._tree_repr(lambda item: item.path + f' <{id(item.data)}>'))
            # print()
        
        # end for name_item_map in name_item_maps:

        return True
    
    def moveItems(self, src_items: list[XarrayDataTreeItem], dst_parent_item: XarrayDataTreeItem, dst_row: int = -1) -> None:
        if not src_items or not dst_parent_item:
            return
        
        dst_parent_index: QModelIndex = self.indexFromItem(dst_parent_item)
        
        if len(src_items) == 1:
            src_item: XarrayDataTreeItem = src_items[0]
            src_parent_index: QModelIndex = self.indexFromItem(src_item.parent)
            src_row: int = src_item.row
            self.moveRows(src_parent_index, src_row, 1, dst_parent_index, dst_row)
            return
        
        # group items into blocks by data type, parent, and contiguous rows
        src_item_blocks: list[list[XarrayDataTreeItem]] = self._itemBlocks(src_items)
        
        # move each item block
        # note: blocks are in depth-first order, so move in reverse order to ensure row indices remain valid after moving each block
        for block in reversed(src_item_blocks):
            src_parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            src_row: int = block[0].row
            count: int = len(block)
            self.moveRows(src_parent_index, src_row, count, dst_parent_index, dst_row)
        
        # !!! this is not efficient
        if self._highlight_shared_data:
            self.beginResetModel()
            self._updateSharedDataColors()
            self.endResetModel()
    
    def transferItems(self, src_items: list[XarrayDataTreeItem], dst_model: XarrayDataTreeModel, dst_parent_item: XarrayDataTreeItem, dst_row: int = -1) -> None:
        # print(f'transferItems(src_items={[item.name for item in src_items]}, dst_parent_item={dst_parent_item.name}, dst_row={dst_row})...')
        if dst_model is self:
            self.moveItems(src_items, dst_parent_item, dst_row)
            return
        
        # TODO: transfer items to dst_model
        
        # !!! this is not efficient
        if self._highlight_shared_data:
            self.beginResetModel()
            self._updateSharedDataColors()
            self.endResetModel()

            dst_model.beginResetModel()
            dst_model._updateSharedDataColors()
            dst_model.endResetModel()
    
    def _updateSubtreeCoordItems(self, parent_item: XarrayDataTreeItem) -> None:
        item: XarrayDataTreeItem
        for item in parent_item.subtree_depth_first():
            if not item.is_group:
                continue
            
            index: QModelIndex = self.indexFromItem(item)
            group: xr.DataTree = item.data
            inherited_coord_names: set[str] = group._inherited_coords_set()
            coord_names: list[str] = list(group.coords)
            
            # remove invalid coord items (no need to touch datatree)
            # note: invalid coord items may have a data_type of None after tree manipulation
            coord_items_to_remove: list[XarrayDataTreeItem] = [child for child in item.children if (child.is_coord and child.name not in group.coords) or (child.data_type is None) or (not self.isInheritedCoordsVisible() and child.is_inherited_coord)]
            for item in reversed(coord_items_to_remove):
                self.beginRemoveRows(index, item.row, item.row)
                item.orphan()
                self.endRemoveRows()
            
            if not self.isCoordsVisible():
                continue
            
            # add missing coord items (no need to touch datatree)
            existing_coord_names: list[str] = [child.name for child in item.children if child.is_coord]
            missing_coord_names: list[str] = [name for name in coord_names if (name not in existing_coord_names) and (self.isInheritedCoordsVisible() or name not in inherited_coord_names)]
            if missing_coord_names:
                row_names: list[str] = self._visibleRowNames(group)
                for name in missing_coord_names:
                    inherited_coord_item = XarrayDataTreeItem(group.coords[name])
                    row: int = row_names.index(name)
                    if row == -1:
                        row = len(item.children)
                    self.beginInsertRows(index, row, row)
                    item.insert_child(row, inherited_coord_item)
                    self.endInsertRows()
    
    @staticmethod
    def _itemBlocks(items: list[XarrayDataTreeItem], split_data_types: bool = True) -> list[list[XarrayDataTreeItem]]:
        """ Group items by data type, parent, and contiguous rows.

        Each block can be input to removeRows() or moveRows().
        Blocks are ordered depth-first. Typically you should remove/move blocks in reverse depth-first order to ensure insertion row indices remain valid after handling each block.
        """
        # so we don't modify the input list
        items = items.copy()

        # # order by data type
        # items.sort(key=lambda item: XarrayDataTreeModel._data_type_order.index(item.data_type))

        # order items depth-first so that it is easier to group them into blocks
        items.sort(key=lambda item: item.level)
        items.sort(key=lambda item: item.row)

        # group items into blocks by [data type,] parent, and contiguous rows
        blocks: list[list[XarrayDataTreeItem]] = [[items[0]]]
        for item in items[1:]:
            added_to_block = False
            for block in blocks:
                if (item.parent is block[0].parent) and (not split_data_types or item.data_type == block[0].data_type):
                    if item.row == block[-1].row + 1:
                        block.append(item)
                    else:
                        blocks.append([item])
                    added_to_block = True
                    break
            if not added_to_block:
                blocks.append([item])
        return blocks
    
    @staticmethod
    def _itemMapBlocks(name_item_map: dict[str, XarrayDataTreeItem], split_data_types: bool = True) -> list[dict[str, XarrayDataTreeItem]]:
        names: list[str] = list(name_item_map)
        items: list[XarrayDataTreeItem] = list(name_item_map.values())
        item_blocks: list[list[XarrayDataTreeItem]] = XarrayDataTreeModel._itemBlocks(items)
        name_item_map_blocks: list[dict[str, XarrayDataTreeItem]] = []
        for item_block in item_blocks:
            name_item_map_block: dict[str, XarrayDataTreeItem] = {}
            item: XarrayDataTreeItem
            for item in item_block:
                i = items.index(item)
                name = names[i]
                name_item_map_block[name] = item
            name_item_map_blocks.append(name_item_map_block)
        return name_item_map_blocks
    
    @staticmethod
    def _insertionRow(parent_item: XarrayDataTreeItem, data_type: XarrayDataTreeType, row: int) -> int:

        items_of_dtype: list[XarrayDataTreeItem] = [item for item in parent_item.children if item.data_type == data_type]

        if not items_of_dtype:
            # insert after all items of other data types that come before data_type in the model
            row = 0
            for dtype in XarrayDataTreeModel._data_type_order:
                if dtype == data_type:
                    break
                row += len([item for item in parent_item.children if item.data_type == dtype])
            return row
        elif row > items_of_dtype[-1].row:
            # append after last item of data_type
            return items_of_dtype[-1].row + 1
        elif row <= items_of_dtype[0].row:
            # prepend before first item of data_type
            return items_of_dtype[0].row
        else:
            # insert at row which falls within items of data_type
            return row
    
    @staticmethod
    def _handleInsertionConflicts(name_item_map: dict[str, XarrayDataTreeItem], parent_item: XarrayDataTreeItem, orphan_only: bool = False) -> dict[str, XarrayDataTreeItem]:
        if not parent_item.is_group:
            # cannot insert items into non-group item
            return {}
        
        # so we don't alter the input map
        name_item_map = name_item_map.copy()

        parent_group: xr.DataTree = parent_item.data
        parent_keys: list[str] = list(parent_group.keys())

        # conflicts[name] = conflict message
        # we'll handle name conflicts separately from all other conflicts
        conflicts: dict[str, str] = {}
        name_conflicts: dict[str, str] = {}
        
        name: str
        item: XarrayDataTreeItem
        for name, item in name_item_map.items():
            # only allow insertion of orphaned items
            if orphan_only and item.parent is not None:
                conflicts[name] = f'Cannot insert non-orphan "{item.path}".'
                continue

            # cannot insert item into one of its descendents
            if parent_item.has_ancestor(item):
                conflicts[name] = f'Cannot insert "{item.path}" into its own subtree at "{parent_item.path}".'
                continue

            # inserted objects must align with parent group
            try:
                if isinstance(item.data, xr.DataTree):
                    data = item.data.dataset
                elif isinstance(item.data, xr.DataArray):
                    data = item.data
                # dataset views include inherited coords
                xr.align(parent_group.dataset, data, join='exact')
            except:
                conflicts[name] = f'"{item.path}" is not aligned with "{parent_item.path}".'
                continue
            
            # inserted item names must be valid new keys in parent
            if '/' in name:
                conflicts[name] = f'"{name}" is not a valid DataTree name, which cannot contain "/".'
                continue
            if name in parent_keys:
                name_conflicts[name] = f'"{name}" already exists in "{parent_item.path}".'
                continue

            parent_keys.append(name)
        
        # either abort or skip these conflicts
        if conflicts:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Conflict'
            text = '\n'.join(list(conflicts.values()))
            dlg = ConflictDialog(parent_widget, title, text)
            if dlg.exec() == QDialog.DialogCode.Rejected:
                # abort
                return {}
            for name in conflicts:
                # skip conflicting items
                del name_item_map[name]
        
        # either abort, skip, overwrite, merge, or rename these conflicts
        if name_conflicts:
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Name Conflict'
            text = '\n'.join(list(name_conflicts.values()))
            dlg = NameConflictDialog(parent_widget, title, text)
            dlg._merge_button.setEnabled(False) # TODO
            if dlg.exec() == QDialog.DialogCode.Rejected:
                # abort
                return {}
            action = dlg._action_button_group.checkedButton().text().lower()
            if action == 'overwrite':
                # nothing to do here (this is the default)
                pass
            elif action == 'merge':
                # TODO
                pass
            elif action == 'keep both':
                for existing_name in name_conflicts:
                    new_name: str = xarray_utils.unique_name(existing_name, parent_keys)
                    name_item_map = {new_name if name == existing_name else name: item for name, item in name_item_map.items()}
                    parent_keys.append(new_name)
            elif action == 'skip':
                for name in name_conflicts:
                    del name_item_map[name]
        
        return name_item_map
    
    def _updateSharedDataColors(self) -> None:
        import numpy as np
        dt: xr.DataTree = self.datatree()
        ids: list[int] = []
        for group in xarray_utils.subtree_depth_first_iter(dt):
            for data_var in group.data_vars.values():
                ids.append(id(data_var.data))
            for coord in group.coords.values():
                ids.append(id(coord.data))
        shared_ids = [id_ for id_ in ids if ids.count(id_) > 1]
        cm = cmap.Colormap('viridis')
        colors = cm(np.linspace(0, 1, len(shared_ids)))
        self._shared_data_colormap: dict[int, QColor] = {id_: QColor(*[int(255*c) for c in color[:3]]) for id_, color in zip(shared_ids, colors)}
    
    def mimeTypes(self) -> list[str]:
        """ Return the MIME types supported by this view for drag-and-drop operations.
        """
        return [XarrayDataTreeMimeData.MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> XarrayDataTreeMimeData | None:
        data: AbstractTreeMimeData = super().mimeData(indexes)
        if data is None:
            return
        return XarrayDataTreeMimeData(data.src_model, data.src_items)

    @staticmethod
    def _popupWarningDialog(self, text: str, system_warn: bool = True) -> None:
        focused_widget: QWidget = QApplication.focusWidget()
        QMessageBox.warning(focused_widget, 'Warning', text)
        if system_warn:
            from warnings import warn
            warn(text)


class XarrayDataTreeMimeData(AbstractTreeMimeData):
    """ Custom MIME data class for Xarray DataTree objects.
    """

    MIME_TYPE = 'application/x-xarray-datatree-model'

    def __init__(self, src_model: XarrayDataTreeModel, src_items: list[XarrayDataTreeItem]):
        super().__init__(self, src_model, src_items)

        # Ensure that the MIME type self.MIME_TYPE is set.
        # The actual value of the data here is not important, as we won't use it.
        # Instead, we will use the above attributes to handle drag-and-drop.
        self.setData(self.MIME_TYPE, self.MIME_TYPE.encode('utf-8'))
    
    def hasFormat(self, mime_type: str) -> bool:
        """ Check if the MIME data has the specified format.
        
        Overrides the default method to check for self.MIME_TYPE.
        """
        return mime_type == self.MIME_TYPE or super().hasFormat(mime_type)


class ConflictDialog(QDialog):

    def __init__(self, parent: QWidget, title: str, text: str):
        super().__init__(parent, modal=True)
        
        self.setWindowTitle(title)
        vbox = QVBoxLayout(self)

        self._text_field = QTextEdit(readOnly=True, plainText=text)
        vbox.addWidget(self._text_field)
        vbox.addSpacing(10)

        # self._skip_button = QRadioButton('Skip')
        # self._skip_all_button = QRadioButton('Skip All')
        # self._action_button_group = QButtonGroup()
        # self._action_button_group.addButton(self._skip_button)
        # self._action_button_group.addButton(self._skip_all_button)
        # self._skip_button.setChecked(True)
        # vbox.addWidget(self._skip_button)
        # vbox.addWidget(self._skip_all_button)
        # vbox.addSpacing(10)

        buttons = QDialogButtonBox()
        self._continue_button: QPushButton = buttons.addButton('Skip & Continue', QDialogButtonBox.ButtonRole.AcceptRole)
        self._cancel_button: QPushButton = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._continue_button.setAutoDefault(False)
        self._cancel_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        vbox.addWidget(buttons)


class NameConflictDialog(QDialog):

    def __init__(self, parent: QWidget, title: str, text: str):
        super().__init__(parent, modal=True)
        
        self.setWindowTitle(title)
        vbox = QVBoxLayout(self)

        self._text_field = QTextEdit(readOnly=True, plainText=text)
        vbox.addWidget(self._text_field)
        vbox.addSpacing(10)

        self._overwrite_button = QRadioButton('Overwrite')
        self._merge_button = QRadioButton('Merge')
        self._keep_both_button = QRadioButton('Keep Both')
        self._skip_button = QRadioButton('Skip')
        self._action_button_group = QButtonGroup()
        self._action_button_group.addButton(self._overwrite_button)
        self._action_button_group.addButton(self._merge_button)
        self._action_button_group.addButton(self._keep_both_button)
        self._action_button_group.addButton(self._skip_button)
        vbox.addWidget(self._overwrite_button)
        vbox.addWidget(self._merge_button)
        vbox.addWidget(self._keep_both_button)
        vbox.addWidget(self._skip_button)
        vbox.addSpacing(10)

        self._apply_to_all_checkbox = QCheckBox('Apply to all')
        vbox.addWidget(self._apply_to_all_checkbox)

        buttons = QDialogButtonBox()
        self._continue_button: QPushButton = buttons.addButton('Continue', QDialogButtonBox.ButtonRole.AcceptRole)
        self._cancel_button: QPushButton = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._continue_button.setAutoDefault(False)
        self._cancel_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        vbox.addWidget(buttons)

        # continuing is only valid if an action is selected
        self._continue_button.setEnabled(self._action_button_group.checkedButton() is not None)
        for button in self._action_button_group.buttons():
            button.pressed.connect(lambda: self._continue_button.setEnabled(True))


def test_model():
    app = QApplication()

    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.tutorial.load_dataset('tiny')
    dt['child3/grandchild2'] = xr.DataTree()
    # print(dt)

    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setDatatree(dt)

    view = QTreeView()
    view.setModel(model)
    view.expandAll()
    view.resizeColumnToContents(0)
    view.resize(800, 800)
    view.show()

    # dlg = NameConflictDialog('blah blah')
    # dlg.show()

    app.exec()


if __name__ == '__main__':
    test_model()