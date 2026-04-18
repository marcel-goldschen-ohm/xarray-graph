""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- moveRows: merge items?
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import XarrayDataTreeItem, AbstractTreeModel


class XarrayDataTreeModel(AbstractTreeModel):
    """ PyQt tree model interface for a Xarray DataTree.
    """

    MIME_TYPE = 'application/x-xarray-datatree-model'

    themes = {
        'default': {
            'icon': {
                'node': 'ph.folder-thin',
                'data_var': 'ph.cube-thin',
                'coord': 'ph.list-numbers-thin',
                'index_coord': 'ph.asterisk-thin',
                'unknown': 'fa6s.question',
            },
            'color': {
                'node': None, # None -> use default text color
                'data_var': None,
                'coord': None,
                'inherited_coord': None,
                'unknown': None,
            },
        },
        'dark': {
            'color': {
                'node': '#e69f00',
                'data_var': '#56b4e9',
                'coord': '#cc79a7',
                # 'inherited_coord': '#cc79a780', # last 80 makes it 50% transparent
                'unknown': '#990000',
            },
        }
    }

    def setTheme(self, name: str) -> None:
        # color_scheme = QGuiApplication.styleHints().colorScheme()
        # if color_scheme == Qt.ColorScheme.Dark:
        #     pass
        # elif color_scheme == Qt.ColorScheme.Light:
        #     pass

        default_color = QApplication.palette().color(QPalette.ColorRole.Text)

        theme = XarrayDataTreeModel.themes[name]

        try:
            colors = theme['color']
        except KeyError:
            # if theme does not have colors, use default colors
            colors = XarrayDataTreeModel.themes['default']['color']

        self._node_color: QColor = QColor(colors['node'] or default_color)
        self._data_var_color: QColor = QColor(colors['data_var'] or default_color)
        self._coord_color: QColor = QColor(colors['coord'] or default_color)
        inherited_coord_color = colors.get('inherited_coord', None)
        if not inherited_coord_color:
            # if no inherited_coord color specified, use coord color but faded
            inherited_coord_color = QColor(self._coord_color)
            inherited_coord_color.setAlpha(128)  # make it 50% transparent
        self._inherited_coord_color: QColor = QColor(inherited_coord_color)
        self._unknown_color: QColor = QColor(colors['unknown'] or default_color)

        try:
            icons = theme['icon']
        except KeyError:
            # if theme does not have icons, use default icons
            icons = XarrayDataTreeModel.themes['default']['icon']

        self._node_icon: QIcon = qta.icon(icons['node'], color=self._node_color)
        self._data_var_icon: QIcon = qta.icon(icons['data_var'], color=self._data_var_color)
        self._coord_icon: QIcon = qta.icon(icons['coord'], color=self._coord_color)
        self._index_coord_icon: QIcon = qta.icon(icons['index_coord'], color=self._coord_color)
        self._inherited_coord_icon: QIcon = qta.icon(icons['coord'], color=self._inherited_coord_color)
        self._inherited_index_coord_icon: QIcon = qta.icon(icons['index_coord'], color=self._inherited_coord_color)
        self._unknown_icon: QIcon = qta.icon(icons['unknown'], color=self._unknown_color)

        self._theme = name

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['DataTree', 'Details']

        # parts of datatree to show
        self._is_data_vars_visible: bool = True
        self._is_coords_visible: bool = True
        self._is_inherited_coords_visible: bool = False
        self._is_details_column_visible: bool = True

        # theme
        # self.setTheme('default')
        self.setTheme('dark')

        # setup item tree
        datatree: xr.DataTree = xr.DataTree()
        self._root_item = XarrayDataTreeItem(datatree)
    
    def treeData(self) -> xr.DataTree:
        """ Get the datatree.
        """
        root_item: XarrayDataTreeItem = self.rootItem()
        return root_item.data()
    
    def setTreeData(self, data: xr.DataTree) -> None:
        """ Set the datatree.
        """
        new_root_item = XarrayDataTreeItem(data)
        self._rebuildItemSubtree(new_root_item)
        self.setRootItem(new_root_item)
    
    def _rebuildItemSubtree(self, item: XarrayDataTreeItem) -> None:
        item.rebuildSubtree(
            include_data_vars=self.isDataVarsVisible(),
            include_coords=self.isCoordsVisible(),
            include_inherited_coords=self.isInheritedCoordsVisible()
        )
    
    def reset(self) -> None:
        """ Reset the model.
        """
        self.beginResetModel()
        self._rebuildItemSubtree(self._root_item)
        self.endResetModel()
    
    def isDataVarsVisible(self) -> bool:
        return self._is_data_vars_visible
    
    def setDataVarsVisible(self, visible: bool) -> None:
        if visible == self.isDataVarsVisible():
            return
        self.beginResetModel()
        self._is_data_vars_visible = visible
        self._rebuildItemSubtree(self._root_item)
        self.endResetModel()
    
    def isCoordsVisible(self) -> bool:
        return self._is_coords_visible
    
    def setCoordsVisible(self, visible: bool) -> None:
        if visible == self.isCoordsVisible():
            return
        self.beginResetModel()
        self._is_coords_visible = visible
        self._rebuildItemSubtree(self._root_item)
        self.endResetModel()
    
    def isInheritedCoordsVisible(self) -> bool:
        return self._is_inherited_coords_visible
    
    def setInheritedCoordsVisible(self, visible: bool) -> None:
        if visible == self.isInheritedCoordsVisible():
            return
        self.beginResetModel()
        self._is_inherited_coords_visible = visible
        self._rebuildItemSubtree(self._root_item)
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
                elif item.isIndexCoord():
                    if item.isInheritedCoord():
                        return self._inherited_index_coord_icon
                    return self._index_coord_icon
                elif item.isCoord():
                    if item.isInheritedCoord():
                        return self._inherited_coord_icon
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
            parent_node: xr.DataTree = item.parentNode()
            # ensure no name conflict with existing objects
            if new_name in parent_node:
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
                # update item name in branch
                branch_root_item: XarrayDataTreeItem = item.root()[branch_root.path.strip('/')]
                branch_item: XarrayDataTreeItem
                for branch_item in branch_root_item.subtree_depth_first():
                    if branch_item._varname == old_name:
                        branch_item._varname = new_name
                # self._updateSubtreeItems(branch_root_item)
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
            self._updateSubtreeItems(parent_item)
        return success
    
    def insertItems(self, items: list[XarrayDataTreeItem], row: int, parent_item: XarrayDataTreeItem) -> bool:
        if not items:
            return False

        if not parent_item.isNode():
            # raise ValueError('Can only insert items into nodes.')
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot insert items in non-node "{parent_item.path()}".'
            QMessageBox.warning(parent_widget, title, text)
            return False

        # insert items one at a time (because actual insertion position may differ from requested position to maintain data type order)
        inserted_items: list[XarrayDataTreeItem] = []
        parent_keys: list[str] = list(parent_item._node.keys())
        skip_all_conflicts = False
        name_conflict_default_action = None
        for item in items:
            # check conflicts
            conflict = None
            if item.parent is not None:
                conflict = f'Cannot insert non-orphan "{item.path()}".'
            elif parent_item.hasAncestor(item):
                conflict = f'Cannot insert "{item.path()}" into its own subtree at "{parent_item.path()}".'
            elif parent_item._node.has_data and item._node.has_data:
                # check alignment conflict
                try:
                    data = item.data()
                    if isinstance(data, xr.DataTree):
                        data = data.dataset
                    xr.align(parent_item._node.dataset, data, join='exact')
                except:
                    conflict = f'"{item.path()}" is not aligned with "{parent_item.path()}".'
            if conflict:
                if skip_all_conflicts:
                    continue
                parent_widget: QWidget = QApplication.focusWidget()
                title = 'Conflict'
                text = conflict
                dlg = ConflictDialog(parent_widget, title, text)
                if dlg.exec() == QDialog.DialogCode.Rejected:
                    # abort
                    break
                # skip
                skip_all_conflicts = dlg.skipAll()
                continue

            # check name conflict
            name_conflict = None
            item_name = item.name()
            if '/' in item_name:
                name_conflict = f'"{item_name}" is not a valid DataTree name, which cannot contain "/".'
            elif item_name in parent_keys:
                name_conflict = f'"{item_name}" already exists in "{parent_item.path()}".'
            if name_conflict:
                action = name_conflict_default_action
                if action is None:
                    parent_widget: QWidget = QApplication.focusWidget()
                    title = 'Name Conflict'
                    text = name_conflict
                    dlg = NameConflictDialog(parent_widget, title, text)
                    dlg._merge_button.setEnabled(False) # TODO
                    if dlg.exec() == QDialog.DialogCode.Rejected:
                        # abort
                        break
                    action = dlg.selectedAction()
                    if dlg.applyToAll():
                        name_conflict_default_action = action
                if action == 'Overwrite':
                    # remove item to be overwritten in parent
                    item_to_remove: XarrayDataTreeItem = parent_item[item_name]
                    row_to_remove = item_to_remove.row()
                    parent_index = self.indexFromItem(parent_item)
                    success = super().removeRows(row_to_remove, 1, parent_index)
                    if not success:
                        # skip
                        continue
                    if row_to_remove < row:
                        row -= 1
                elif action == 'Merge':
                    # TODO
                    pass
                elif action == 'Keep Both':
                    new_name = xarray_utils.unique_name(item_name, parent_keys)
                    item.setName(new_name)
                elif action == 'Skip':
                    continue

            # insert item
            row_for_item = XarrayDataTreeItem._findInsertionIndex(parent_item, item, row)
            success = super().insertItems([item], row_for_item, parent_item)
            if success:
                inserted_items.append(item)
                parent_keys.append(item.name())
                if row_for_item <= row:
                    row += 1
            else:
                # TODO: how should we handle failed insertions?
                pass
        
        # update inserted item subtrees (e.g., for inherited coords that may need to be added/removed in subtree after insertion)
        for item in inserted_items:
            self._updateSubtreeItems(item)
        
        # !! does not check success of each insertItems() call
        return len(inserted_items) > 0
    
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
        
        src_items: list[XarrayDataTreeItem] = src_parent_item.children[src_row: src_row + count]

        # move items one at a time (because actual insertion position may differ from requested position to maintain data type order)
        moved_items: list[XarrayDataTreeItem] = []
        src_parent_keys: list[str] = list(src_parent_item._node.keys())
        dst_parent_keys: list[str] = list(dst_parent_item._node.keys())
        skip_all_conflicts = False
        name_conflict_default_action = None
        for src_item in src_items:
            # check conflicts
            conflict = None
            if dst_parent_item.hasAncestor(src_item):
                conflict = f'Cannot move "{src_item.path()}" to its own descendent "{dst_parent_item.path()}".'
            elif dst_parent_item._node.has_data and src_item._node.has_data:
                # check alignment conflict
                try:
                    src_data = src_item.data()
                    if isinstance(src_data, xr.DataTree):
                        src_data = src_data.dataset
                    xr.align(dst_parent_item._node.dataset, src_data, join='exact')
                except:
                    conflict = f'"{src_item.path()}" is not aligned with "{dst_parent_item.path()}".'
            if conflict:
                if skip_all_conflicts:
                    continue
                parent_widget: QWidget = QApplication.focusWidget()
                title = 'Conflict'
                text = conflict
                dlg = ConflictDialog(parent_widget, title, text)
                if dlg.exec() == QDialog.DialogCode.Rejected:
                    # abort
                    break
                # skip
                skip_all_conflicts = dlg.skipAll()
                continue

            # check name conflict
            name_conflict = None
            src_item_name = src_item.name()
            if '/' in src_item_name:
                name_conflict = f'"{src_item_name}" is not a valid DataTree name, which cannot contain "/".'
            elif src_item_name in dst_parent_keys:
                name_conflict = f'"{src_item_name}" already exists in "{dst_parent_item.path()}".'
            if name_conflict:
                action = name_conflict_default_action
                if action is None:
                    parent_widget: QWidget = QApplication.focusWidget()
                    title = 'Name Conflict'
                    text = name_conflict
                    dlg = NameConflictDialog(parent_widget, title, text)
                    dlg._merge_button.setEnabled(False) # TODO
                    if dlg.exec() == QDialog.DialogCode.Rejected:
                        # abort
                        break
                    action = dlg.selectedAction()
                    if dlg.applyToAll():
                        name_conflict_default_action = action
                if action == 'Overwrite':
                    # remove item to be overwritten in dst parent
                    dst_item_to_remove: XarrayDataTreeItem = dst_parent_item[src_item_name]
                    row_to_remove = dst_item_to_remove.row()
                    success = super().removeRows(row_to_remove, 1, dst_parent_index)
                    if not success:
                        # skip
                        continue
                    if row_to_remove < dst_row:
                        dst_row -= 1
                elif action == 'Merge':
                    # TODO
                    pass
                elif action == 'Keep Both':
                    # !! Since rename ocurs before move, it must consider both src and dst parent keys to avoid conflicts. Better would be to rename mid-move after orphaning from src parent but before inserting into dst parent.
                    new_name = xarray_utils.unique_name(src_item_name, dst_parent_keys + src_parent_keys)
                    src_item.setName(new_name)
                elif action == 'Skip':
                    continue

            # move src_item
            dst_row_for_item = XarrayDataTreeItem._findInsertionIndex(dst_parent_item, src_item, dst_row)
            # print(f'moving {src_item.path()} from {src_parent_item.path()} to {dst_parent_item.path()} at row {dst_row} -> {dst_row_for_item}')
            success = super().moveRows(src_parent_index, src_item.row(), 1, dst_parent_index, dst_row_for_item)
            if success:
                moved_items.append(src_item)
                dst_parent_keys.append(src_item.name())
                if dst_row_for_item < dst_row:
                    dst_row += 1
            else:
                # TODO: how should we handle failed moves?
                pass
        
        # update moved item subtrees (e.g., for inherited coords that may need to be added/removed in subtree after move)
        for item in moved_items:
            self._updateSubtreeItems(item)
        
        # !! does not check success of each insertItems() call
        return True

    def _visibleRowNames(self, item: XarrayDataTreeItem) -> list[str]:
        if not item.isNode():
            return []
        return xarray_utils.ordered_node_keys(
            item._node,
            include_data_vars=self.isDataVarsVisible(),
            include_coords=self.isCoordsVisible(),
            include_inherited_coords=self.isInheritedCoordsVisible()
        )
        # node: xr.DataTree = item.data()
        # names: list[str] = []
        # for data_type in tuple(XarrayDataTreeItem.DataType):
        #     if data_type == XarrayDataTreeItem.DataType.INDEX_COORD:
        #         if self.isCoordsVisible():
        #             names += list(node.xindexes)
        #     elif data_type == XarrayDataTreeItem.DataType.INHERITED_COORD:
        #         if self.isCoordsVisible() and self.isInheritedCoordsVisible():
        #             names += list(node._inherited_coords_set())
        #     elif data_type == XarrayDataTreeItem.DataType.COORD:
        #         if self.isCoordsVisible():
        #             names += [name for name in node.coords if (name not in node.xindexes) and (name not in node._inherited_coords_set())]
        #     elif data_type == XarrayDataTreeItem.DataType.DATA_VAR:
        #         if self.isDataVarsVisible():
        #             names += list(node.data_vars)
        #     elif data_type == XarrayDataTreeItem.DataType.NODE:
        #          names += list(node.children)
        # return names
    
    def _updateSubtreeItems(self, parent_item: XarrayDataTreeItem) -> None:
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
                    inherited_coord_item = XarrayDataTreeItem(node, name)
                    row: int = row_names.index(name)
                    if row == -1:
                        row = len(item.children)
                    self.beginInsertRows(index, row, row)
                    item.insertChild(row, inherited_coord_item)
                    self.endInsertRows()
    
    # @staticmethod
    # def _itemBlocks(items: list[XarrayDataTreeItem]) -> list[list[XarrayDataTreeItem]]:
    #     """ Group items by data type, parent, and contiguous rows.

    #     Each block can be input to removeRows() or moveRows().
    #     Blocks are ordered depth-first. Typically you should remove/move blocks in reverse depth-first order to ensure insertion row indices remain valid after handling each block.
    #     """
    #     # so we don't modify the input list
    #     items = items.copy()

    #     # order by data type
    #     data_type_order = tuple(XarrayDataTreeItem.DataType)
    #     items.sort(key=lambda item: data_type_order.index(item.dataType()))

    #     # order items depth-first so that it is easier to group them into blocks
    #     items.sort(key=lambda item: item.level())
    #     items.sort(key=lambda item: item.siblingIndex())

    #     # group items into blocks by [data type,] parent, and contiguous rows
    #     blocks: list[list[XarrayDataTreeItem]] = [[items[0]]]
    #     for item in items[1:]:
    #         added_to_block = False
    #         for block in blocks:
    #             if (item.parent is block[0].parent) and (item.dataType() == block[0].dataType()):
    #                 if item.siblingIndex() == block[-1].siblingIndex() + 1:
    #                     block.append(item)
    #                 else:
    #                     blocks.append([item])
    #                 added_to_block = True
    #                 break
    #         if not added_to_block:
    #             blocks.append([item])
    #     return blocks


