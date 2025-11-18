""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- movePaths/copyPaths
    - check for attempt to move or copy a path to itself
    - reorder dst variables after move/copy
    - test conflicts
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph import xarray_utils


class XarrayDataTreeModel(QAbstractItemModel):
    """ PyQt tree model interface for a Xarray DataTree.
    """

    def __init__(self, *args, **kwargs):
        datatree: xr.DataTree = kwargs.pop('datatree', xr.DataTree())
        super().__init__(*args, **kwargs)

        self._root: xr.DataTree = datatree

        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['DataTree', 'Details']

        self._is_data_vars_visible: bool = True 
        self._is_coords_visible: bool = False
        self._is_inherited_coords_visible: bool = True
        self._is_details_column_visible: bool = False

        # drag-and-drop support for moving tree items within the tree or copying them to other tree models
        self._supportedDropActions: Qt.DropActions = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

        # icons
        self._datatree_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')
    
    def reset(self) -> None:
        """ Reset the model.
        """
        self.beginResetModel()
        self.endResetModel()

    def datatree(self) -> xr.DataTree:
        """ Get the model's current datatree.
        """
        return self._root
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        """ Reset the model to the input datatree.
        """
        self.beginResetModel()
        self._root = datatree
        self.endResetModel()
    
    def isDataVarsVisible(self) -> bool:
        return self._is_data_vars_visible
    
    def setDataVarsVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._is_data_vars_visible = visible
        self.endResetModel()
    
    def isCoordsVisible(self) -> bool:
        return self._is_coords_visible
    
    def setCoordsVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._is_coords_visible = visible
        self.endResetModel()
    
    def isInheritedCoordsVisible(self) -> bool:
        return self._is_inherited_coords_visible
    
    def setInheritedCoordsVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._is_inherited_coords_visible = visible
        self.endResetModel()
    
    def isDetailsColumnVisible(self) -> bool:
        return self._is_details_column_visible
    
    def setDetailsColumnVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._is_details_column_visible = visible
        self.endResetModel()
    
    def pathFromIndex(self, index: QModelIndex = QModelIndex()) -> str:
        """ Get the datatree path associated with index.
        
        The path is determined from the parent DataTree node in index.internalPointer() and index.row() which is used to index into the list of visible child rows for the parent node.
        """
        if not index.isValid():
            return self._root.path
        parent_node: xr.DataTree = index.internalPointer()
        row_names = self.visibleRowNames(parent_node)
        name = row_names[index.row()]
        parent_path = parent_node.path.rstrip('/')
        return f'{parent_path}/{name}'
    
    def indexFromPath(self, path: str, column: int = 0) -> QModelIndex:
        """ Get the index associated with the datatree path.

        Path corresponds to a row in the model, so can optionally specify the colummn.
        By default, the first column is assumed.
        """
        if not path.startswith('/'):
            path = f'{self._root.path.rstrip('/')}/{path}'
        if path == self._root.path:
            return QModelIndex()
        obj: xr.DataTree | xr.DataArray = self._root[path]
        if isinstance(obj, xr.DataTree):
            # should always be defined since obj is not the root node
            parent_node: xr.DataTree = obj.parent
        elif isinstance(obj, xr.DataArray):
            # remove name and trailing slash (if empty, use '/')
            parent_path: str = path[:-len(obj.name)-1] or '/'
            parent_node: xr.DataTree = self._root[parent_path]
        row_names = self.visibleRowNames(parent_node)
        row: int = row_names.index(obj.name)
        # The index internal pointer stores a reference to the parent node.
        # The object associated with the index is row-th item in the list of visible child items of the parent node.
        return self.createIndex(row, column, parent_node)
    
    def parentPath(self, path: str) -> str | None:
        """ Get the parent path for a given path.
        """
        if path == '/':
            return None
        parts = path.split('/')
        parent_path = '/'.join(parts[:-1])
        return parent_path or '/'
    
    def visibleRowNames(self, node: xr.DataTree) -> list[str]:
        """ Ordered list of names for data_vars (if visible), coords (if visible), and children in node.

        Coords are ordered with index coords listed first in data dimension order, followed by non-index coords.
        """
        names = []
        if self.isDataVarsVisible():
            names += list(node.data_vars)
        if self.isCoordsVisible():
            all_coords = list(node.coords) # includes inherited coords
            index_coords = list(node.indexes) # includes inherited coords
            inherited_coords = node._inherited_coords_set()
            # start with index coords
            dims = xarray_utils.get_ordered_dims([node])
            for dim in dims:
                if dim not in index_coords:
                    continue
                if self.isInheritedCoordsVisible() or (dim not in inherited_coords):
                    names.append(dim)
            # then add non-index coords
            for coord in all_coords:
                if coord in names:
                    continue
                if self.isInheritedCoordsVisible() or (coord not in inherited_coords):
                    names.append(coord)
        names += list(node.children)
        return names
    
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        parent_path: str = self.pathFromIndex(parent_index)
        parent_obj: xr.DataTree | xr.DataArray = self._root[parent_path]
        if isinstance(parent_obj, xr.DataTree):
            return len(self.visibleRowNames(parent_obj))
        else:
            # no children for DataArrays
            return 0
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        if self.isDetailsColumnVisible():
            return 2
        return 1

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        path: str = self.pathFromIndex(index)
        parent_path: str = self.parentPath(path)
        return self.indexFromPath(parent_path)

    def index(self, row: int, column: int, parent_index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent_index):
            return QModelIndex()
        parent_path: str = self.pathFromIndex(parent_index)
        parent_node: xr.DataTree = self._root[parent_path]
        return self.createIndex(row, column, parent_node)

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
        
        if index.column() == 0:
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        elif index.column() == 1:
            # cannot edit details column
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            path: str = self.pathFromIndex(index)
            obj = self._root[path]
            if isinstance(obj, xr.DataTree):
                # can drag and drop onto DataTree items
                flags |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
            elif isinstance(obj, xr.DataArray):
                # can drag but not drop onto DataArray items
                flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            path: str = self.pathFromIndex(index)
            obj = self._root[path]
            if index.column() == 0:
                # main column
                return obj.name
            elif index.column() == 1:
                # details column
                if isinstance(obj, xr.DataTree):
                    sizes_str = ', '.join([f'{dim}: {size}' for dim, size in obj.dataset.sizes.items()])
                    return f'({sizes_str})'
                elif isinstance(obj, xr.DataArray):
                    parent_node: xr.DataTree = index.internalPointer()
                    if obj.name in parent_node.data_vars:
                        rep = str(parent_node.dataset)
                        i = rep.find('Data variables:')
                        i = rep.find(f' {obj.name} ', i)  # find var
                        i = rep.find('(', i)  # skip var name
                        j = rep.find('\n', i)
                        return rep[i:j] if j > 0 else rep[i:]
                    elif obj.name in parent_node.coords:
                        rep = str(parent_node.dataset)
                        i = rep.find('Coordinates:')
                        i = rep.find(f' {obj.name} ', i)  # find coord
                        i = rep.find('(', i)  # skip coord name
                        j = rep.find('\n', i)
                        return rep[i:j] if j > 0 else rep[i:]
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                path: str = self.pathFromIndex(index)
                obj = self._root[path]
                if isinstance(obj, xr.DataTree):
                    return self._datatree_icon
                elif isinstance(obj, xr.DataArray):
                    parent_node: xr.DataTree = index.internalPointer()
                    if obj.name in parent_node.data_vars:
                        return self._data_var_icon
                    elif obj.name in parent_node.coords:
                        return self._coord_icon

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
            # rename obj
            path: str = self.pathFromIndex(index)
            obj = self._root[path]
            old_name = obj.name
            new_name = str(value).strip()
            if old_name == new_name:
                # nothing to do
                return False
            if not new_name or '/' in new_name:
                msg = f'Name "{new_name}" is not a valid DataTree key. Must be a non-empty string without any path separators "/".'
                warn(msg)
                self.popupWarningDialog(msg)
                return False
            parent_node: xr.DataTree = index.internalPointer()
            if new_name in parent_node:
                msg = f'Name "{new_name}" already exists in parent DataTree.'
                warn(msg)
                self.popupWarningDialog(msg)
                return False
            if isinstance(obj, xr.DataTree):
                # update parent node's children mapping to rename child obj
                children = {}
                for name, child in parent_node.children.items():
                    if name == old_name:
                        name = new_name
                    children[name] = child
                parent_node.children = children
                self.dataChanged.emit(index, index)
            elif isinstance(obj, xr.DataArray):
                if old_name in parent_node.xindexes:
                    # rename dim along with coord in aligned branch
                    # branch starts from furthest ancestor that contains the dim as an index coord
                    dim_root_node = parent_node
                    for node in dim_root_node.parents:
                        if old_name in node.xindexes:
                            dim_root_node = node
                        else:
                            break
                    dim_root_node.dataset = dim_root_node.to_dataset().rename_dims({old_name: new_name})
                    # rename coord to match dim
                    dim_root_node.dataset = dim_root_node.to_dataset().rename_vars({old_name: new_name})
                    # the above does not rename dims in data_vars of child nodes, so do that here
                    for node in dim_root_node.subtree:
                        if node is dim_root_node:
                            continue
                        for name, data_var in node.data_vars.items():
                            if old_name in data_var.dims:
                                new_data_var = data_var.swap_dims({old_name: new_name})
                                node.dataset = node.to_dataset().assign({name: new_data_var})
                    # emit dataChanged for dim coord in entire aligned branch
                    for node in dim_root_node.subtree:
                        if node is dim_root_node or self.isInheritedCoordsVisible():
                            dim_index: QModelIndex = self.indexFromPath(f'{node.path}/{new_name}')
                            self.dataChanged.emit(dim_index, dim_index)
                    return True
                # rename array in parent node
                parent_node.dataset = parent_node.to_dataset().rename_vars({old_name: new_name})
                self.dataChanged.emit(index, index)
                return True
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
        return self._root.depth - self._root.level

    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        try:
            indexes: list[QModelIndex] = [self.index(row, 0, parent_index) for row in range(row, row + count)]
            paths: list[str] = [self.pathFromIndex(index) for index in indexes]
        except:
            return False
        
        self.beginRemoveRows(parent_index, row, row + count - 1)
        # as we know the rows are contiguous, begin/endRemoveRows is more efficient than begin/endResetModel
        self.removePaths(paths, update_model=False)
        self.endRemoveRows()
        return True
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        try:
            src_model: XarrayDataTreeModel = self
            dst_model: XarrayDataTreeModel = self
            src_indexes: list[QModelIndex] = [self.index(row, 0, src_parent_index) for row in range(src_row, src_row + count)]
            src_paths: list[str] = [self.pathFromIndex(index) for index in src_indexes]
            dst_parent_path = self.pathFromIndex(dst_parent_index)
        except:
            return False
        
        # begin/endMoveRows may fail due to changing dst_row based on data_var vs coord vs node type
        # so we resort to begin/endResetModel (see transferPaths)
        self.movePaths(src_model, src_paths, dst_model, dst_parent_path, dst_row)
        return True
    
    def removePaths(self, paths: list[str], update_model: bool = True) -> None:
        """ Remove items by their path.
        """
        # group paths by their parent node from deepest to shallowest so that moving/removing them in order does not change the paths of the remaining groups
        path_groups: dict[str, list[str]] = self._groupPathsByParentNode(paths)

        if update_model:
            self.beginResetModel()

        # remove paths one node at a time
        for parent_path, child_paths in path_groups.items():
            parent_node: xr.DataTree = self._root[parent_path]

            # remove nodes
            nodes_to_remove = [node for name, node in parent_node.children.items() if f'{parent_path}/{name}' in child_paths]
            for node in nodes_to_remove:
                node.orphan()
            
            # remove variables
            var_names_to_remove = [name for name in parent_node.variables if f'{parent_path}/{name}' in child_paths]
            parent_node.dataset = parent_node.to_dataset().drop_vars(var_names_to_remove)

        if update_model:
            self.endResetModel()
    
    def movePaths(self, src_model: XarrayDataTreeModel, src_paths: list[str], dst_model: XarrayDataTreeModel, dst_parent_path: str, dst_row: int, name_conflict: str = 'ask', update_model: bool = True) -> None:
        """ Move items between trees by their path.
        """
        src_datatree: xr.DataTree = src_model.datatree()
        dst_datatree: xr.DataTree = dst_model.datatree()
        dst_parent_node: xr.DataTree = dst_datatree[dst_parent_path]

        # group paths by their parent node from deepest to shallowest so that moving/removing them in order does not change the paths of the remaining groups
        src_path_groups: dict[str, list[str]] = src_model._groupPathsByParentNode(src_paths)

        if update_model:
            src_model.beginResetModel()
            if dst_model is not src_model:
                dst_model.beginResetModel()

        # transfer paths one node at a time
        abort = False
        for src_parent_path, src_child_paths in src_path_groups.items():
            src_parent_node: xr.DataTree = src_datatree[src_parent_path]

            # transfer nodes
            nodes_to_transfer = [node for name, node in src_parent_node.children.items() if f'{src_parent_path}/{name}' in src_child_paths]
            dst_keys = list(dst_parent_node.keys())
            for node in nodes_to_transfer:
                node.orphan()
                name = node.name
                # handle name conflict
                if name in dst_keys:
                    if name_conflict == 'ask':
                        focused_widget: QWidget = QApplication.focusWidget()
                        msg = f'"{name}" already exists in destination DataTree.'
                        dlg = NameConflictDialog(msg, focused_widget)
                        dlg._merge_button.setEnabled(False) # TODO: implement merge below
                        if dlg.exec() == QDialog.DialogCode.Rejected:
                            abort = True
                            break
                        this_name_conflict = dlg._action_button_group.checkedButton().text().lower()
                        apply_to_all_name_conflicts = dlg._apply_to_all_checkbox.isChecked()
                        if apply_to_all_name_conflicts:
                            name_conflict = this_name_conflict
                    else:
                        this_name_conflict = name_conflict.lower()
                    if this_name_conflict == 'overwrite':
                        pass # will be overwritten below
                    elif this_name_conflict == 'merge':
                        # TODO: implement merge
                        continue
                    elif this_name_conflict == 'keep both':
                        name = xarray_utils.unique_name(name, dst_keys)
                        dst_keys.append(name)
                    elif this_name_conflict == 'skip':
                        continue
                dst_node_path = f'{dst_parent_path}/{name}'
                dst_datatree[dst_node_path] = node
            if abort:
                break
            
            # transfer variables
            var_names_to_transfer = [name for name in src_parent_node.variables if f'{src_parent_path}/{name}' in src_child_paths]
            var_names_not_to_transfer = [name for name in src_parent_node.variables if f'{src_parent_path}/{name}' not in src_child_paths]
            dataset_to_transfer: xr.Dataset = src_parent_node.to_dataset().drop_vars(var_names_not_to_transfer)
            dst_dataset: xr.Dataset = dst_parent_node.to_dataset()
            # handle name conflicts (data_vars only, ignore coords)
            dst_keys = list(dst_parent_node.keys())
            for name in list(dataset_to_transfer.data_vars):
                if name in dst_keys:
                    if name_conflict == 'ask':
                        focused_widget: QWidget = QApplication.focusWidget()
                        msg = f'"{name}" already exists in destination DataTree.'
                        dlg = NameConflictDialog(msg, focused_widget)
                        if dlg.exec() == QDialog.DialogCode.Rejected:
                            abort = True
                            break
                        this_name_conflict = dlg._action_button_group.checkedButton().text().lower()
                        apply_to_all_name_conflicts = dlg._apply_to_all_checkbox.isChecked()
                        if apply_to_all_name_conflicts:
                            name_conflict = this_name_conflict
                    else:
                        this_name_conflict = name_conflict.lower()
                    if this_name_conflict == 'overwrite':
                        dst_dataset = dst_dataset.drop_vars([name])
                    elif this_name_conflict == 'merge':
                        pass # will be merged below
                    elif this_name_conflict == 'keep both':
                        new_name = xarray_utils.unique_name(name, dst_keys)
                        dst_keys.append(new_name)
                        dataset_to_transfer = dataset_to_transfer.rename_vars({name: new_name})
                    elif this_name_conflict == 'skip':
                        dataset_to_transfer = dataset_to_transfer.drop_vars([name])
            if abort:
                break
            try:
                dst_dataset = dst_dataset.merge(dataset_to_transfer, compat='no_conflicts', join='outer', combine_attrs='override')
                dst_parent_node.dataset = dst_dataset
                src_parent_node.dataset = src_parent_node.to_dataset().drop_vars(var_names_to_transfer)
            except:
                msg = f'Failed to transfer variables from {src_parent_path}'
                from warnings import warn
                warn(msg)
                self.popupWarningDialog(msg)

        if update_model:
            src_model.endResetModel()
            if dst_model is not src_model:
                dst_model.endResetModel()
    
    def copyPaths(self, src_model: XarrayDataTreeModel, src_paths: list[str], dst_model: XarrayDataTreeModel, dst_parent_path: str, dst_row: int, deep: bool = True, update_model: bool = True) -> None:
        """ Move items between trees by their path.
        """
        src_datatree: xr.DataTree = src_model.datatree()
        dst_datatree: xr.DataTree = dst_model.datatree()
        dst_parent_node: xr.DataTree = dst_datatree[dst_parent_path]

        # group paths by their parent node from deepest to shallowest so that moving/removing them in order does not change the paths of the remaining groups
        src_path_groups: dict[str, list[str]] = src_model._groupPathsByParentNode(src_paths)

        if update_model:
            dst_model.beginResetModel()

        # copy paths one node at a time
        for src_parent_path, src_child_paths in src_path_groups.items():
            src_parent_node: xr.DataTree = src_datatree[src_parent_path]

            # copy nodes
            nodes_to_copy = [node for name, node in src_parent_node.children.items() if f'{src_parent_path}/{name}' in src_child_paths]
            for node in nodes_to_copy:
                name = node.name
                # name = xarray_utils.unique_name(node.name, list(dst_parent_node.keys()))
                dst_node_path = f'{dst_parent_path}/{name}'
                dst_datatree[dst_node_path] = node.copy(deep=deep)
            
            # copy variables
            var_names_to_copy = [name for name in src_parent_node.variables if f'{src_parent_path}/{name}' in src_child_paths]
            var_names_not_to_copy = [name for name in src_parent_node.variables if f'{src_parent_path}/{name}' not in src_child_paths]
            dataset_copy: xr.Dataset = src_parent_node.to_dataset().drop_vars(var_names_not_to_copy).copy(deep=deep)
            try:
                dst_parent_node.dataset = dst_parent_node.to_dataset().merge(dataset_copy, compat='no_conflicts', join='outer', combine_attrs='override')
            except:
                msg = f'Failed to copy variables from {src_parent_path}'
                from warnings import warn
                warn(msg)
                self.popupWarningDialog(msg)

        if update_model:
            dst_model.endResetModel()
    
    def _groupPathsByParentNode(self, paths: list[str]) -> dict[str, list[str]]:
        # group paths by their parent node
        # path_groups[parent_path] = [child_paths]
        path_groups: dict[str, list[str]] = {}
        for path in paths:
            parent_path: str = self.parentPath(path)
            if parent_path in path_groups:
                path_groups[parent_path].append(path)
            else:
                path_groups[parent_path] = [path]

        # order groups by parent path from leaves to root so that moving/removing them in order does not change the paths of the remaining groups
        parent_paths: list[str] = list(path_groups)
        # sort by depth (more slashes means deeper in the tree)
        parent_paths.sort(key=lambda p: p.count('/'), reverse=True)
        path_groups = {parent_path: path_groups[parent_path] for parent_path in parent_paths}
        return path_groups
    
    # def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
    #     try:
    #         if count <= 0:
    #             return False
    #         n_rows: int = self.rowCount(parent_index)
    #         if (row < 0) or (row + count > n_rows):
    #             return False
        
    #         parent_path: xr.DataTree = self.pathFromIndex(parent_index)
    #         parent_node: xr.DataTree = self._root[parent_path]
    #         names_to_remove: list[str] = self.visibleRowNames(parent_node)[row:row + count]
    #         vars_to_remove: list[str] = [name for name in names_to_remove if name in parent_node.data_vars]
    #         coords_to_remove: list[str] = [name for name in names_to_remove if name in parent_node.coords]
    #         nodes_to_remove: list[str]= [name for name in names_to_remove if name in parent_node.children]
    #     except:
    #         return False
        
    #     self.beginRemoveRows(parent_index, row, row + count - 1)
    #     if vars_to_remove or coords_to_remove:
    #         parent_node.dataset = parent_node.to_dataset().drop_vars(vars_to_remove + coords_to_remove)
    #     if nodes_to_remove:
    #         parent_node.children = {name: node for name, node in parent_node.children.items() if name not in nodes_to_remove}
    #     self.endRemoveRows()
    #     return True
    
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
    
    # def movePaths(self, src_paths: list[str], dst_parent_path: str, dst_row: int) -> None:
    #     """ Move items within tree by their path.
    #     """
    #     # print('movePaths(', src_paths, dst_parent_path, dst_row, ')', flush=True)
    #     try:
    #         dst_parent_node: xr.DataTree = self._root[dst_parent_path]
    #     except KeyError:
    #         # Invalid dst_parent_path
    #         return
    #     dst_parent_index: QModelIndex = self.indexFromPath(dst_parent_path)
    #     dst_num_rows: int = self.rowCount(dst_parent_index)
    #     if dst_row < 0 or dst_row > dst_num_rows:
    #         # append rows
    #         dst_row = dst_num_rows
        
    #     # group paths for moving block by contiguous row block
    #     src_path_groups: dict[str, list[list[int]]] = self.groupPaths(src_paths)
    #     for src_parent_path, row_blocks in src_path_groups.items():
    #         for row_block in row_blocks:
    #             row: int = row_block[0]
    #             count: int = len(row_block)
    #             src_parent_index: QModelIndex = self.indexFromPath(src_parent_path)
    #             self.moveRows(src_parent_index, row, count, dst_parent_index, dst_row)
    
    # def groupPaths(self, paths: list[str]) -> dict[str, list[list[int]]]:
    #     """ Group paths by their parent node and contiguous rows block.
        
    #     This is used to prepare for moving or copying paths in the tree.
    #     Note: paths should never contain the root path '/'.
    #     """
    #     # groups[parent path][[block row indices], ...]
    #     groups: dict[str, list[list[int]]] = {}
    #     for path in paths:
    #         parent_path: str = self.parentPath(path)
    #         if parent_path not in groups:
    #             groups[parent_path] = []
    #         parent_node: xr.DataTree = self._root[parent_path]
    #         row_names: list[str] = self.visibleRowNames(parent_node)
    #         name = path.split('/')[-1]
    #         row = row_names.index(name)
    #         added = False
    #         rows_group: list[int]
    #         for rows_group in groups[parent_path]:
    #             if row == rows_group[0] - 1:
    #                 rows_group.insert(0, row)
    #                 added = True
    #                 break
    #             elif row == rows_group[-1] + 1:
    #                 rows_group.append(row)
    #                 added = True
    #                 break
    #         if not added:
    #             # start a new group of rows
    #             groups[parent_path].append([row])

    #     # order groups by parent path from leaves to root so that moving/removing them in order does not change the paths of the remaining groups
    #     parent_paths: list[str] = list(groups.keys())
    #     parent_paths.sort(key=lambda p: p.count('/'), reverse=True)  # sort by depth (more slashes means deeper in the tree)
    #     groups = {parent_path: groups[parent_path] for parent_path in parent_paths}

    #     # order row blocks from last block to first block so that removing them in order does not change the row indices of the remaining blocks
    #     for parent_path, row_blocks in groups.items():
    #         row_blocks.sort(key=lambda block: block[0], reverse=True)
        
    #     return groups
    
    # def _reorderVariables(self, node: xr.DataTree, var_order: list[str] = None) -> None:
    #     if var_order is None:
    #         ordered_vars = node.variables
    #     else:
    #         ordered_vars = {name: node.variables[name] for name in ordered_vars if name in node.variables}
    #         # unordered variables are appended
    #         for name in node.variables:
    #             if name not in ordered_vars:
    #                 ordered_vars[name] = node.variables[name]
        
    #     ordered_data_vars = {name: var for name, var in ordered_vars.items() if name in node.data_vars}
    #     ordered_coords = {name: var for name, var in ordered_vars.items() if name in node.coords}
        
    #     ds: xr.Dataset = node.to_dataset()
    #     node.dataset = xr.Dataset(data_vars=ordered_data_vars, coords=ordered_coords, attrs=ds.attrs)
    
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
            return None
        if self.datatree() is None:
            return None
        
        paths: list[str] = []
        for index in indexes:
            if not index.isValid():
                continue
            path: str = self.pathFromIndex(index)
            if path not in paths:
                paths.append(path)
        if not paths:
            return None
        
        return XarrayDataTreeMimeData(self, paths)

    def dropMimeData(self, data: XarrayDataTreeMimeData, action: Qt.DropAction, row: int, column: int, parent_index: QModelIndex) -> bool:
        # print('dropMimeData')
        if not isinstance(data, XarrayDataTreeMimeData):
            return False
        src_model: XarrayDataTreeModel = data.model
        src_paths: list[str] = data.paths
        if not src_model or not src_paths:
            return False
        src_datatree: xr.DataTree = src_model.datatree()
        if not src_datatree:
            return False

        # move paths to the destination (row-th child of parent_index)
        dst_model: XarrayDataTreeModel = self
        dst_datatree: xr.DataTree = dst_model.datatree()
        if not dst_datatree:
            return False
        dst_parent_path: str = self.pathFromIndex(parent_index)
        
        # check for any name and alignment conflicts and decide what to do with conflicts
        # dst_parent_node: xr.DataTree = dst_datatree[dst_parent_path]
        # TODO... if we do this here, then maybe it's not needed in moveRows?

        # store the view state of the dragged items under their destination paths
        for path, state in data.src_view_state.items():
            for src_path in src_paths:
                if path.startswith(src_path):
                    src_parent_path: str = src_model.parentPath(src_path)
                    if src_parent_path == '/':
                        path = dst_parent_path.rstrip('/') + path
                    else:
                        path = path.replace(src_parent_path, dst_parent_path.rstrip('/'), 1)
                    data.dst_view_state[path] = state
                    break

        self.movePaths(src_model, src_paths, dst_model, dst_parent_path, row)

        # !? If we return True, the model will attempt to remove rows.
        # As we already completely handled the move, this will corrupt our model, so return False.
        return False
    
    def popupWarningDialog(self, text: str) -> None:
        focused_widget: QWidget = QApplication.focusWidget()
        QMessageBox.warning(focused_widget, 'Warning', text)


