""" PyQt tree model interface for a Xarray.DataTree.

TODO:
- handle name and alignment conflicts when moving rows
- optional merging of data arrays when moving rows
- renaming coords also renames dimensions of same name?
- rename dimensions (propagate throughout branch or tree). Optionally rename coords of same name?
- implement moving/copying rows between different models
- handle unneeded inherited coords after moving rows
- remove debugging print statements
"""

from __future__ import annotations
from warnings import warn
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta


class XarrayDataTreeModel(QAbstractItemModel):
    """ PyQt tree model interface for a Xarray DataTree.
    """

    def __init__(self, datatree: xr.DataTree, parent: QObject = None):
        QAbstractItemModel.__init__(self, parent)

        self._datatree: xr.DataTree = datatree

        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['DataTree', 'Details']

        self._isVariablesVisible: bool = True
        self._isCoordinatesVisible: bool = True
        self._isDetailsColumnVisible: bool = True

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
        return self._datatree
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        """ Reset the model to the input datatree.
        """
        self.beginResetModel()
        self._datatree = datatree
        self.endResetModel()
    
    def isDataVarsVisible(self) -> bool:
        return self._isVariablesVisible
    
    def setDataVarsVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._isVariablesVisible = visible
        self.endResetModel()
    
    def isCoordsVisible(self) -> bool:
        return self._isCoordinatesVisible
    
    def setCoordsVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._isCoordinatesVisible = visible
        self.endResetModel()
    
    def isDetailsColumnVisible(self) -> bool:
        return self._isDetailsColumnVisible
    
    def setDetailsColumnVisible(self, visible: bool) -> None:
        self.beginResetModel()
        self._isDetailsColumnVisible = visible
        self.endResetModel()
    
    def pathFromIndex(self, index: QModelIndex = QModelIndex()) -> str:
        """ Get the datatree path associated with index.

        The path is determined from the parent DataTree node in index.internalPointer() and index.row() which is used to index into the list of visible child rows for the parent node. 
        """
        if not index.isValid():
            return '/'
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
        if path == '/':
            return QModelIndex()  # root index
        obj = self._datatree[path]
        name: str = obj.name
        if isinstance(obj, xr.DataTree):
            parent_node: xr.DataTree = obj.parent  # should always be defined since path is not '/' (root)
        elif isinstance(obj, xr.DataArray):
            parent_path: str = path[:-len(name)-1] or '/' # remove name and trailing slash (if empty, use '/')
            parent_node: xr.DataTree = self._datatree[parent_path]
        row_names = self.visibleRowNames(parent_node)
        row: int = row_names.index(name)
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
        """
        names = []
        if self.isDataVarsVisible():
            names += list(node.data_vars)
        if self.isCoordsVisible():
            names += list(node.coords)
        names += list(node.children)
        return names
    
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        # if parent_index.column() > 0:
        #     return 0
        parent_path: str = self.pathFromIndex(parent_index)
        parent_obj: xr.DataTree | xr.DataArray = self._datatree[parent_path]
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
        # if parent_index.isValid() and parent_index.column() != 0:
        #     return QModelIndex()
        parent_path: str = self.pathFromIndex(parent_index)
        parent_node: xr.DataTree = self._datatree[parent_path]
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
            obj = self._datatree[path]
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
            obj = self._datatree[path]
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
                        i = rep.find(obj.name, i)  # find var
                        i = rep.find('(', i)  # skip var name
                        j = rep.find('\n', i)
                        return rep[i:j] if j > 0 else rep[i:]
                    elif obj.name in parent_node.coords:
                        rep = str(parent_node.dataset)
                        i = rep.find('Coordinates:')
                        i = rep.find(obj.name, i)  # find coord
                        i = rep.find('(', i)  # skip coord name
                        j = rep.find('\n', i)
                        return rep[i:j] if j > 0 else rep[i:]
        elif role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                path: str = self.pathFromIndex(index)
                obj = self._datatree[path]
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
            # cannot edit details column
            return False
        if role == Qt.ItemDataRole.EditRole:
            # rename obj
            path: str = self.pathFromIndex(index)
            obj = self._datatree[path]
            old_name = obj.name
            new_name = str(value).strip().strip('/')
            # print('rename', path, 'to', parent_path + '/' + new_name)
            if old_name == new_name:
                # nothing to do
                return False
            if not new_name or '/' in new_name:
                warn(f'Name "{new_name}" is not a valid DataTree key.')
                return False
            parent_node: xr.DataTree = index.internalPointer()
            if new_name in parent_node:
                warn(f'Name "{new_name}" already exists in parent DataTree.')
                return False
            if isinstance(obj, xr.DataTree):
                # update parent node's children mapping to rename child obj
                children = {}
                for name, child in parent_node.children.items():
                    if name == old_name:
                        children[new_name] = obj
                    else:
                        children[name] = child
                parent_node.children = children
            elif isinstance(obj, xr.DataArray):
                if old_name in parent_node.xindexes:
                    # rename dim in entire branch?
                    pass # TODO...
                    return False
                # rename array in parent node
                parent_node.dataset = parent_node.to_dataset().rename_vars({old_name: new_name})
            self.dataChanged.emit(index, index)
            print(self.datatree(), flush=True)
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
    
    def maxDepth(self) -> int:
        max_depth: int = 0
        node: xr.DataTree
        for node in self._datatree.leaves:
            depth: int = 0
            while node.parent is not None:
                depth += 1
                node = node.parent
            if depth > max_depth:
                max_depth = depth
        return max_depth

    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        print('removeRows(', row, count, self.pathFromIndex(parent_index), ')', flush=True)
        try:
            if count <= 0:
                return False
            n_rows: int = self.rowCount(parent_index)
            if (row < 0) or (row + count > n_rows):
                return False
        
            parent_path: xr.DataTree = self.pathFromIndex(parent_index)
            parent_node: xr.DataTree = self._datatree[parent_path]
            names_to_remove: list[str] = self.visibleRowNames(parent_node)[row:row + count]
            vars_to_remove: list[str] = [name for name in names_to_remove if name in parent_node.data_vars]
            coords_to_remove: list[str] = [name for name in names_to_remove if name in parent_node.coords]
            nodes_to_remove: list[str]= [name for name in names_to_remove if name in parent_node.children]
        except:
            return False
        
        self.beginRemoveRows(parent_index, row, row + count - 1)
        if vars_to_remove or coords_to_remove:
            parent_node.dataset = parent_node.to_dataset().drop_vars(vars_to_remove + coords_to_remove)
        if nodes_to_remove:
            parent_node.children = {name: node for name, node in parent_node.children.items() if name not in nodes_to_remove}
        self.endRemoveRows()
        return True

    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        print('moveRows(', self.pathFromIndex(src_parent_index), src_row, count, self.pathFromIndex(dst_parent_index), dst_row, ')', flush=True)
        if count <= 0:
            return False
        
        n_src_rows: int = self.rowCount(src_parent_index)
        n_dst_rows: int = self.rowCount(dst_parent_index)
        if (src_row < 0) or (src_row + count > n_src_rows):
            return False
        if not (0 <= dst_row <= n_dst_rows):
            return False

        src_parent_path: str = self.pathFromIndex(src_parent_index)
        dst_parent_path: str = self.pathFromIndex(dst_parent_index)

        print('src_parent_path:', src_parent_path, flush=True)
        print('dst_parent_path:', dst_parent_path, flush=True)
        print('src_rows:', list(range(src_row, src_row + count)), flush=True)
        print('dst_row:', dst_row, flush=True)

        if (src_parent_path == dst_parent_path) and (0 <= dst_row - src_row <= count):
            # no change
            print('No change in moveRows.', flush=True)
            return False
        
        src_parent_node: xr.DataTree = self._datatree[src_parent_path]
        dst_parent_node: xr.DataTree = self._datatree[dst_parent_path]

        src_names: list[str] = self.visibleRowNames(src_parent_node)[src_row: src_row + count]
        src_data_vars: dict[str, xr.DataArray] = {name: src_parent_node[name] for name in src_names if name in src_parent_node.data_vars}
        src_coords: dict[str, xr.DataArray] = {name: src_parent_node[name] for name in src_names if name in src_parent_node.coords}
        src_children: dict[str, xr.DataTree] = {name: src_parent_node[name] for name in src_names if name in src_parent_node.children}

        print('src_names:', src_names, flush=True)
        print('src_data_vars:', list(src_data_vars), flush=True)
        print('src_coords:', list(src_coords), flush=True)
        print('src_children:', list(src_children), flush=True)

        if src_children:
            dst_parent_paths: list[str] = [node.path for node in dst_parent_node.parents]
            src_paths: list[str] = [node.path for node in src_children.values()]
            print('dst_parent_paths:', dst_parent_paths, flush=True)
            print('src_paths:', src_paths, flush=True)
            for src_path in src_paths:
                print('src_path:', src_path, flush=True)
                if src_path in dst_parent_paths:
                    # Cannot move a node to one of its descendents.
                    # Instead of raising an error, just warn and silently fail.
                    # TODO... maybe optionally just don't move this node, but continue with the rest?
                    warn('Cannot move DataTrees to their own descendents.')
                    return False
        
        pre_dst_names = self.visibleRowNames(dst_parent_node)
        pre_dst_data_vars: dict[str, xr.DataArray] = {name: dst_parent_node[name] for name in pre_dst_names if name in dst_parent_node.data_vars}
        pre_dst_coords: dict[str, xr.DataArray] = {name: dst_parent_node[name] for name in pre_dst_names if name in dst_parent_node.coords}
        pre_dst_children: dict[str, xr.DataTree] = {name: dst_parent_node[name] for name in pre_dst_names if name in dst_parent_node.children}

        print('dst_names:', pre_dst_names, flush=True)
        print('dst_data_vars:', list(pre_dst_data_vars), flush=True)
        print('dst_coords:', list(pre_dst_coords), flush=True)
        print('dst_children:', list(pre_dst_children), flush=True)

        # TODO... check for name/alignment conflicts (decide what to do with conflicts)
        
        # get name at insertion point
        try:
            dst_name = pre_dst_names[dst_row]
        except IndexError:
            dst_name = None
        print('dst_name:', dst_name, flush=True)

        # get post move item order at destination
        post_dst_data_var_names = [name for name in pre_dst_data_vars if name not in src_data_vars]
        try:
            i = post_dst_data_var_names.index(dst_name)
            post_dst_data_var_names = post_dst_data_var_names[:i] + list(src_data_vars) + post_dst_data_var_names[i:]
        except:
            post_dst_data_var_names += list(src_data_vars)

        post_dst_coord_names = [name for name in pre_dst_coords if name not in src_coords]
        try:
            i = post_dst_coord_names.index(dst_name)
            post_dst_coord_names = post_dst_coord_names[:i] + list(src_coords) + post_dst_coord_names[i:]
        except:
            post_dst_coord_names += list(src_coords)

        post_dst_children_names = [name for name in pre_dst_children if name not in src_children]
        try:
            i = post_dst_children_names.index(dst_name)
            post_dst_children_names = post_dst_children_names[:i] + list(src_children) + post_dst_children_names[i:]
        except:
            post_dst_children_names += list(src_children)

        self.beginResetModel()
        # self.beginMoveRows(src_parent_index, src_row, src_row + count - 1, dst_parent_index, dst_row)  # !? segfault?

        # move data arrays
        if src_data_vars or src_coords:
            # update dst_parent_node.dataset
            if src_parent_path != dst_parent_path:
                # assign moved variables to dst_parent_node
                if src_data_vars:
                    dst_parent_node.dataset = dst_parent_node.to_dataset().assign(src_data_vars)
                if src_coords:
                    dst_parent_node.dataset = dst_parent_node.to_dataset().assign_coords(src_coords)
                
                # drop moved variables from src_parent_node
                names_to_drop = list(src_data_vars) + list(src_coords)
                src_parent_node.dataset = src_parent_node.to_dataset().drop_vars(names_to_drop)
            
            # reorder variables in dataset
            self.reorderVariables(dst_parent_node, post_dst_data_var_names, post_dst_coord_names)
        
        # move nodes
        if src_children:
            if src_parent_path != dst_parent_path:
                # append moved nodes to dst_parent_node
                for name, node in src_children.items():
                    node.orphan()
                    dst_parent_node[name] = node
            
            # reorder nodes
            dst_parent_node.children = {name: dst_parent_node.children[name] for name in post_dst_children_names}
        
        print(self.datatree(), flush=True)
        # self.endMoveRows()
        self.endResetModel()
        return True
    
    def removePaths(self, paths: list[str]) -> None:
        """ Remove items by their path.
        """
        print('removePaths(', paths, ')', flush=True)
        # group paths for removal block by contiguous row block
        path_groups: dict[str, list[list[int]]] = self.groupPaths(paths)
        for parent_path, row_blocks in path_groups.items():
            for row_block in row_blocks:
                row: int = row_block[0]
                count: int = len(row_block)
                parent_index: QModelIndex = self.indexFromPath(parent_path)
                self.removeRows(row, count, parent_index)
    
    def movePaths(self, src_paths: list[str], dst_parent_path: str, dst_row: int) -> None:
        """ Move items within tree by their path.
        """
        print('movePaths(', src_paths, dst_parent_path, dst_row, ')', flush=True)
        try:
            dst_parent_node: xr.DataTree = self._datatree[dst_parent_path]
        except KeyError:
            # Invalid dst_parent_path
            return
        dst_parent_index: QModelIndex = self.indexFromPath(dst_parent_path)
        dst_num_rows: int = self.rowCount(dst_parent_index)
        if dst_row < 0 or dst_row > dst_num_rows:
            # append rows
            dst_row = dst_num_rows
        
        # group paths for moving block by contiguous row block
        src_path_groups: dict[str, list[list[int]]] = self.groupPaths(src_paths)
        for src_parent_path, row_blocks in src_path_groups.items():
            for row_block in row_blocks:
                row: int = row_block[0]
                count: int = len(row_block)
                src_parent_index: QModelIndex = self.indexFromPath(src_parent_path)
                self.moveRows(src_parent_index, row, count, dst_parent_index, dst_row)
    
    def transferPaths(self, src_model: XarrayDataTreeModel, src_paths: list[str], dst_model: XarrayDataTreeModel, dst_parent_path: str, dst_row: int) -> None:
        """ Move items between trees by their path.
        """
        print('transferPaths')
        if src_model is dst_model:
            # move within the same tree model
            src_model.movePaths(src_paths, dst_parent_path, dst_row)
            return
        
        # TODO... implement transfer between different tree models
        src_groups: dict[str, list[list[int]]] = src_model.groupPaths(src_paths)
        print(src_groups, flush=True)

    def groupPaths(self, paths: list[str]) -> dict[str, list[list[int]]]:
        """ Group paths by their parent node and contiguous rows block.
        
        This is used to prepare for moving or copying paths in the tree.
        Note: paths should never contain the root path '/'.
        """
        # groups[parent path][[block row indices], ...]
        groups: dict[str, list[list[int]]] = {}
        for path in paths:
            parent_path: str = self.parentPath(path)
            if parent_path not in groups:
                groups[parent_path] = []
            parent_node: xr.DataTree = self._datatree[parent_path]
            row_names: list[str] = self.visibleRowNames(parent_node)
            name = path.split('/')[-1]
            row = row_names.index(name)
            added = False
            rows_group: list[int]
            for rows_group in groups[parent_path]:
                if row == rows_group[0] - 1:
                    rows_group.insert(0, row)
                    added = True
                    break
                elif row == rows_group[-1] + 1:
                    rows_group.append(row)
                    added = True
                    break
            if not added:
                # start a new group of rows
                groups[parent_path].append([row])

        # order groups by parent path from leaves to root so that moving/removing them in order does not change the paths of the remaining groups
        parent_paths: list[str] = list(groups.keys())
        parent_paths.sort(key=lambda p: p.count('/'), reverse=True)  # sort by depth (more slashes means deeper in the tree)
        groups = {parent_path: groups[parent_path] for parent_path in parent_paths}

        # order row blocks from last block to first block so that removing them in order does not change the row indices of the remaining blocks
        for parent_path, row_blocks in groups.items():
            row_blocks.sort(key=lambda block: block[0], reverse=True)
        
        return groups
    
    def reorderVariables(self, node: xr.DataTree, data_var_order: list[str] = None, coord_order: list[str] = None) -> None:
        if data_var_order is None:
            ordered_data_vars = node.data_vars
        else:
            ordered_data_vars = {name: node.data_vars[name] for name in data_var_order if name in node.data_vars}
            # unordered data_vars are appended
            for name in node.data_vars:
                if name not in ordered_data_vars:
                    ordered_data_vars[name] = node.data_vars[name]
        
        if coord_order is None:
            ordered_coords = node.coords
        else:
            ordered_coords = {name: node.coords[name] for name in coord_order if name in node.coords}
            # unordered coords are appended
            for name in node.coords:
                if name not in ordered_coords:
                    ordered_coords[name] = node.coords[name]
        
        ds: xr.Dataset = node.to_dataset()
        node.dataset = xr.Dataset(data_vars=ordered_data_vars, coords=ordered_coords, attrs=ds.attrs)
    
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
        print('dropMimeData')
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

        # store the src -> dst paths in the MIME data
        # we'll use these in the view dropEvent to restore the view for moved paths
        # TODO...

        self.transferPaths(src_model, src_paths, dst_model, dst_parent_path, row)
        return True


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
        self.view_state: dict[str, dict] = {}

        # Mapping from source to destination paths.
        # To be defined in dropMimeData().
        # Used to restore the view of the dragged items in the dropped view's dropEvent() callback.
        self.drop_path_map: dict[str, str] = {}

        # Ensure that the MIME type self.MIME_TYPE is set.
        # The actual value of the data here is not important, as we won't use it.
        # Instead, we will use the above attributes to handle drag-and-drop.
        self.setData(self.MIME_TYPE, self.MIME_TYPE.encode('utf-8'))
    
    def hasFormat(self, mime_type: str) -> bool:
        """ Check if the MIME data has the specified format.
        
        Overrides the default method to check for self.MIME_TYPE.
        """
        return mime_type == self.MIME_TYPE or super().hasFormat(mime_type)


def test_model():
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.tutorial.load_dataset('tiny')
    dt['child3/grandchild2'] = xr.DataTree()
    print(dt)

    model = XarrayDataTreeModel(datatree=dt)

    # test indexFromPath and pathFromIndex
    node: xr.DataTree
    for node in dt.subtree:
        index: QModelIndex = model.indexFromPath(node.path)
        path: str = model.pathFromIndex(index)
        print('round-trip:', node.path, '->', path, flush=True)
        for name, var in node.data_vars.items():
            index: QModelIndex = model.indexFromPath(node.path + '/' + name)
            path: str = model.pathFromIndex(index)
            print('round-trip:', node.path + '/' + name, '->', path, flush=True)
        for name, var in node.coords.items():
            index: QModelIndex = model.indexFromPath(node.path + '/' + name)
            path: str = model.pathFromIndex(index)
            print('round-trip:', node.path + '/' + name, '->', path, flush=True)

    app = QApplication()
    view = QTreeView()
    view.setModel(model)
    view.show()
    app.exec()


if __name__ == '__main__':
    test_model()