class ConflictDialog(QDialog):

    def __init__(self, parent: QWidget, title: str, text: str):
        super().__init__(parent, modal=True)
        
        self.setWindowTitle(title)
        vbox = QVBoxLayout(self)

        self._text_field = QTextEdit(readOnly=True, plainText=text)
        vbox.addWidget(self._text_field)
        vbox.addSpacing(10)

        self._skip_button = QRadioButton('Skip')
        self._skip_all_button = QRadioButton('Skip All')
        self._action_button_group = QButtonGroup()
        self._action_button_group.addButton(self._skip_button)
        self._action_button_group.addButton(self._skip_all_button)
        self._skip_button.setChecked(True)
        vbox.addWidget(self._skip_button)
        vbox.addWidget(self._skip_all_button)
        vbox.addSpacing(10)

        buttons = QDialogButtonBox()
        self._continue_button: QPushButton = buttons.addButton('Skip & Continue', QDialogButtonBox.ButtonRole.AcceptRole)
        self._cancel_button: QPushButton = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._continue_button.setAutoDefault(False)
        self._cancel_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        vbox.addWidget(buttons)
    
    def skipAll(self) -> bool:
        return self._skip_all_button.isChecked()


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
    
    def selectedAction(self) -> str:
        """ Return the selected action button's text.
        """
        button: QRadioButton = self._action_button_group.checkedButton()
        if button is not None:
            return button.text()
    
    def applyToAll(self) -> bool:
        return self._apply_to_all_checkbox.isChecked()


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
    dt['rasm/rasm'] = xr.tutorial.load_dataset('rasm')
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