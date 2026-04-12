""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- moveRows: merge items?
- should we ask before removing inherited coords in descendents when moving a coord?
- enforce coord order at all times? note: this currently happens when refreshing the tree, but not otherwise.
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
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import XarrayDataTreeItem, AbstractTreeModel
import cmap


class XarrayDataTreeModel(AbstractTreeModel):
    """ PyQt tree model interface for a Xarray DataTree.
    """

    MIME_TYPE = 'application/x-xarray-datatree-model'

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

        # colors
        self._default_text_color = QApplication.palette().color(QPalette.ColorRole.Text)
        color_scheme = QGuiApplication.styleHints().colorScheme()
        if color_scheme == Qt.ColorScheme.Dark:
            self._node_color: QColor = QColor('#e69f00')
            self._data_var_color: QColor = QColor('#56b4e9')
            self._coord_color: QColor = QColor('#cc79a7')
            self._unknown_color: QColor = QColor('#990000')
        elif color_scheme == Qt.ColorScheme.Light:
            # TODO: choose better colors for light mode
            self._node_color: QColor = self._default_text_color
            self._data_var_color: QColor = QColor('#D7005F')
            self._coord_color: QColor = QColor('#005F87')
            self._unknown_color: QColor = QColor('#FF0000')
        self._inherited_coord_color: QColor = QColor(self._coord_color or self._default_text_color)
        self._inherited_coord_color.setAlpha(128)

        # icons
        self._node_icon: QIcon = qta.icon('ph.folder-thin', color=self._node_color)
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin', color=self._data_var_color)
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin', color=self._coord_color)
        self._index_coord_icon: QIcon = qta.icon('ph.asterisk-thin', color=self._coord_color)
        self._inherited_coord_icon: QIcon = qta.icon('ph.asterisk-thin', color=self._inherited_coord_color)
        self._unknown_icon: QIcon = qta.icon('fa6s.question', color=self._unknown_color)

        # setup item tree
        datatree: xr.DataTree = xr.DataTree()
        self._root_item = XarrayDataTreeItem(datatree)
    
    def treeData(self) -> xr.DataTree:
        """ Get the datatree.
        """
        root_item: XarrayDataTreeItem = self.rootItem()
        return root_item.data
    
    def setTreeData(self, data: xr.DataTree) -> None:
        """ Set the datatree.
        """
        new_root_item = XarrayDataTreeItem(data)
        self._updateItemSubtree(new_root_item)
        self.setRootItem(new_root_item)
    
    def _updateItemSubtree(self, item: XarrayDataTreeItem) -> None:
        item.updateSubtree(
            include_data_vars=self.isDataVarsVisible(),
            include_coords=self.isCoordsVisible(),
            include_inherited_coords=self.isInheritedCoordsVisible()
        )
    
    def reset(self) -> None:
        """ Reset the model.
        """
        self.beginResetModel()
        self._updateItemSubtree(self._root_item)
        self.endResetModel()
    
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
        if item.isInheritedCoord():
            return Qt.ItemFlag.ItemIsEnabled
        
        if index.column() == 0:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        elif index.column() == 1:
            # cannot edit details column
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            if item.isNode():
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
                return item.name()
            elif index.column() == 1:
                # details column
                if item.isNode():
                    sizes_str = ', '.join([f'{dim}: {size}' for dim, size in item.node().sizes.items()])
                    return f'({sizes_str})'
                elif item.isDataVar():
                    rep = str(item.node().dataset)
                    i = rep.find('Data variables:')
                    i = rep.find(f' {item.name()} ', i)  # find data_var
                    i = rep.find('(', i)  # skip data_var name
                    preview = False
                    if preview:
                        j = rep.find('\n', i)
                    else:
                        j = rep.find(')', i)  # end of dims
                        j = rep.find(' ', j+2)  # after dtype
                    rep = rep[i:j] if j > 0 else rep[i:]
                    return rep
                elif item.isCoord():
                    rep = str(item.node().dataset)
                    i = rep.find('Coordinates:')
                    i = rep.find(f' {item.name()} ', i)  # find coord
                    i = rep.find('(', i)  # skip coord name
                    preview = False
                    if preview:
                        j = rep.find('\n', i)
                    else:
                        j = rep.find(')', i)  # end of dims
                        j = rep.find(' ', j+2)  # after dtype
                    rep = rep[i:j] if j > 0 else rep[i:]
                    return rep
        
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: XarrayDataTreeItem = self.itemFromIndex(index)
                if item.isNode():
                    return self._node_icon
                elif item.isDataVar():
                    return self._data_var_icon
                elif item.isInheritedCoord():
                    return self._inherited_coord_icon
                elif item.isIndexCoord():
                    return self._index_coord_icon
                elif item.isCoord():
                    return self._coord_icon
                else:
                    # should never happen
                    return self._unknown_icon
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            if item.isNode():
                return self._node_color
            elif item.isDataVar():
                return self._data_var_color
            elif item.isCoord():
                if item.isInheritedCoord():
                    return self._inherited_coord_color
                return self._coord_color

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False
        if index.column() != 0:
            # only allow editing the names in column 0
            return False
        if role == Qt.ItemDataRole.EditRole:
            # rename object
            new_name: str = value.strip()
            if not new_name:
                # must have a valid name
                return False
            if '/' in new_name:
                parent_widget: QWidget = QApplication.focusWidget()
                title='Invalid Name'
                text = f'Object names cannot contain path separators "/".'
                QMessageBox.warning(parent_widget, title, text)
                return False
            item: XarrayDataTreeItem = self.itemFromIndex(index)
            if item.isInheritedCoord():
                # cannot rename inherited coords
                return False
            old_name = item.name()
            if new_name == old_name:
                # nothing to do
                return False
            #            parent_item: XarrayDataTreeItem = item.parent
            parent_node: xr.DataTree = item.parentNode()
            # ensure no name conflict with existing objects
            parent_keys: list[str] = list(parent_node.keys())
            if new_name in parent_keys:
                parent_widget: QWidget = QApplication.focusWidget()
                title='Existing Name'
                text = f'"{new_name}" already exists in parent DataTree.'
                QMessageBox.warning(parent_widget, title, text)
                return False
            if item.isIndexCoord():
                # rename dimension in entire branch
                branch_root: xr.DataTree = xarray_utils.aligned_root(parent_node)
                branch_root.dataset = branch_root.to_dataset().rename_dims({old_name: new_name})
                for node in branch_root.descendants:
                    node.dataset = node.to_dataset().swap_dims({old_name: new_name})
                # rename index coord
                new_index_coord = item.data()#.copy(deep=False).swap_dims({old_name: new_name})
                parent_node.dataset = parent_node.to_dataset().reindex({new_name: new_index_coord}, copy=False).drop_indexes(old_name).reset_coords(old_name, drop=True)
                for node in parent_node.descendants:
                    if old_name in node.coords:
                        node.dataset = node.to_dataset().reset_coords(old_name, drop=True)
                # xarray_utils.rename_dims(parent_node, {old_name: new_name})
                item._varname = new_name
                # update item name in subtree
                branch_item: XarrayDataTreeItem
                for branch_item in item.parent.subtree_depth_first():
                    if branch_item._varname == old_name:
                        branch_item._varname = new_name
                print(item.parent)
                self.refreshRequested.emit() # inefficient solution to update branch
                return True
            elif item.isVariable():
                parent_node.dataset = parent_node.to_dataset().rename_vars({old_name: new_name})
                item._varname = new_name
                return True
            elif item.isNode():
                parent_node.children = {name if name != old_name else new_name: child for name, child in parent_node.children.items()}
                # item._node.name = new_name
                return True
        return False

    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        if self.isInheritedCoordsVisible():
            parent_item: XarrayDataTreeItem = self.itemFromIndex(parent_index)
            items_to_remove: list[XarrayDataTreeItem] = parent_item.children[row: row + count]
            is_coord_removed = any(item.isCoord() for item in items_to_remove)
        success = super().removeRows(row, count, parent_index)
        if self.isInheritedCoordsVisible() and success and is_coord_removed:
            # clean up inherited coords in parent's subtree
            self._updateSubtreeCoordItems(parent_item)
        return success
    
    def insertItems(self, items: list[XarrayDataTreeItem], row: int, parent_item: XarrayDataTreeItem) -> None:
        if not items:
            return

        if not parent_item.isNode():
            # raise ValueError('Can only insert items into nodes.')
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot insert items in non-node "{parent_item.path()}".'
            QMessageBox.warning(parent_widget, title, text)
            return False
        
        # TODO: handle name conflicts (or should this be done by the individual items?)
        # TODO: handle alignment conflicts (or at least decide how they should be handled?)
        
        # insert items one data type at a time
        for data_type in tuple(XarrayDataTreeItem.DataType):
            items_of_type: list[XarrayDataTreeItem] = [item for item in items if item.dataType() == data_type]
            if items_of_type:
                row_for_type = XarrayDataTreeModel._insertionRow(parent_item, data_type, row)
                super().insertItems(items_of_type, row_for_type, parent_item)
                if row_for_type < row:
                    row += len(items_of_type)
        
        # update inherited coords in inserted item subtrees
        if self.isInheritedCoordsVisible():
            for item in items:
                self._updateSubtreeCoordItems(item)
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
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
        
        items_to_move: list[XarrayDataTreeItem] = src_parent_item.children[src_row: src_row + count]

        # TODO: handle name conflicts (or should this be done by the individual items?)
        # TODO: handle alignment conflicts (or at least decide how they should be handled?)
        
        # move items one data type at a time
        for data_type in reversed(tuple(XarrayDataTreeItem.DataType)):
            items_of_type = [item for item in items_to_move if item.dataType() == data_type]
            if not items_of_type:
                continue
            src_row_for_type = items_of_type[0].row()
            count = len(items_of_type)
            dst_row_for_type = XarrayDataTreeModel._insertionRow(dst_parent_item, data_type, dst_row)
            success = super().moveRows(src_parent_index, src_row_for_type, count, dst_parent_index, dst_row_for_type)
            if success and dst_row_for_type < dst_row:
                dst_row += count
        
        # update inherited coords in moved item subtrees
        if self.isInheritedCoordsVisible():
            for item in items_to_move:
                self._updateSubtreeCoordItems(item)
        
        return True

    def _visibleRowNames(self, item: XarrayDataTreeItem) -> list[str]:
        if not item.isNode():
            return []
        node: xr.DataTree = item.data()
        names: list[str] = []
        for data_type in tuple(XarrayDataTreeItem.DataType):
            if data_type == XarrayDataTreeItem.DataType.INDEX_COORD:
                if self.isCoordsVisible():
                    names += list(node.xindexes)
            elif data_type == XarrayDataTreeItem.DataType.INHERITED_COORD:
                if self.isCoordsVisible() and self.isInheritedCoordsVisible():
                    names += list(node._inherited_coords_set())
            elif data_type == XarrayDataTreeItem.DataType.COORD:
                if self.isCoordsVisible():
                    names += [name for name in node.coords if (name not in node.xindexes) and (name not in node._inherited_coords_set())]
            elif data_type == XarrayDataTreeItem.DataType.DATA_VAR:
                if self.isDataVarsVisible():
                    names += list(node.data_vars)
            elif data_type == XarrayDataTreeItem.DataType.NODE:
                 names += list(node.children)
        return names
    
    def _updateSubtreeCoordItems(self, parent_item: XarrayDataTreeItem) -> None:
        item: XarrayDataTreeItem
        for item in parent_item.subtree_depth_first():
            if not item.isNode():
                continue
            
            index: QModelIndex = self.indexFromItem(item)
            node: xr.DataTree = item.data()
            inherited_coord_names = node._inherited_coords_set()
            coord_names = list(node.coords)
            
            # remove invalid coord items (no need to touch datatree)
            # note: invalid coord items may have a data type of None after tree manipulation
            coord_items_to_remove: list[XarrayDataTreeItem] = []
            child: XarrayDataTreeItem
            for child in item.children:
                if (child.isCoord() and child.name() not in node.coords) or (child.dataType() is None) or (not self.isInheritedCoordsVisible() and child.isInheritedCoord()):
                    coord_items_to_remove.append(child)
            for coord_item in reversed(coord_items_to_remove):
                self.beginRemoveRows(index, coord_item.row(), coord_item.row())
                coord_item.orphan()
                self.endRemoveRows()
            
            if not self.isCoordsVisible():
                continue
            
            # add missing coord items (no need to touch datatree)
            existing_coord_names: list[str] = [child.name() for child in item.children if child.isCoord()]
            missing_coord_names: list[str] = [name for name in coord_names if (name not in existing_coord_names) and (self.isInheritedCoordsVisible() or name not in inherited_coord_names)]
            if missing_coord_names:
                row_names: list[str] = self._visibleRowNames(item)
                for name in missing_coord_names:
                    inherited_coord_item = XarrayDataTreeItem(node.coords[name])
                    row: int = row_names.index(name)
                    if row == -1:
                        row = len(item.children)
                    self.beginInsertRows(index, row, row)
                    item.insertChild(row, inherited_coord_item)
                    self.endInsertRows()
    
    @staticmethod
    def _itemBlocks(items: list[XarrayDataTreeItem]) -> list[list[XarrayDataTreeItem]]:
        """ Group items by data type, parent, and contiguous rows.

        Each block can be input to removeRows() or moveRows().
        Blocks are ordered depth-first. Typically you should remove/move blocks in reverse depth-first order to ensure insertion row indices remain valid after handling each block.
        """
        # so we don't modify the input list
        items = items.copy()

        # order by data type
        items.sort(key=lambda item: XarrayDataTreeModel._data_type_order.index(item._data_type))

        # order items depth-first so that it is easier to group them into blocks
        items.sort(key=lambda item: item.level)
        items.sort(key=lambda item: item.siblingIndex)

        # group items into blocks by [data type,] parent, and contiguous rows
        blocks: list[list[XarrayDataTreeItem]] = [[items[0]]]
        for item in items[1:]:
            added_to_block = False
            for block in blocks:
                if (item.parent is block[0].parent) and (item._data_type == block[0]._data_type):
                    if item.siblingIndex == block[-1].siblingIndex + 1:
                        block.append(item)
                    else:
                        blocks.append([item])
                    added_to_block = True
                    break
            if not added_to_block:
                blocks.append([item])
        return blocks
    
    @staticmethod
    def _insertionRow(parent_item: XarrayDataTreeItem, data_type: XarrayDataTreeItem.DataType, row: int) -> int:
        """ Get the row index at which to insert an item of data_type when attempting to insert at row.
        
        This ensures that the data type order is maintained.
        """
        items_of_type: list[XarrayDataTreeItem] = [item for item in parent_item.children if item.dataType() == data_type]

        if not items_of_type:
            # insert after all items of other data types that come before data_type in the model
            row = 0
            for dtype in tuple(XarrayDataTreeItem.DataType):
                if dtype == data_type:
                    break
                row += len([item for item in parent_item.children if item.dataType() == dtype])
            return row
        elif row > items_of_type[-1].row():
            # append after last item of data_type
            return items_of_type[-1].row() + 1
        elif row <= items_of_type[0].row():
            # prepend before first item of data_type
            return items_of_type[0].row()
        else:
            # insert at row which falls within items of data_type
            return row
    
    # @staticmethod
    # def _handleInsertionConflicts(name_item_map: dict[str, XarrayDataTreeItem], parent_item: XarrayDataTreeItem, orphan_only: bool = False) -> dict[str, XarrayDataTreeItem]:
    #     if not parent_item.is_group:
    #         # cannot insert items into non-group item
    #         return {}
        
    #     # so we don't alter the input map
    #     name_item_map = name_item_map.copy()

    #     parent_group: xr.DataTree = parent_item.data
    #     parent_keys: list[str] = list(parent_group.keys())

    #     # conflicts[name] = conflict message
    #     # we'll handle name conflicts separately from all other conflicts
    #     conflicts: dict[str, str] = {}
    #     name_conflicts: dict[str, str] = {}
        
    #     name: str
    #     item: XarrayDataTreeItem
    #     for name, item in name_item_map.items():
    #         # only allow insertion of orphaned items
    #         if orphan_only and item.parent is not None:
    #             conflicts[name] = f'Cannot insert non-orphan "{item.path}".'
    #             continue

    #         # cannot insert item into one of its descendents
    #         if parent_item.hasAncestor(item):
    #             conflicts[name] = f'Cannot insert "{item.path}" into its own subtree at "{parent_item.path}".'
    #             continue

    #         # inserted objects must align with parent group
    #         try:
    #             if isinstance(item.data, xr.DataTree):
    #                 data = item.data.dataset
    #             elif isinstance(item.data, xr.DataArray):
    #                 data = item.data
    #             # dataset views include inherited coords
    #             xr.align(parent_group.dataset, data, join='exact')
    #         except:
    #             conflicts[name] = f'"{item.path}" is not aligned with "{parent_item.path}".'
    #             continue
            
    #         # inserted item names must be valid new keys in parent
    #         if '/' in name:
    #             conflicts[name] = f'"{name}" is not a valid DataTree name, which cannot contain "/".'
    #             continue
    #         if name in parent_keys:
    #             name_conflicts[name] = f'"{name}" already exists in "{parent_item.path}".'
    #             continue

    #         parent_keys.append(name)
        
    #     # either abort or skip these conflicts
    #     if conflicts:
    #         parent_widget: QWidget = QApplication.focusWidget()
    #         title = 'Conflict'
    #         text = '\n'.join(list(conflicts.values()))
    #         dlg = ConflictDialog(parent_widget, title, text)
    #         if dlg.exec() == QDialog.DialogCode.Rejected:
    #             # abort
    #             return {}
    #         for name in conflicts:
    #             # skip conflicting items
    #             del name_item_map[name]
        
    #     # either abort, skip, overwrite, merge, or rename these conflicts
    #     if name_conflicts:
    #         parent_widget: QWidget = QApplication.focusWidget()
    #         title = 'Name Conflict'
    #         text = '\n'.join(list(name_conflicts.values()))
    #         dlg = NameConflictDialog(parent_widget, title, text)
    #         dlg._merge_button.setEnabled(False) # TODO
    #         if dlg.exec() == QDialog.DialogCode.Rejected:
    #             # abort
    #             return {}
    #         action = dlg._action_button_group.checkedButton().text().lower()
    #         if action == 'overwrite':
    #             # nothing to do here (this is the default)
    #             pass
    #         elif action == 'merge':
    #             # TODO
    #             pass
    #         elif action == 'keep both':
    #             for existing_name in name_conflicts:
    #                 new_name: str = xarray_utils.unique_name(existing_name, parent_keys)
    #                 name_item_map = {new_name if name == existing_name else name: item for name, item in name_item_map.items()}
    #                 parent_keys.append(new_name)
    #         elif action == 'skip':
    #             for name in name_conflicts:
    #                 del name_item_map[name]
        
    #     return name_item_map


