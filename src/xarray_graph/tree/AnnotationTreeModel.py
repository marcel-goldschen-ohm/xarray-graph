""" Tree model for dict representations of data/graph annotations.

Annotations are dicts which can be grouped via their 'group' key.

The model accepts either a list of annotations or a dict of lists of annotations.
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import AbstractTreeItem, AbstractTreeModel


class AnnotationTreeItem(AbstractTreeItem):

    def __init__(self, data: list | str | dict, list_label: str = None, parent: AnnotationTreeItem = None, sibling_index: int = -1):
        # tree linkage
        super().__init__(parent, sibling_index)

        # annotation dict or group name or list of annotations
        self.data = data
        self.list_label = list_label # only used if data is a list

    @property
    def name(self) -> str:
        if self.is_annotation_list():
            return self.list_label if self.list_label else ''
        elif self.is_annotation_group():
            return self.data
        elif self.is_annotation():
            from xarray_graph.graph.Annotation import annotation_label
            label = annotation_label(self.data)
            return label if label else '{...}'
        return ''
    
    def is_annotation(self) -> bool:
        return isinstance(self.data, dict)

    def is_annotation_group(self) -> bool:
        return isinstance(self.data, str)

    def is_annotation_list(self) -> bool:
        return isinstance(self.data, list)


class AnnotationTreeModel(AbstractTreeModel):
    
    MIME_TYPE = 'application/x-annotation-tree-model'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['Annotation', 'Type']

        # options
        self._is_types_column_visible: bool = False

        # annotation dicts
        self.setAnnotations([])
    
    def reset(self) -> None:
        self.setAnnotations(self.annotations())
    
    def annotations(self) -> list[dict] | dict[str, list[dict]]:
        return self._annotations
    
    def setAnnotations(self, annotations: list[dict] | dict[str, list[dict]]) -> None:
        self._annotations = annotations
        
        if isinstance(annotations, dict):
            # multiple separate annotation lists
            root = AnnotationTreeItem(None)
            for ann_list_name, ann_list in annotations.items():
                ann_list_item = AnnotationTreeItem(ann_list, list_label=ann_list_name, parent=root)
                # ungrouped annotations
                for ann in ann_list:
                    if ann.get('group', None) is None:
                        AnnotationTreeItem(ann, parent=ann_list_item)
                # grouped annotations
                group_items = {}
                for ann in ann_list:
                    group_name = ann.get('group', None)
                    if group_name is not None:
                        if group_name not in group_items:
                            group_items[group_name] = AnnotationTreeItem(group_name, parent=ann_list_item)
                        AnnotationTreeItem(ann, parent=group_items[group_name])
        elif isinstance(annotations, list):
            # single annotation list
            root = AnnotationTreeItem(annotations)
            # ungrouped annotations
            for ann in annotations:
                if ann.get('group', None) is None:
                    AnnotationTreeItem(ann, parent=root)
            # grouped annotations
            group_items = {}
            for ann in annotations:
                group_name = ann.get('group', None)
                if group_name is not None:
                    if group_name not in group_items:
                        group_items[group_name] = AnnotationTreeItem(group_name, parent=root)
                    AnnotationTreeItem(ann, parent=group_items[group_name])
        else:
            raise ValueError('Model only accepts a list of annotation dicts or a dict of named lists of annotation dicts.')
        self.setRootItem(root)
    
    def isTypesColumnVisible(self) -> bool:
        return self._is_types_column_visible
    
    def setTypesColumnVisible(self, visible: bool) -> None:
        if visible == self.isTypesColumnVisible():
            return
        
        if visible:
            self.beginInsertColumns(QModelIndex(), 1, 1)
            self._is_types_column_visible = visible
            self.endInsertColumns()
        else:
            self.beginRemoveColumns(QModelIndex(), 1, 1)
            self._is_types_column_visible = visible
            self.endRemoveColumns()
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        if self.isTypesColumnVisible():
            return 2
        return 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            # root item
            if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
                # allow drops on the root item (i.e., this allows drops on the viewport away from other items)
                return Qt.ItemFlag.ItemIsDropEnabled
            return Qt.ItemFlag.NoItemFlags
        
        if index.column() != 0:
            return Qt.ItemFlag.NoItemFlags
        
        item: AnnotationTreeItem = self.itemFromIndex(index)
        
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        # allow editing of annotations and annotation groups, but not annotation lists
        if item.is_annotation() or item.is_annotation_group():
            flags |= Qt.ItemFlag.ItemIsEditable
        
        # drag and drop
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            # can drag and drop annotations and annotation groups, but not annotation lists
            if item.is_annotation() or item.is_annotation_group():
                flags |= Qt.ItemFlag.ItemIsDragEnabled
            # can only drop onto groups or lists
            if not item.is_annotation():
                flags |= Qt.ItemFlag.ItemIsDropEnabled
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                if item.is_annotation_list():
                    return item.list_label
                elif item.is_annotation_group():
                    return item.data
                elif item.is_annotation():
                    from xarray_graph.graph.Annotation import annotation_label
                    return annotation_label(item.data)
            elif index.column() == 1:
                # types column
                item: AnnotationTreeItem = self.itemFromIndex(index)
                if item.is_annotation():
                    atype = item.data.get('type', None)
                    return atype
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                if item.is_annotation_list():
                    return qta.icon('ph.folder-thin')
                elif item.is_annotation_group():
                    return qta.icon('mdi.group')
                elif item.is_annotation():
                    atype = item.data.get('type', '').lower()
                    if atype == 'hregion':
                        return qta.icon('mdi.arrow-expand-horizontal')
                    elif atype == 'vregion':
                        return qta.icon('mdi.arrow-expand-vertical')
                    elif atype in ['region', 'rectangle', 'box', 'area']:
                        return qta.icon('mdi.rectangle-outline')
                    else:
                        return qta.icon('mdi.tag-multiple')

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                if item.is_annotation_list():
                    # list labels are not editable
                    return False
                elif item.is_annotation_group():
                    # TODO: rename group
                    return True
                elif item.is_annotation():
                    # TODO: update annotation
                    return True
        return False

    def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
        if count <= 0:
            return False
        num_rows: int = self.rowCount(parent_index)
        if (row < 0) or (row + count > num_rows):
            return False
        
        parent_item: AnnotationTreeItem = self.itemFromIndex(parent_index)
        items_to_remove: list[AnnotationTreeItem] = parent_item.children[row: row + count]

        self.beginRemoveRows(parent_index, row, row + count - 1)

        item: AnnotationTreeItem
        for item in reversed(items_to_remove):
            if item.is_annotation_list():
                # clear the list
                annotations_list: list[dict] = item.data
                del annotations_list[:]
            elif item.is_annotation_group():
                # remove all annotations in group
                group: str = item.data
                annotations_list: list[dict] = parent_item.data
                i = 0
                while i < len(annotations_list):
                    if annotations_list[i].get('group', None) == group:
                        del annotations_list[i]
                    else:
                        i += 1
            elif item.is_annotation():
                # remove annotation
                if parent_item.is_annotation_group():
                    annotations_list: list[dict] = parent_item.parent.data
                else:
                    annotations_list: list[dict] = parent_item.data
                annotation: dict = item.data
                annotations_list.remove(annotation)
            item.parent = None
        
        del parent_item.children[row: row + count]

        self.endRemoveRows()
        
        return True
    
    def insertGroups(self, groups: list[str], row: int, parent_item: AnnotationTreeItem) -> bool:
        """ Insert empty groups.
        """
        num_rows: int = len(parent_item.children)
        if row < 0:
            # negative indexing
            row += num_rows
        if (row < 0) or (row > num_rows):
            return False
        
        if not parent_item.is_annotation_list():
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Insertion'
            text = f'Cannot insert groups in non-list "{parent_item.path}".'
            QMessageBox.warning(parent_widget, title, text)
            return False

        existing_groups: list[str] = [item.data for item in parent_item.children if item.is_annotation_group()]
        groups_to_insert = [group for group in groups if group not in existing_groups]
        if not groups_to_insert:
            return False
        
        existing_ungrouped_annotations: list[dict] = [item.data for item in parent_item.children if item.is_annotation()]
        n_existing_ungrouped_annotations = len(existing_ungrouped_annotations)

        # insert empty groups
        parent_index: QModelIndex = self.indexFromItem(parent_item)
        count: int = len(groups_to_insert)
        if row < n_existing_ungrouped_annotations:
            row = n_existing_ungrouped_annotations
        self.beginInsertRows(parent_index, row, row + count - 1)

        for i, group in zip(range(row, row + count), groups_to_insert):
            group_item = AnnotationTreeItem(group)
            parent_item.insert_child(i, group_item)

        self.endInsertRows()
        return True
    
    def insertAnnotations(self, annotations: list[dict], row: int, parent_item: AnnotationTreeItem) -> None:
        """ `items` must be a flat list of
        """
        num_rows: int = len(parent_item.children)
        if row < 0:
            # negative indexing
            row += num_rows
        if (row < 0) or (row > num_rows):
            return False
        
        if parent_item.is_annotation():
            parent_item = parent_item.parent
        
        if parent_item.is_annotation_group():
            # if inserting into an existing group, all inserted annotations will belong to the existing group
            group: str = parent_item.data
            for annotation in annotations:
                annotation['group'] = group
            parent_item = parent_item.parent
        
        if not parent_item.is_annotation_list():
            # !?
            return False
        
        # insert groups as needed for new annotations
        groups: list[str] = list(set([ann['group'] for ann in annotations if ann.get('group', None)]))
        existing_groups: list[str] = [item.data for item in parent_item.children if item.is_annotation_group()]
        groups_to_insert: list[str] = [group for group in groups if group not in existing_groups]
        if groups_to_insert:
            row: int = len(parent_item.children)
            self.insertGroups(groups_to_insert, row, parent_item)

        # split annotations into groups
        ungrouped_annotations: list[dict] = []
        grouped_annotations: dict[str, list[dict]] = {}
        annotation: dict
        for annotation in annotations:
            group: str | None = annotation.get('group', None)
            if group:
                if group not in grouped_annotations:
                    grouped_annotations[group] = []
                grouped_annotations[group].append(annotation)
            else:
                ungrouped_annotations.append(annotation)
        
        existing_ungrouped_annotations: list[dict] = [item.data for item in parent_item.children if item.is_annotation()]
        n_existing_ungrouped_annotations = len(existing_ungrouped_annotations)
        
        # insert ungrouped annotations
        if ungrouped_annotations:
            parent_index: QModelIndex = self.indexFromItem(parent_item)
            if row > n_existing_ungrouped_annotations:
                row = n_existing_ungrouped_annotations
            count: int = len(ungrouped_annotations)
            self.beginInsertRows(parent_index, row, row + count - 1)
            for i, annotation in zip(range(row, row + count), ungrouped_annotations):
                parent_item.data.insert(i, annotation)
                parent_item.insert_child(i, AnnotationTreeItem(annotation))
            self.endInsertRows()
            n_existing_ungrouped_annotations += count
        
        # insert grouped annotations
        if grouped_annotations:
            for group, group_annotations in grouped_annotations.items():
                group_item: AnnotationTreeItem = None
                for item in parent_item.children:
                    if item.data == group:
                        group_item = item
                        break
                if not group_item:
                    continue
                
                group_index: QModelIndex = self.indexFromItem(group_item)
                row: int = len(group_item.children)
                count: int = len(group_annotations)
                self.beginInsertRows(group_index, row, row + count - 1)
                for annotation in group_annotations:
                    parent_item.data.append(annotation)
                    group_item.append_child(AnnotationTreeItem(annotation))
                self.endInsertRows()
        
        return True
    
    def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
        if count <= 0:
            return False
        num_src_rows: int = self.rowCount(src_parent_index)
        if (src_row < 0) or (src_row + count > num_src_rows):
            return False
        num_dst_rows: int = self.rowCount(dst_parent_index)
        if (dst_row < 0) or (dst_row > num_dst_rows):
            return False
        
        src_parent_item: AnnotationTreeItem = self.itemFromIndex(src_parent_index)
        dst_parent_item: AnnotationTreeItem = self.itemFromIndex(dst_parent_index)

        if src_parent_item is dst_parent_item:
            if src_row <= dst_row <= src_row + count:
                # nothing moved
                return False

        src_items_to_move: list[AnnotationTreeItem] = src_parent_item.children[src_row:src_row+count]
        print('src_items_to_move', src_items_to_move)
        src_annotations: list[dict] = []
        item: AnnotationTreeItem
        for item in src_items_to_move:
            leaf: AnnotationTreeItem
            for leaf in item.subtree_leaves():
                if leaf.is_annotation():
                    src_annotations.append(leaf.data)

        # remove from src
        self.removeRows(src_row, count, src_parent_index)

        # insert at dst
        self.insertAnnotations(src_annotations, dst_row, dst_parent_item)

        return True


def test_model():
    model = AnnotationTreeModel()

    model.setAnnotations(
        {
            'List 1': [
                {'type': 'vregion', 'position': {'lat': [0, 1]}},
                {'type': 'hregion', 'position': {'lon': [2, 3]}},
            ],
            'List 2': [
                {'type': 'region', 'position': {'lat': [4, 5], 'lon': [6, 7]}, 'group': 'Group A'},
                {'type': 'hregion', 'position': {'lon': [6, 7]}, 'group': 'Group A'},
                {'type': 'vregion', 'position': {'lat': [8, 9]}, 'group': 'Group B'},
            ],
        }
    )

    app = QApplication()
    view = QTreeView()
    view.setModel(model)
    view.show()
    view.expandAll()
    app.exec()

    # print(model.rootItem())
    # # print(dt)
    # print(dt.attrs['annotations'])
    # print(dt['child1'].attrs['annotations'])


if __name__ == '__main__':
    test_model()