class XarrayDataTreeMimeData(QMimeData):
    """ Custom MIME data class for Xarray DataTree objects.

    This class allows storing a reference to an XarrayDataTreeModel object in the MIME data.
    It can be used to transfer DataTree or DataArray items within and between XarrayDataTreeModels in the same program/process.

    Note:
    This approach probably won't work if you need to pass items between XarrayDataTreeModels in separate programs/processes.
    If you really need to do this, you need to somehow serialize the datatree or items thereof (maybe with pickle), pass the serialized bytes in the drag MIME data, then deserialize back to datatree items on drop.
    """

    MIME_TYPE = 'application/x-xarray-datatree-model'

    def __init__(self, model: XarrayDataTreeModel, paths: list[str]):
        QMimeData.__init__(self)

        # these define the datatree items being dragged
        self.model: XarrayDataTreeModel = model
        self.paths: list[str] = paths

        # The view state of the dragged items and all of their descendents.
        # Mapping from path to state dict.
        # To be defined in the view's dragEnter() event callback.
        # Used to restore the view of the dragged items in the dropped view's dropEvent() callback.
        self.src_view_state: dict[str, dict] = {}
        self.dst_view_state: dict[str, dict] = {}

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
    print(dt)

    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setDatatree(dt)

    # test indexFromPath and pathFromIndex
    node: xr.DataTree
    for node in dt.subtree:
        index: QModelIndex = model.indexFromPath(node.path)
        path: str = model.pathFromIndex(index)
        assert(node.path == path)
        # print('round-trip:', node.path, '->', path, flush=True)
        for name in node.data_vars:
            index: QModelIndex = model.indexFromPath(node.path + '/' + name)
            path: str = model.pathFromIndex(index)
            assert(node.path + '/' + name == path)
            # print('round-trip:', node.path + '/' + name, '->', path, flush=True)
        for name in node.coords:
            index: QModelIndex = model.indexFromPath(node.path + '/' + name)
            path: str = model.pathFromIndex(index)
            assert(node.path + '/' + name == path)
            # print('round-trip:', node.path + '/' + name, '->', path, flush=True)

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