# class ConflictDialog(QDialog):

#     def __init__(self, parent: QWidget, title: str, text: str):
#         super().__init__(parent, modal=True)
        
#         self.setWindowTitle(title)
#         vbox = QVBoxLayout(self)

#         self._text_field = QTextEdit(readOnly=True, plainText=text)
#         vbox.addWidget(self._text_field)
#         vbox.addSpacing(10)

#         # self._skip_button = QRadioButton('Skip')
#         # self._skip_all_button = QRadioButton('Skip All')
#         # self._action_button_group = QButtonGroup()
#         # self._action_button_group.addButton(self._skip_button)
#         # self._action_button_group.addButton(self._skip_all_button)
#         # self._skip_button.setChecked(True)
#         # vbox.addWidget(self._skip_button)
#         # vbox.addWidget(self._skip_all_button)
#         # vbox.addSpacing(10)

#         buttons = QDialogButtonBox()
#         self._continue_button: QPushButton = buttons.addButton('Skip & Continue', QDialogButtonBox.ButtonRole.AcceptRole)
#         self._cancel_button: QPushButton = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
#         self._continue_button.setAutoDefault(False)
#         self._cancel_button.setDefault(True)
#         buttons.accepted.connect(self.accept)
#         buttons.rejected.connect(self.reject)
#         vbox.addWidget(buttons)


