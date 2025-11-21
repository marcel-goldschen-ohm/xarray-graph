""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- moveRows
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

    def __init__(self, data: xr.DataTree | xr.DataArray, parent: XarrayDataTreeItem = None):
        super().__init__(parent)
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
        item.children = []
        if self.isDataVarsVisible():
            data_var: xr.DataArray
            for data_var in item.data.data_vars.values():
                child_item = XarrayDataTreeItem(data_var, item)
                item.children.append(child_item)
        if self.isCoordsVisible():
            coord: xr.DataArray
            for coord in self._orderedCoords(item.data):
                child_item = XarrayDataTreeItem(coord, item)
                item.children.append(child_item)
        node: xr.DataTree
        for node in item.data.children.values():
            child_item = XarrayDataTreeItem(node, item)
            item.children.append(child_item)
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
        for coord in node.coords.values():
            if coord.name in traversed_coord_names:
                continue
            if self.isInheritedCoordsVisible() or (coord.name not in inherited_coord_names):
                yield coord
    
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
                self._popupWarningDialog(msg)
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
                self._popupWarningDialog(msg)
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
                pass # TODO
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
        
        # remove item blocks in reverse depth-first order to ensure row indices remain valid after each removal
        for block in reversed(blocks):
            row: int = block[0].row
            count: int = len(block)
            parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            self.removeRows(row, count, parent_index)
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        print('moveRows...')
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
        
        print(src_row, count, dst_row)
        
        src_parent_item: XarrayDataTreeItem = self.itemFromIndex(src_parent_index)
        src_items: list[XarrayDataTreeItem] = src_parent_item.children[src_row: src_row + count]
        src_node_items: list[XarrayDataTreeItem] = [item for item in src_items if item.is_node]
        src_data_var_items: list[XarrayDataTreeItem] = [item for item in src_items if item.is_data_var]
        src_coord_items: list[XarrayDataTreeItem] = [item for item in src_items if item.is_coord]

        dst_parent_item: XarrayDataTreeItem = self.itemFromIndex(dst_parent_index)
        dst_items: list[XarrayDataTreeItem] = dst_parent_item.children.copy()
        dst_node_items: list[XarrayDataTreeItem] = [item for item in dst_items if item.is_node]
        dst_data_var_items: list[XarrayDataTreeItem] = [item for item in dst_items if item.is_data_var]
        dst_coord_items: list[XarrayDataTreeItem] = [item for item in dst_items if item.is_coord]

        src_parent_node: xr.DataTree = src_parent_item.data
        dst_parent_node: xr.DataTree = dst_parent_item.data

        # TODO: handle move conflicts

        # move nodes
        if src_node_items:
            src_row_: int = src_node_items[0].row
            count_: int = len(src_node_items)
            dst_node_names = list(dst_parent_node.children)
            if not dst_node_items or dst_row > dst_node_items[-1].row:
                # append nodes
                dst_row_: int = len(dst_parent_item.children)
                dst_node_row: int = len(dst_node_items)
                dst_pre_nodes = {}
                dst_post_nodes = dst_parent_node.children
            elif dst_row <= dst_node_items[0].row:
                # prepend nodes
                dst_row_: int = dst_node_items[0].row
                dst_node_row: int = 0
                dst_pre_nodes = dst_parent_node.children
                dst_post_nodes = {}
            else:
                dst_row_: int = dst_row
                dst_node_row: int = dst_row - dst_node_items[0].row
                dst_pre_nodes = {name: dst_parent_node.children[name] for name in dst_node_names[:dst_node_row]}
                dst_post_nodes = {name: dst_parent_node.children[name] for name in dst_node_names[dst_node_row:]}
            self.beginMoveRows(src_parent_index, src_row_, src_row_ + count_ - 1, dst_parent_index, dst_row_)
            for item in src_node_items:
                item.data = item.data.orphan()
                item.parent = dst_parent_item
            dst_parent_node.children = dst_pre_nodes | {item.name: item.data for item in src_node_items} | dst_post_nodes
            dst_parent_item.children = dst_parent_item.children[:dst_row_] + src_node_items + dst_parent_item.children[dst_row_:]
            del src_parent_item.children[src_row_: src_row_ + count_]
            self.endMoveRows()

        # move data_vars
        if src_data_var_items:
            pass # TODO

        # move coords
        if src_coord_items:
            pass # TODO
        
        return True
    
    def moveItems(self, src_items: list[XarrayDataTreeItem], dst_parent_item: XarrayDataTreeItem, dst_row: int = -1) -> None:
        print('moveItems...')
        if not src_items or not dst_parent_item:
            return
        
        dst_parent_index: QModelIndex = self.indexFromItem(dst_parent_item)
        
        if len(src_items) == 1:
            src_item: XarrayDataTreeItem = src_items[0]
            src_parent_index: QModelIndex = self.indexFromItem(src_item.parent)
            src_row: int = src_item.row
            self.moveRows(src_parent_index, src_row, 1, dst_parent_index, dst_row)
            return
        
        # order items depth-first so that it is easier to group them into blocks
        src_items.sort(key=lambda item: item.level)
        src_items.sort(key=lambda item: item.row)

        # group items into blocks by parent and contiguous rows
        blocks: list[list[XarrayDataTreeItem]] = [[src_items[0]]]
        for item in src_items[1:]:
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
        
        # move item blocks in reverse depth-first order to ensure row indices remain valid after each move
        for block in reversed(blocks):
            src_parent_index: QModelIndex = self.indexFromItem(block[0].parent)
            src_row: int = block[0].row
            count: int = len(block)
            self.moveRows(src_parent_index, src_row, count, dst_parent_index, dst_row)
    
    def transferItems(self, src_items: list[XarrayDataTreeItem], dst_model: XarrayDataTreeModel, dst_parent_item: XarrayDataTreeItem, dst_row: int = -1) -> None:
        print('transferItems...')
        if dst_model is self:
            self.moveItems(src_items, dst_parent_item, dst_row)
            return
        
        # TODO: transfer items to dst_model
    
    # def movePaths(self, src_model: XarrayDataTreeModel, src_paths: list[str], dst_model: XarrayDataTreeModel, dst_parent_path: str, dst_row: int, name_conflict: str = 'ask', update_model: bool = True) -> None:
    #     """ Move items between trees by their path.
    #     """
    #     print('movePaths...')
    #     src_datatree: xr.DataTree = src_model.datatree()
    #     dst_datatree: xr.DataTree = dst_model.datatree()
    #     dst_parent_node: xr.DataTree = dst_datatree[dst_parent_path]

    #     # group paths by their parent node from deepest to shallowest so that moving/removing them in order does not change the paths of the remaining groups
    #     src_path_groups: dict[str, list[str]] = src_model._groupPathsByParentNode(src_paths)

    #     if update_model:
    #         src_model.beginResetModel()
    #         if dst_model is not src_model:
    #             dst_model.beginResetModel()

    #     # transfer paths one node at a time
    #     abort = False
    #     for src_parent_path, src_child_paths in src_path_groups.items():
    #         src_parent_node: xr.DataTree = src_datatree[src_parent_path]

    #         # transfer nodes
    #         nodes_to_transfer = [node for name, node in src_parent_node.children.items() if f'{src_parent_path}/{name}' in src_child_paths]
    #         dst_keys = list(dst_parent_node.keys())
    #         for node in nodes_to_transfer:
    #             node.orphan()
    #             name = node.name
    #             # handle name conflict
    #             if name in dst_keys:
    #                 if name_conflict == 'ask':
    #                     focused_widget: QWidget = QApplication.focusWidget()
    #                     msg = f'"{name}" already exists in destination DataTree.'
    #                     dlg = NameConflictDialog(msg, focused_widget)
    #                     dlg._merge_button.setEnabled(False) # TODO: implement merge below
    #                     if dlg.exec() == QDialog.DialogCode.Rejected:
    #                         abort = True
    #                         break
    #                     this_name_conflict = dlg._action_button_group.checkedButton().text().lower()
    #                     apply_to_all_name_conflicts = dlg._apply_to_all_checkbox.isChecked()
    #                     if apply_to_all_name_conflicts:
    #                         name_conflict = this_name_conflict
    #                 else:
    #                     this_name_conflict = name_conflict.lower()
    #                 if this_name_conflict == 'overwrite':
    #                     pass # will be overwritten below
    #                 elif this_name_conflict == 'merge':
    #                     # TODO: implement merge
    #                     continue
    #                 elif this_name_conflict == 'keep both':
    #                     name = xarray_utils.unique_name(name, dst_keys)
    #                     dst_keys.append(name)
    #                 elif this_name_conflict == 'skip':
    #                     continue
    #             dst_node_path = f'{dst_parent_path}/{name}'
    #             dst_datatree[dst_node_path] = node
    #         if abort:
    #             break
            
    #         # transfer variables
    #         var_names_to_transfer = [name for name in src_parent_node.variables if f'{src_parent_path}/{name}' in src_child_paths]
    #         var_names_not_to_transfer = [name for name in src_parent_node.variables if f'{src_parent_path}/{name}' not in src_child_paths]
    #         dataset_to_transfer: xr.Dataset = src_parent_node.to_dataset().drop_vars(var_names_not_to_transfer)
    #         dst_dataset: xr.Dataset = dst_parent_node.to_dataset()
    #         # handle name conflicts (data_vars only, ignore coords)
    #         dst_keys = list(dst_parent_node.keys())
    #         for name in list(dataset_to_transfer.data_vars):
    #             if name in dst_keys:
    #                 if name_conflict == 'ask':
    #                     focused_widget: QWidget = QApplication.focusWidget()
    #                     msg = f'"{name}" already exists in destination DataTree.'
    #                     dlg = NameConflictDialog(msg, focused_widget)
    #                     if dlg.exec() == QDialog.DialogCode.Rejected:
    #                         abort = True
    #                         break
    #                     this_name_conflict = dlg._action_button_group.checkedButton().text().lower()
    #                     apply_to_all_name_conflicts = dlg._apply_to_all_checkbox.isChecked()
    #                     if apply_to_all_name_conflicts:
    #                         name_conflict = this_name_conflict
    #                 else:
    #                     this_name_conflict = name_conflict.lower()
    #                 if this_name_conflict == 'overwrite':
    #                     dst_dataset = dst_dataset.drop_vars([name])
    #                 elif this_name_conflict == 'merge':
    #                     pass # will be merged below
    #                 elif this_name_conflict == 'keep both':
    #                     new_name = xarray_utils.unique_name(name, dst_keys)
    #                     dst_keys.append(new_name)
    #                     dataset_to_transfer = dataset_to_transfer.rename_vars({name: new_name})
    #                 elif this_name_conflict == 'skip':
    #                     dataset_to_transfer = dataset_to_transfer.drop_vars([name])
    #         if abort:
    #             break
    #         try:
    #             dst_dataset = dst_dataset.merge(dataset_to_transfer, compat='no_conflicts', join='outer', combine_attrs='override')
    #             dst_parent_node.dataset = dst_dataset
    #             src_parent_node.dataset = src_parent_node.to_dataset().drop_vars(var_names_to_transfer)
    #         except:
    #             msg = f'Failed to transfer variables from {src_parent_path}'
    #             from warnings import warn
    #             warn(msg)
    #             self.popupWarningDialog(msg)

    #     if update_model:
    #         src_model.endResetModel()
    #         if dst_model is not src_model:
    #             dst_model.endResetModel()
    #     print('... movePaths')
    
    # def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
    #     # print('moveRows(', self.pathFromIndex(src_parent_index), src_row, count, self.pathFromIndex(dst_parent_index), dst_row, ')', flush=True)
    #     if count <= 0:
    #         return False
        
    #     n_src_rows: int = self.rowCount(src_parent_index)
    #     n_dst_rows: int = self.rowCount(dst_parent_index)
    #     if (src_row < 0) or (src_row + count > n_src_rows):
    #         return False
    #     if not (0 <= dst_row <= n_dst_rows):
    #         return False

    #     src_parent_path: str = self.pathFromIndex(src_parent_index)
    #     dst_parent_path: str = self.pathFromIndex(dst_parent_index)
    #     # print('src_parent_path:', src_parent_path, flush=True)
    #     # print('dst_parent_path:', dst_parent_path, flush=True)
    #     # print('src_rows:', list(range(src_row, src_row + count)), flush=True)
    #     # print('dst_row:', dst_row, flush=True)

    #     if (src_parent_path == dst_parent_path) and (0 <= dst_row - src_row <= count):
    #         # no change
    #         # print('No change in moveRows.', flush=True)
    #         return False
        
    #     src_parent_node: xr.DataTree = self._root[src_parent_path]
    #     dst_parent_node: xr.DataTree = self._root[dst_parent_path]

    #     # the source items prior to the move
    #     pre_src_names: list[str] = self.visibleRowNames(src_parent_node)[src_row: src_row + count]
    #     pre_src_data_vars: dict[str, xr.DataArray] = {name: src_parent_node[name] for name in pre_src_names if name in src_parent_node.data_vars}
    #     pre_src_coords: dict[str, xr.DataArray] = {name: src_parent_node[name] for name in pre_src_names if name in src_parent_node.coords}
    #     pre_src_children: dict[str, xr.DataTree] = {name: src_parent_node[name] for name in pre_src_names if name in src_parent_node.children}
    #     # print('pre_src_names:', pre_src_names, flush=True)
    #     # print('pre_src_data_vars:', list(pre_src_data_vars), flush=True)
    #     # print('pre_src_coords:', list(pre_src_coords), flush=True)
    #     # print('pre_src_children:', list(pre_src_children), flush=True)

    #     # abort if attempting to move a node to its own descendent
    #     if pre_src_children:
    #         dst_parent_paths: list[str] = [node.path for node in dst_parent_node.parents]
    #         src_paths: list[str] = [node.path for node in pre_src_children.values()]
    #         # print('dst_parent_paths:', dst_parent_paths, flush=True)
    #         # print('src_paths:', src_paths, flush=True)
    #         for src_path in src_paths:
    #             # print('src_path:', src_path, flush=True)
    #             if src_path in dst_parent_paths:
    #                 msg = 'Cannot move a DataTree node to its own descendent.'
    #                 warn(msg)
    #                 self.popupWarningDialog(msg)
    #                 return False
        
    #     # the destination items prior to the move
    #     pre_dst_names: list[str] = self.visibleRowNames(dst_parent_node)
    #     pre_dst_data_vars: dict[str, xr.DataArray] = {name: dst_parent_node[name] for name in pre_dst_names if name in dst_parent_node.data_vars}
    #     pre_dst_coords: dict[str, xr.DataArray] = {name: dst_parent_node[name] for name in pre_dst_names if name in dst_parent_node.coords}
    #     pre_dst_children: dict[str, xr.DataTree] = {name: dst_parent_node[name] for name in pre_dst_names if name in dst_parent_node.children}
    #     # print('pre_dst_names:', pre_dst_names, flush=True)
    #     # print('pre_dst_data_vars:', list(pre_dst_data_vars), flush=True)
    #     # print('pre_dst_coords:', list(pre_dst_coords), flush=True)
    #     # print('pre_dst_children:', list(pre_dst_children), flush=True)

    #     # check for alignment conflicts
    #     # For now, moves are only allowed between aligned nodes.
    #     if src_parent_path != dst_parent_path:
    #         src_nodes_that_must_align: list[xr.DataTree] = []
    #         if pre_src_data_vars or pre_src_coords:
    #             src_nodes_that_must_align.append(src_parent_node)
    #         src_nodes_that_must_align += list(pre_src_children.values())
    #         for src_node in src_nodes_that_must_align:
    #             # print(f'checking alignment between {src_node.path} and {dst_parent_path}...')
    #             try:
    #                 xr.align(src_node.to_dataset(), dst_parent_node.to_dataset(), join='exact')
    #             except:
    #                 msg = 'Cannot move to non-aligned DataTree nodes.'
    #                 warn(msg)
    #                 self.popupWarningDialog(msg)
    #                 return False

    #     # check for name conflicts unless moving within the same node
    #     dst_overwrite_names: list[str] = []
    #     src_renames: dict[str, str] = {}
    #     merge_names: list[str] = []
    #     if src_parent_path != dst_parent_path:
    #         name_conflict_action: str = None
    #         apply_to_all_name_conflicts: bool = False
    #         for name in pre_src_names:
    #             if name in pre_dst_names:
    #                 # !! name conflict
    #                 if not apply_to_all_name_conflicts:
    #                     msg = f'"{name}" already exists in destination DataTree.'
    #                     dlg = NameConflictDialog(msg)
    #                     if dlg.exec() == QDialog.DialogCode.Rejected:
    #                         # abort entire move
    #                         return False
    #                     name_conflict_action = dlg._action_button_group.checkedButton().text()
    #                     apply_to_all_name_conflicts = dlg._apply_to_all_checkbox.isChecked()
    #                 # handle name conflict
    #                 if name_conflict_action == 'Overwrite':
    #                     dst_overwrite_names.append(name)
    #                 elif name_conflict_action == 'Merge':
    #                     merge_names.append(name)
    #                 elif name_conflict_action == 'Keep Both':
    #                     src_renames[name] = self.uniqueName(name, pre_dst_names + pre_src_names + list(src_renames))
    #                 elif name_conflict_action == 'Skip':
    #                     pre_src_names.remove(name)
    #                     if name in pre_src_data_vars:
    #                         pre_src_data_vars.pop(name)
    #                     elif name in pre_src_coords:
    #                         pre_src_coords.pop(name)
    #                     elif name in pre_src_children:
    #                         pre_src_children.pop(name)

    #     # check for merge conflicts
    #     if merge_names:
    #         pass # TODO...

    #     # copy inherited coords for moved data_vars
    #     inherited_coord_names = src_parent_node._inherited_coords_set()
    #     for name, pre_src_data_var in pre_src_data_vars.items():
    #         for dim in pre_src_data_var.dims:
    #             if dim in inherited_coord_names:
    #                 coord = src_parent_node.coords[dim]
    #                 pre_src_data_var.coords[dim] = xr.DataArray(coord.data.copy(), dims=coord.dims, attrs=deepcopy(coord.attrs))
        
    #     # the source items after the move
    #     post_src_names: list[str] = []
    #     post_src_data_vars: dict[str, xr.DataArray] = {}
    #     post_src_coords: dict[str, xr.DataArray] = {}
    #     post_src_children: dict[str, xr.DataTree] = {}
    #     for name in pre_src_names:
    #         dst_name = src_renames.get(name, name)
    #         post_src_names.append(dst_name)
    #         if name in pre_src_children:
    #             post_src_children[dst_name] = pre_src_children[name]
    #         elif name in pre_src_data_vars:
    #             post_src_data_vars[dst_name] = pre_src_data_vars[name]
    #         elif name in pre_src_coords:
    #             post_src_coords[dst_name] = pre_src_coords[name]
    #     # print('post_src_names:', post_src_names, flush=True)
    #     # print('post_src_data_vars:', list(post_src_data_vars), flush=True)
    #     # print('post_src_coords:', list(post_src_coords), flush=True)
    #     # print('post_src_children:', list(post_src_children), flush=True)
        
    #     # get name at insertion point
    #     try:
    #         dst_name = pre_dst_names[dst_row]
    #     except IndexError:
    #         dst_name = None
    #     # print('dst_name:', dst_name, flush=True)
        
    #     # the destination items after the move
    #     post_dst_names: list[str] = []
    #     post_dst_data_vars: dict[str, xr.DataArray] = {}
    #     post_dst_coords: dict[str, xr.DataArray] = {}
    #     post_dst_children: dict[str, xr.DataTree] = {}
    #     for dname in pre_dst_names:
    #         if dname in dst_overwrite_names:
    #             continue
    #         if dname == dst_name:
    #             # insert moved items here
    #             for sname in post_src_names:
    #                 post_dst_names.append(sname)
    #         post_dst_names.append(dname)
    #     if dst_name is None:
    #         # append moved items
    #         for sname in post_src_names:
    #             post_dst_names.append(sname)
    #     for name in post_dst_names:
    #         if name in pre_dst_children:
    #             post_dst_children[name] = pre_dst_children[name]
    #         elif name in post_src_children:
    #             post_dst_children[name] = post_src_children[name]
    #         elif name in pre_dst_data_vars:
    #             post_dst_data_vars[name] = pre_dst_data_vars[name]
    #         elif name in post_src_data_vars:
    #             post_dst_data_vars[name] = post_src_data_vars[name]
    #         elif name in pre_dst_coords:
    #             post_dst_coords[name] = pre_dst_coords[name]
    #         elif name in post_src_coords:
    #             post_dst_coords[name] = post_src_coords[name]
    #     # print('post_dst_names:', post_dst_names, flush=True)
    #     # print('post_dst_data_vars:', list(post_dst_data_vars), flush=True)
    #     # print('post_dst_coords:', list(post_dst_coords), flush=True)
    #     # print('post_dst_children:', list(post_dst_children), flush=True)

    #     self.beginResetModel()
    #     # self.beginMoveRows(src_parent_index, src_row, src_row + count - 1, dst_parent_index, dst_row)  # !? segfault?

    #     # move data arrays
    #     if pre_src_data_vars or pre_src_coords:
    #         # update dst_parent_node.dataset
    #         ds: xr.Dataset = dst_parent_node.to_dataset()
    #         dst_parent_node.dataset = xr.Dataset(
    #             data_vars=post_dst_data_vars,
    #             coords=post_dst_coords,
    #             attrs=ds.attrs
    #         )

    #         if src_parent_path != dst_parent_path:
    #             # drop moved variables from src_parent_node
    #             names_to_drop = list(pre_src_data_vars) + list(pre_src_coords)
    #             src_parent_node.dataset = src_parent_node.to_dataset().drop_vars(names_to_drop)
        
    #     # move nodes
    #     if pre_src_children:
    #         if src_parent_path != dst_parent_path:
    #             # remove moved nodes from src_parent_node
    #             for name, node in pre_src_children.items():
    #                 # copy inherited coords only for all data_vars dims
    #                 inherited_coords_copy = {}
    #                 if node.data_vars:
    #                     data_var_dims = []
    #                     for data_var in node.data_vars.values():
    #                         data_var_dims += list(data_var.dims)
    #                     for name in node._inherited_coords_set():
    #                         if name not in data_var_dims:
    #                             continue
    #                         coord = node.coords[name]
    #                         inherited_coords_copy[name] = xr.DataArray(coord.data.copy(), dims=coord.dims, attrs=deepcopy(coord.attrs))
    #                 node.orphan()
    #                 if inherited_coords_copy:
    #                     node.dataset = node.to_dataset().assign_coords(inherited_coords_copy)
            
    #         # attach nodes to dst_parent_node
    #         dst_parent_node.children = post_dst_children
        
    #     # print(self.datatree(), flush=True)
    #     # self.endMoveRows()
    #     self.endResetModel()
    #     return True
    
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
        src_model: XarrayDataTreeModel = data.model
        src_items: list[XarrayDataTreeItem] = data.items
        dst_model: XarrayDataTreeModel = self
        dst_parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)

        src_model.transferItems(src_items, dst_model, dst_parent_item, row)

        # !? If we return True, the model will attempt to remove rows.
        # As we already completely handled the move, this will corrupt our model, so return False.
        print('... dropMimeData')
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

    def __init__(self, model: XarrayDataTreeModel, items: list[XarrayDataTreeItem]):
        QMimeData.__init__(self)

        # these define the datatree items being dragged
        self.model: XarrayDataTreeModel = model
        self.items: list[XarrayDataTreeItem] = items

        # Ensure that the MIME type self.MIME_TYPE is set.
        # The actual value of the data here is not important, as we won't use it.
        # Instead, we will use the above attributes to handle drag-and-drop.
        self.setData(self.MIME_TYPE, self.MIME_TYPE.encode('utf-8'))
    
    def hasFormat(self, mime_type: str) -> bool:
        """ Check if the MIME data has the specified format.
        
        Overrides the default method to check for self.MIME_TYPE.
        """
        return mime_type == self.MIME_TYPE or super().hasFormat(mime_type)


class NameConflictDialog(QDialog):

    def __init__(self, msg: str, parent: QWidget = None, **kwargs):
        if parent is None:
            parent = QApplication.focusWidget()
        if 'modal' not in kwargs:
            kwargs['modal'] = True
        super().__init__(parent, **kwargs)
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