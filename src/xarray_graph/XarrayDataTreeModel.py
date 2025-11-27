""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- setData
    - rename coord
- moveRows
    - data_vars
    - coords
    - handle reordering only
    - merge items?
    - for any moved coords, remove inherited coords in descendents of src_parent
    - for any moved data_vars, copy any inherited coords from src_parent that don't already exist in dst_parent to dst_parent node
    - for any moved nodes, copy any inherited coords that don't already exist in dst_parent
- insertItems
- transferItems
"""

from __future__ import annotations
from collections.abc import Iterator
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph import xarray_utils, TreeItem


class XarrayDataTreeItem(TreeItem):
    """ Tree item wrapper for nodes and variables in XarrayDataTreeModel.

    This isn't strictly necessary, but it speeds object access and thus tree UI performance.
    """

    def __init__(self, data: xr.DataTree | xr.DataArray, parent: XarrayDataTreeItem = None, sibling_index: int = -1):
        super().__init__(parent, sibling_index)
        self.data: xr.DataTree | xr.DataArray = data
    
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
    def is_node(self) -> bool:
        return isinstance(self.data, xr.DataTree)
    
    @property
    def is_data_var(self) -> bool:
        return self.parent and isinstance(self.data, xr.DataArray) and self.data.name in self.parent.data.data_vars
    
    @property
    def is_coord(self) -> bool:
        return self.parent and isinstance(self.data, xr.DataArray) and self.data.name in self.parent.data.coords
    
    @property
    def is_index_coord(self) -> bool:
        return self.is_coord and self.data.name in self.parent.data.xindexes
    
    @property
    def is_inherited_coord(self) -> bool:
        return self.is_coord and self.data.name in self.parent.data._inherited_coords_set()


class XarrayDataTreeModel(QAbstractItemModel):
    """ PyQt tree model interface for a Xarray DataTree.
    """

    item_order = ['coords', 'data_vars', 'children']

    def __init__(self, *args, **kwargs):
        datatree: xr.DataTree = kwargs.pop('datatree', xr.DataTree())
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['DataTree', 'Details']

        # parts of datatree to show
        self._is_data_vars_visible: bool = True
        self._is_coords_visible: bool = False
        self._is_inherited_coords_visible: bool = False
        self._is_details_column_visible: bool = False

        # drag-and-drop support for moving tree items within the tree or copying them to other tree models
        self._supportedDropActions: Qt.DropActions = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

        # icons
        self._datatree_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')

        # colors
        self._inherited_coords_color: QColor = QColor(128, 128, 128)

        # setup item tree
        self._root_item = XarrayDataTreeItem(datatree)
        self._updateItemSubtree(self._root_item)
    
    def reset(self) -> None:
        """ Reset the model.
        """
        self.beginResetModel()
        self._updateItemSubtree(self._root_item)
        self.endResetModel()

    def datatree(self) -> xr.DataTree:
        """ Get the model's current datatree.
        """
        return self._root_item.data
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        """ Reset the model to the input datatree.
        """
        self.beginResetModel()
        self._root_item = XarrayDataTreeItem(datatree)
        self._updateItemSubtree(self._root_item)
        self.endResetModel()
    
    def _updateItemSubtree(self, item: XarrayDataTreeItem) -> None:
        if not item.is_node:
            return
        item.children = [] # will repopulate below
        for item_type in self.item_order:
            if item_type == 'data_vars':
                if self.isDataVarsVisible():
                    data_var: xr.DataArray
                    for data_var in item.data.data_vars.values():
                        child_item = XarrayDataTreeItem(data_var, item)
            elif item_type == 'coords':
                if self.isCoordsVisible():
                    coord: xr.DataArray
                    for coord in self._orderedCoords(item.data):
                        child_item = XarrayDataTreeItem(coord, item)
            elif item_type == 'children':
                node: xr.DataTree
                for node in item.data.children.values():
                    child_item = XarrayDataTreeItem(node, item)
                    self._updateItemSubtree(child_item)
    
    def _orderedCoords(self, node: xr.DataTree) -> Iterator[xr.DataArray]:
        if not self.isInheritedCoordsVisible():
            inherited_coord_names: set[str] = node._inherited_coords_set()
        ordered_dims: tuple[str] = tuple(xarray_utils.get_ordered_dims([node]))
        traversed_coord_names: list[str] = []
        dim: str
        for dim in ordered_dims:
            if dim not in node.indexes:
                continue
            if self.isInheritedCoordsVisible() or (dim not in inherited_coord_names):
                yield node.coords[dim]
                traversed_coord_names.append(dim)
        coord: xr.DataArray
        for coord in node.coords.values():
            if coord.name in traversed_coord_names:
                continue
            if self.isInheritedCoordsVisible() or (coord.name not in inherited_coord_names):
                yield coord
    
    def _visibleRowNames(self, node: xr.DataTree) -> list[str]:
        names: list[str] = []
        for item_type in self.item_order:
            if item_type == 'data_vars':
                if self.isDataVarsVisible():
                    names += list(node.data_vars)
            elif item_type == 'coords':
                if self.isCoordsVisible():
                    names += [coord.name for coord in self._orderedCoords(node)]
            elif item_type == 'children':
                names += list(node.children)
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
    
    def itemFromIndex(self, index: QModelIndex) -> XarrayDataTreeItem:
        if not index.isValid():
            return self._root_item
        item: XarrayDataTreeItem = index.internalPointer()
        return item
    
    def indexFromItem(self, item: XarrayDataTreeItem, column: int = 0) -> QModelIndex:
        if (item is self._root_item) or (item.parent is None):
            return QModelIndex()
        row: int = item.parent.children.index(item)
        return self.createIndex(row, column, item)
    
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)
        if parent_item is None:
            return 0
        return len(parent_item.children)
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        if self.isDetailsColumnVisible():
            return 2
        return 1

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        item: XarrayDataTreeItem = self.itemFromIndex(index)
        parent_item: XarrayDataTreeItem = item.parent
        if (parent_item is None) or (parent_item is self._root_item):
            return QModelIndex()
        return self.indexFromItem(parent_item)

    def index(self, row: int, column: int, parent_index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent_index):
            return QModelIndex()
        if parent_index.isValid() and parent_index.column() != 0:
            return QModelIndex()
        try:
            parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)
            item: XarrayDataTreeItem = parent_item.children[row]
            return self.createIndex(row, column, item)
        except IndexError:
            return QModelIndex()

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
            if item.is_node:
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
                if item.is_node:
                    sizes_str = ', '.join([f'{dim}: {size}' for dim, size in item.data.dataset.sizes.items()])
                    return f'({sizes_str})'
                elif item.is_data_var:
                    rep = str(item.parent.data.dataset)
                    i = rep.find('Data variables:')
                    i = rep.find(f' {item.data.name} ', i)  # find var
                    i = rep.find('(', i)  # skip var name
                    j = rep.find('\n', i)
                    return rep[i:j] if j > 0 else rep[i:]
                elif item.is_coord:
                    rep = str(item.parent.data.dataset)
                    i = rep.find('Coordinates:')
                    i = rep.find(f' {item.data.name} ', i)  # find coord
                    i = rep.find('(', i)  # skip coord name
                    j = rep.find('\n', i)
                    return rep[i:j] if j > 0 else rep[i:]
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: XarrayDataTreeItem = self.itemFromIndex(index)
                if item.is_node:
                    return self._datatree_icon
                elif item.is_data_var:
                    return self._data_var_icon
                elif item.is_coord:
                    return self._coord_icon
        elif role == Qt.ItemDataRole.TextColorRole:
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            if item.is_inherited_coord:
                return self._inherited_coords_color

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        """ This amounts to just renaming DataTree nodes, data_vars, and coords.
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
                msg = f'"{new_name}" is not a valid DataTree key. Must be a non-empty string without any path separators "/".'
                QMessageBox.warning(parent=QApplication.focusWidget(), title='Invalid Name', text=msg)
                return False
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            old_name = item.data.name
            if new_name == old_name:
                # nothing to do
                return False
            parent_node: xr.DataTree = item.parent.data
            parent_keys: list[str] = list(parent_node.keys())
            if new_name in parent_keys:
                msg = f'"{new_name}" already exists in parent DataTree.'
                QMessageBox.warning(parent=QApplication.focusWidget(), title='Existing Name', text=msg)
                return False
            if item.is_node:
                parent_node.children = {name if name != old_name else new_name: child for name, child in parent_node.children.items()}
                self.dataChanged.emit(index, index)
                return True
            elif item.is_data_var:
                ds: xr.Dataset = parent_node.to_dataset()
                ds.data_vars = {name if name != old_name else new_name: data_var for name, data_var in ds.data_vars.items}
                parent_node.dataset = ds
                self.dataChanged.emit(index, index)
                return True
            elif item.is_coord:
                pass # TODO: rename coord and also dimension if coord is an index coord
        return False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        """ Get data from `rowLabels` or `columnLabels`.
        """
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = self.columnLabels()
            elif orientation == Qt.Orientation.Vertical:
                labels = self.rowLabels()
            if section < len(labels):
                label = labels[section]
                if label is not None:
                    return label
            return section

    def setHeaderData(self, section: int, orientation: Qt.Orientation, value, role: int) -> bool:
        """ Set data in `rowLabels` or `columnLabels`.
        """
        if role == Qt.ItemDataRole.EditRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = self.columnLabels()
            elif orientation == Qt.Orientation.Vertical:
                labels = self.rowLabels()
            if section < len(labels):
                labels[section] = value
            else:
                labels += [None] * (section - len(labels)) + [value]
            if orientation == Qt.Orientation.Horizontal:
                self.setColumnLabels(labels)
            elif orientation == Qt.Orientation.Vertical:
                self.setRowLabels(labels)
            self.headerDataChanged.emit(orientation, section, section)
            return True
        return False
    
    def rowLabels(self) -> list:
        return self._row_labels
    
    def setRowLabels(self, labels: list) -> None:
        old_labels = self._row_labels
        n_overlap = min(len(labels), len(old_labels))
        first_change = 0
        while (first_change < n_overlap) and (labels[first_change] == old_labels[first_change]):
            first_change += 1
        last_change = max(len(labels), len(old_labels)) - 1
        while (last_change < n_overlap) and (labels[last_change] == old_labels[last_change]):
            last_change -= 1
        self._row_labels = labels
        if first_change <= last_change: 
            self.headerDataChanged.emit(Qt.Orientation.Vertical, first_change, last_change)
    
    def columnLabels(self) -> list | None:
        return self._column_labels
    
    def setColumnLabels(self, labels: list | None) -> None:
        old_labels = self._column_labels
        n_overlap = min(len(labels), len(old_labels))
        first_change = 0
        while (first_change < n_overlap) and (labels[first_change] == old_labels[first_change]):
            first_change += 1
        last_change = max(len(labels), len(old_labels)) - 1
        while (last_change < n_overlap) and (labels[last_change] == old_labels[last_change]):
            last_change -= 1
        self._column_labels = labels
        if first_change <= last_change: 
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, first_change, last_change)
    
    def depth(self) -> int:
        """ Maximum depth of root's subtree.
        """
        dt: xr.DataTree = self.datatree()
        return dt.depth - dt.level
    
    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        if count <= 0:
            return False
        num_rows: int = self.rowCount(parent_index)
        if row < 0:
            # negative indexing
            row += num_rows
        if (row < 0) or (row + count > num_rows):
            return False
        
        parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)
        items: list[XarrayDataTreeItem] = parent_item.children[row: row + count]
        node_items: list[XarrayDataTreeItem] = [item for item in items if item.is_node]
        data_var_items: list[XarrayDataTreeItem] = [item for item in items if item.is_data_var]
        coord_items: list[XarrayDataTreeItem] = [item for item in items if item.is_coord]
        var_items: list[XarrayDataTreeItem] = data_var_items + coord_items

        parent_node: xr.DataTree = parent_item.data
        
        # remove inherited coords in descendents
        is_removing_inherited_coords_in_descendents = getattr(self, '_is_removing_inherited_coords_in_descendents', False)
        if not is_removing_inherited_coords_in_descendents and coord_items and self.isInheritedCoordsVisible():
            self._is_removing_inherited_coords_in_descendents = True
            coord_names = [item.name for item in coord_items]
            for node_item in parent_item.subtree_reverse_depth_first():
                if node_item is parent_item or not node_item.is_node:
                    continue
                node: xr.DataTree = node_item.data
                inherited_coord_names = node._inherited_coords_set()
                inherited_coord_names_to_remove = [name for name in inherited_coord_names if name in coord_names]
                if inherited_coord_names_to_remove:
                    coord_items_to_remove: list[XarrayDataTreeItem] = [child for child in node_item.children if child.is_inherited_coord and child.name in inherited_coord_names_to_remove]
                    self.removeItems(coord_items_to_remove)
            self._is_removing_inherited_coords_in_descendents = False
        
        self.beginRemoveRows(parent_index, row, row + count - 1)
        if node_items:
            node_names = [item.name for item in node_items]
            parent_node.children = {name: node for name, node in parent_node.children.items() if name not in node_names}
        if var_items:
            var_names = [item.name for item in var_items]
            parent_node.dataset = parent_node.to_dataset().drop_vars(var_names)
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
        # blocks are in reverse depth-first order to ensure row indices remain valid after removing each block
        item_blocks: list[list[XarrayDataTreeItem]] = self._itemBlocks(items)
        
        # remove each item block
        # blocks are in reverse depth-first order to ensure row indices remain valid after removing each block
        for block in item_blocks:
            row: int = block[0].row
            count: int = len(block)
            parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            self.removeRows(row, count, parent_index)
    
    def insertItems(self, items: list[XarrayDataTreeItem], parent_item: XarrayDataTreeItem, row: int = -1) -> None:
        pass # TODO
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        print(f'moveRows(src_row={src_row}, count={count}, dst_row={dst_row})...')
        if count <= 0:
            return False
        num_src_rows: int = self.rowCount(src_parent_index)
        if src_row < 0:
            # negative indexing
            src_row += num_src_rows
        if (src_row < 0) or (src_row + count > num_src_rows):
            return False
        num_dst_rows: int = self.rowCount(dst_parent_index)
        if dst_row < 0:
            # negative indexing
            dst_row += num_dst_rows
        if (dst_row < 0) or (dst_row > num_dst_rows):
            return False
        
        src_parent_item: XarrayDataTreeItem = self.itemFromIndex(src_parent_index)
        dst_parent_item: XarrayDataTreeItem = self.itemFromIndex(dst_parent_index)

        src_parent_node: xr.DataTree = src_parent_item.data
        dst_parent_node: xr.DataTree = dst_parent_item.data

        if src_parent_node is dst_parent_node:
            # TODO: reorder child items
            return True

        src_parent_dataset: xr.Dataset = src_parent_node.to_dataset(inherit=True)
        dst_parent_dataset: xr.Dataset = dst_parent_node.to_dataset(inherit=True)

        # only allow move if src and dst parent nodes align
        try:
            xr.align(src_parent_dataset, dst_parent_dataset, join='exact')
        except:
            msg = f'Cannot move items from {src_parent_item.path} to non-aligned {dst_parent_item.path}.'
            QMessageBox.warning(parent=QApplication.focusWidget(), title='Non-Aligned DataTrees', text=msg)
            return False
        
        src_items_map: dict[str, XarrayDataTreeItem] = {item.name: item for item in src_parent_item.children[src_row: src_row + count]}
            
        # handle name conflicts
        abort = False
        name_conflict_action = getattr(self, '_name_conflict_action', 'ask')
        src_keys = list(src_items_map)
        dst_keys: list[str] = list(dst_parent_node.keys())
        dst_keys_to_be_overwritten: list[str] = []
        dst_keys_to_be_merged: list[str] = []
        src_key_renames = {}
        src_keys_to_be_skipped: list[str] = []
        for src_key in src_keys:
            if src_key not in dst_keys:
                dst_keys.append(src_key)
                continue
            
            if name_conflict_action == 'ask':
                msg = f'"{src_key}" already exists in destination DataTree.'
                dlg = NameConflictDialog(msg, parent=QApplication.focusWidget())
                dlg._merge_button.setEnabled(False) # TODO
                if dlg.exec() == QDialog.DialogCode.Rejected:
                    abort = True
                    break
                this_name_conflict_action = dlg._action_button_group.checkedButton().text().lower()
                apply_to_all_name_conflicts = dlg._apply_to_all_checkbox.isChecked()
                if apply_to_all_name_conflicts:
                    name_conflict_action = this_name_conflict_action
            else:
                this_name_conflict_action = name_conflict_action.lower()
            
            if this_name_conflict_action == 'overwrite':
                dst_keys_to_be_overwritten.append(src_key)
            elif this_name_conflict_action == 'merge':
                dst_keys_to_be_merged.append(src_key)
            elif this_name_conflict_action == 'keep both':
                new_key = xarray_utils.unique_name(src_key, dst_keys)
                src_key_renames[src_key] = new_key
                dst_keys.append(new_key)
            elif this_name_conflict_action == 'skip':
                src_keys_to_be_skipped.append(src_key)
        
        if abort:
            return False
        
        for src_key in src_keys_to_be_skipped:
            src_items_map.pop(src_key)
        
        if src_key_renames:
            src_items_map = {src_key_renames.get(name, name): item for name, item in src_items_map.items()}
        
        dst_items_map: dict[str, XarrayDataTreeItem] = {item.name: item for item in dst_parent_item.children}

        for dst_key in dst_keys_to_be_overwritten:
            if dst_key in dst_items_map:
                # remove the destination item to be overwritten without touching the underlying datatree which will be overwritten when assigning src items during move
                dst_item: XarrayDataTreeItem = dst_items_map[dst_key]
                if dst_item.row < dst_row:
                    dst_row -= 1
                dst_item.parent.children.remove(dst_item)
                dst_item.parent = None
                dst_items_map.pop(dst_key)

        for dst_key in dst_keys_to_be_merged:
            pass # TODO
        
        # move data_vars, coords, and nodes separately as their true destination row may differ from dst_row
        src_data_var_items_map: dict[str, XarrayDataTreeItem] = {name: item for name, item in src_items_map.items() if item.is_data_var}
        src_coord_items_map: dict[str, XarrayDataTreeItem] = {name: item for name, item in src_items_map.items() if item.is_coord}
        src_node_items_map: dict[str, XarrayDataTreeItem] = {name: item for name, item in src_items_map.items() if item.is_node}

        dst_data_var_items_map: dict[str, XarrayDataTreeItem] = {name: item for name, item in dst_items_map.items() if item.is_data_var}
        dst_coord_items_map: dict[str, XarrayDataTreeItem] = {name: item for name, item in dst_items_map.items() if item.is_coord}
        dst_node_items_map: dict[str, XarrayDataTreeItem] = {name: item for name, item in dst_items_map.items() if item.is_node}

        # Move item types in reverse order of their appearance in the item tree to ensure that dst_row remains valid after each move.
        src_item_maps: list[dict[str, XarrayDataTreeItem]] = []
        dst_item_maps: list[dict[str, XarrayDataTreeItem]] = []
        for item_type in self.item_order:
            if item_type == 'data_vars':
                src_item_maps.append(src_data_var_items_map)
                dst_item_maps.append(dst_data_var_items_map)
            elif item_type == 'coords':
                src_item_maps.append(src_coord_items_map)
                dst_item_maps.append(dst_coord_items_map)
            elif item_type == 'children':
                src_item_maps.append(src_node_items_map)
                dst_item_maps.append(dst_node_items_map)
        src_item_map: dict[str, XarrayDataTreeItem]
        for src_item_map in reversed(src_item_maps):
            if not src_item_map:
                continue
            # Rechunk items into contiguous blocks. This could be needed if, for example, an item was skipped.
            names: list[str] = list(src_item_map)
            items: list[XarrayDataTreeItem] = list(src_item_map.values())
            item_blocks: list[list[XarrayDataTreeItem]] = self._itemBlocks(items)
            if len(item_blocks) == 1:
                src_item_block_maps: list[dict[str, XarrayDataTreeItem]] = [src_node_items_map]
            else:
                src_item_block_maps: list[dict[str, XarrayDataTreeItem]] = []
                for block in item_blocks:
                    src_item_block_map: dict[str, XarrayDataTreeItem] = {}
                    for item in block:
                        i: int = items.index(item)
                        name = names[i]
                        src_item_block_map[name] = item
                    src_item_block_maps.append(src_item_block_map)
            
            # move each block one at a time
            for src_item_block_map in src_item_block_maps:
                src_names: list[str] = list(src_item_block_map)
                src_items: list[XarrayDataTreeItem] = list(src_item_block_map.values())
                src_first_row: int = src_items[0].row
                src_last_row: int = src_items[-1].row
                
                # determine destination row location for this block
                if src_items[0].is_node:
                    dst_like_names: list[str] = list(dst_node_items_map)
                    dst_like_items: list[XarrayDataTreeItem] = list(dst_node_items_map.values())
                elif src_items[0].is_data_var:
                    dst_like_names: list[str] = list(dst_data_var_items_map)
                    dst_like_items: list[XarrayDataTreeItem] = list(dst_data_var_items_map.values())
                elif src_items[0].is_coord:
                    dst_like_names: list[str] = list(dst_coord_items_map)
                    dst_like_items: list[XarrayDataTreeItem] = list(dst_coord_items_map.values())
                
                if not dst_like_items:
                    if src_items[0].is_node:
                        i: int = self.item_order.index('children')
                    elif src_items[0].is_data_var:
                        i: int = self.item_order.index('data_vars')
                    elif src_items[0].is_coord:
                        i: int = self.item_order.index('coords')
                    if i == 0:
                        dst_row_: int = 0
                    else:
                        dst_row_: int = 0
                        for j in range(i):
                            dst_row_ += len(dst_item_maps[j])
                    final_dst_like_names = src_names
                elif dst_row > dst_like_items[-1].row:
                    # append items
                    dst_row_: int = dst_like_items[-1].row + 1
                    final_dst_like_names = dst_like_names + src_names
                elif dst_row <= dst_like_items[0].row:
                    # prepend items
                    dst_row_: int = dst_like_items[0].row
                    final_dst_like_names = src_names + dst_like_names
                else:
                    # insert items
                    dst_row_: int = dst_row
                    i: int = dst_row - dst_like_items[0].row
                    final_dst_like_names = dst_like_names[:i] + src_names + dst_like_names[i:]
                
                # move block
                self.beginMoveRows(src_parent_index, src_first_row, src_last_row, dst_parent_index, dst_row)
                if src_items[0].is_node:
                    # move nodes...
                    src_nodes_map: dict[str, xr.DataTree] = {item.name: item.data for item in src_items}
                    # remove src nodes from datatree
                    for node in src_nodes_map.values():
                        node.orphan()
                    # insert src nodes in dst_parent_node (note that this orphans dst_parent_node)
                    dst_parent_node_path: str = dst_parent_node.path
                    dst_parent_node = dst_parent_node.assign(src_nodes_map) # this orphans dst_parent_node
                    dst_parent_node.children = {name: dst_parent_node.children[name] for name in final_dst_like_names} # ordered
                    # reattach dst_parent_node to datatree (not needed if dst_parent is the datatree root)
                    if dst_parent_node_path != '/':
                        dt: xr.DataTree = self.datatree()
                        dt[dst_parent_node_path] = dst_parent_node
                        dst_parent_node = dt[dst_parent_node_path]
                    # relink item tree to new dst_parent_node
                    dst_parent_item.data = dst_parent_node
                    # remove src items from src parent and insert dst in item tree
                    for i, name in enumerate(src_names):
                        src_item = src_item_block_map[name]
                        src_item.orphan()
                        dst_parent_item.insert_child(dst_row_ + i, src_item)
                elif src_items[0].is_data_var:
                    # move data_vars...
                    pass # TODO
                if src_items[0].is_coord:
                    # move coords...
                    pass # TODO
                self.endMoveRows()

        return True
    
    def moveItems(self, src_items: list[XarrayDataTreeItem], dst_parent_item: XarrayDataTreeItem, dst_row: int = -1) -> None:
        print(f'moveItems(src_items={[item.name for item in src_items]}, dst_parent_item={dst_parent_item.name}, dst_row={dst_row})...')
        if not src_items or not dst_parent_item:
            return
        
        dst_parent_index: QModelIndex = self.indexFromItem(dst_parent_item)
        
        if len(src_items) == 1:
            src_item: XarrayDataTreeItem = src_items[0]
            src_parent_index: QModelIndex = self.indexFromItem(src_item.parent)
            src_row: int = src_item.row
            self.moveRows(src_parent_index, src_row, 1, dst_parent_index, dst_row)
            return
        
        # group items into blocks by parent and contiguous rows
        # blocks are in reverse depth-first order to ensure row indices remain valid after moving each block
        src_item_blocks: list[list[XarrayDataTreeItem]] = self._itemBlocks(src_items)
        
        # move each item block
        # blocks are in reverse depth-first order to ensure row indices remain valid after moving each block
        for block in src_item_blocks:
            src_parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            src_row: int = block[0].row
            count: int = len(block)
            self.moveRows(src_parent_index, src_row, count, dst_parent_index, dst_row)
    
    def transferItems(self, src_items: list[XarrayDataTreeItem], dst_model: XarrayDataTreeModel, dst_parent_item: XarrayDataTreeItem, dst_row: int = -1) -> None:
        print(f'transferItems(src_items={[item.name for item in src_items]}, dst_parent_item={dst_parent_item.name}, dst_row={dst_row})...')
        if dst_model is self:
            self.moveItems(src_items, dst_parent_item, dst_row)
            return
        
        # TODO: transfer items to dst_model
    
    @staticmethod
    def _itemBlocks(items: list[XarrayDataTreeItem]) -> list[list[XarrayDataTreeItem]]:
        """ Group items into blocks by parent and contiguous rows.

        Each block can be input to removeRows() or moveRows().
        """
        # so we don't modify the input list
        items = items.copy()

        # order items depth-first so that it is easier to group them into blocks
        items.sort(key=lambda item: item.level)
        items.sort(key=lambda item: item.row)

        # group items into blocks by parent and contiguous rows
        blocks: list[list[XarrayDataTreeItem]] = [[items[0]]]
        for item in items[1:]:
            added_to_block = False
            for block in blocks:
                if item.parent is block[0].parent:
                    if item.row == block[-1].row + 1:
                        block.append(item)
                    else:
                        blocks.append([item])
                    added_to_block = True
                    break
            if not added_to_block:
                blocks.append([item])
        
        # return blocks in reverse depth-first order to ensure row indices remain valid when removing or moving blocks sequentially
        return list(reversed(blocks))
    
    def supportedDropActions(self) -> Qt.DropActions:
        return self._supportedDropActions
    
    def setSupportedDropActions(self, actions: Qt.DropActions) -> None:
        self._supportedDropActions = actions

    def mimeTypes(self) -> list[str]:
        """ Return the MIME types supported by this view for drag-and-drop operations.
        """
        return [XarrayDataTreeMimeData.MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> XarrayDataTreeMimeData | None:
        if not indexes:
            return
        if self.datatree() is None:
            return
        items: list[XarrayDataTreeItem] = [self.itemFromIndex(index) for index in indexes]
        if not items:
            return
        return XarrayDataTreeMimeData(self, items)

    def dropMimeData(self, data: XarrayDataTreeMimeData, action: Qt.DropAction, row: int, column: int, parent_index: QModelIndex) -> bool:
        print('dropMimeData...')
        if not isinstance(data, XarrayDataTreeMimeData):
            return False
        
        src_model: XarrayDataTreeModel = data.src_model
        src_items: list[XarrayDataTreeItem] = data.src_items
        dst_model: XarrayDataTreeModel = data.dst_model
        dst_parent_item: XarrayDataTreeItem = data.dst_parent_item
        dst_row: int = data.dst_row
        if dst_model is not self:
            # sanity check
            return False

        if action == Qt.DropAction.MoveAction:
            src_model.transferItems(src_items, dst_model, dst_parent_item, dst_row)
        # elif action == Qt.DropAction.CopyAction:
        #     pass # TODO

        # !? If we return True, the model will attempt to remove rows.
        # As we already completely handled the drop action above, this will corrupt our model, so return False.
        return False
    
    def _popupWarningDialog(self, text: str, system_warn: bool = True) -> None:
        focused_widget: QWidget = QApplication.focusWidget()
        QMessageBox.warning(focused_widget, 'Warning', text)
        if system_warn:
            from warnings import warn
            warn(text)


class XarrayDataTreeMimeData(QMimeData):
    """ Custom MIME data class for Xarray DataTree objects.

    This class allows storing a reference to an XarrayDataTreeModel object in the MIME data.
    It can be used to transfer DataTree or DataArray items within and between XarrayDataTreeModels in the same program/process.

    Note:
    This approach probably won't work if you need to pass items between XarrayDataTreeModels in separate programs/processes.
    If you really need to do this, you need to somehow serialize the datatree or items thereof (maybe with pickle), pass the serialized bytes in the drag MIME data, then deserialize back to datatree items on drop.
    """

    MIME_TYPE = 'application/x-xarray-datatree-model'

    def __init__(self, src_model: XarrayDataTreeModel, src_items: list[XarrayDataTreeItem]):
        QMimeData.__init__(self)

        # these define the datatree items being dragged
        self.src_model: XarrayDataTreeModel = src_model
        self.src_items: list[XarrayDataTreeItem] = src_items

        # these define where they are being dragged to (set in drop event)
        self.dst_model: XarrayDataTreeModel = None
        self.dst_parent_item: XarrayDataTreeItem = None
        self.dst_row: int = -1

        # Ensure that the MIME type self.MIME_TYPE is set.
        # The actual value of the data here is not important, as we won't use it.
        # Instead, we will use the above attributes to handle drag-and-drop.
        self.setData(self.MIME_TYPE, self.MIME_TYPE.encode('utf-8'))
    
    def hasFormat(self, mime_type: str) -> bool:
        """ Check if the MIME data has the specified format.
        
        Overrides the default method to check for self.MIME_TYPE.
        """
        return mime_type == self.MIME_TYPE or super().hasFormat(mime_type)


# class AbortOrSkipDialog(QDialog):

#     def __init__(self, msg: str, parent: QWidget = None, **kwargs):
#         if parent is None:
#             parent = QApplication.focusWidget()
#         if 'modal' not in kwargs:
#             kwargs['modal'] = True
#         super().__init__(parent, **kwargs)
#         self.setWindowTitle('Name Conflict')
#         vbox = QVBoxLayout(self)
#         vbox.addWidget(QLabel(msg))


class NameConflictDialog(QDialog):

    def __init__(self, msg: str, *args, **kwargs):
        if (len(args) == 0 or not isinstance(args[0], QWidget)) and ('parent' not in kwargs):
            kwargs['parent'] = QApplication.focusWidget()
        if 'modal' not in kwargs:
            kwargs['modal'] = True
        super().__init__(*args, **kwargs)
        self.setWindowTitle('Name Conflict')
        vbox = QVBoxLayout(self)
        vbox.addWidget(QLabel(msg))

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

    app = QApplication()
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