# class NameConflictDialog(QDialog):

#     def __init__(self, parent: QWidget, title: str, text: str):
#         super().__init__(parent, modal=True)
        
#         self.setWindowTitle(title)
#         vbox = QVBoxLayout(self)

#         self._text_field = QTextEdit(readOnly=True, plainText=text)
#         vbox.addWidget(self._text_field)
#         vbox.addSpacing(10)

#         self._overwrite_button = QRadioButton('Overwrite')
#         self._merge_button = QRadioButton('Merge')
#         self._keep_both_button = QRadioButton('Keep Both')
#         self._skip_button = QRadioButton('Skip')
#         self._action_button_group = QButtonGroup()
#         self._action_button_group.addButton(self._overwrite_button)
#         self._action_button_group.addButton(self._merge_button)
#         self._action_button_group.addButton(self._keep_both_button)
#         self._action_button_group.addButton(self._skip_button)
#         vbox.addWidget(self._overwrite_button)
#         vbox.addWidget(self._merge_button)
#         vbox.addWidget(self._keep_both_button)
#         vbox.addWidget(self._skip_button)
#         vbox.addSpacing(10)

#         self._apply_to_all_checkbox = QCheckBox('Apply to all')
#         vbox.addWidget(self._apply_to_all_checkbox)

#         buttons = QDialogButtonBox()
#         self._continue_button: QPushButton = buttons.addButton('Continue', QDialogButtonBox.ButtonRole.AcceptRole)
#         self._cancel_button: QPushButton = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
#         self._continue_button.setAutoDefault(False)
#         self._cancel_button.setDefault(True)
#         buttons.accepted.connect(self.accept)
#         buttons.rejected.connect(self.reject)
#         vbox.addWidget(buttons)

#         # continuing is only valid if an action is selected
#         self._continue_button.setEnabled(self._action_button_group.checkedButton() is not None)
#         for button in self._action_button_group.buttons():
#             button.pressed.connect(lambda: self._continue_button.setEnabled(True))


def test_model():
    app = QApplication()

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

    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setTreeData(dt)

    view = QTreeView()
    view.setModel(model)
    view.expandAll()
    for col in range(model.columnCount()):
        view.resizeColumnToContents(col)
    view.resize(800, 1000)
    view.move(50, 50)
    view.show()

    app.exec()

    print(model.rootItem())


if __name__ == '__main__':
    test_model()