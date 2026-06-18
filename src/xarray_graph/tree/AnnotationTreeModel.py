""" Tree model for dict representations of data/graph annotations.

Annotations are dicts which can be grouped via their 'group' key.

The model accepts a flat list of annotations from which a nested group tree structure is derived.
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import AbstractTreeModel, AnnotationTreeItem


class AnnotationTreeModel(AbstractTreeModel):
    
    MIME_TYPE = 'application/x-annotation-tree-model'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = ['Annotation']

        # annotation dicts
        self.setAnnotations([])
    
    def reset(self) -> None:
        self.setAnnotations(self.annotations())
    
    def annotations(self) -> list[dict]:
        return self._annotations
    
    def setAnnotations(self, annotations: list[dict]) -> None:
        self._annotations = annotations
        root = AnnotationTreeItem(annotations)
        root.rebuildSubtree()
        self.setRootItem(root)
    
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
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
        if item.isAnnotation() or item.isGroup():
            flags |= Qt.ItemFlag.ItemIsEditable
        
        # drag and drop
        if self.supportedDropActions() != Qt.DropAction.IgnoreAction:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
            # can only drop onto groups
            # will check to prevent nested gorups in drop handler
            if item.isGroup():
                flags |= Qt.ItemFlag.ItemIsDropEnabled
        
        return flags

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                return item.name()
        if role == Qt.ItemDataRole.DecorationRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                if item.isGroup():
                    return qta.icon('mdi.group')
                elif item.isAnnotation():
                    atype = item._data.get('type', '').lower()
                    if atype == 'region':
                        ndims = len(item._data.get('position', {}))
                        if ndims == 1:
                            return qta.icon('mdi.arrow-expand-horizontal')
                        elif ndims >= 2:
                            return qta.icon('mdi.rectangle-outline')
                    # return qta.icon('mdi.tag-multiple')

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if role == Qt.ItemDataRole.EditRole:
            if index.column() == 0:
                item: AnnotationTreeItem = self.itemFromIndex(index)
                if item.name() == value:
                    # no change
                    return False
                item.setName(value)
                return True
        return False

    # def removeRows(self, row: int, count: int, parent_index: QModelIndex = QModelIndex()) -> bool:
    #     if count <= 0:
    #         return False
    #     num_rows: int = self.rowCount(parent_index)
    #     if (row < 0) or (row + count > num_rows):
    #         return False
        
    #     parent_item: AnnotationTreeItem = self.itemFromIndex(parent_index)
    #     items_to_remove: list[AnnotationTreeItem] = parent_item.children[row: row + count]

    #     self.beginRemoveRows(parent_index, row, row + count - 1)

    #     item: AnnotationTreeItem
    #     for item in reversed(items_to_remove):
    #         if item.is_annotation_list():
    #             # clear the list
    #             annotations_list: list[dict] = item.data
    #             del annotations_list[:]
    #         elif item.is_annotation_group():
    #             # remove all annotations in group
    #             group: str = item.data
    #             annotations_list: list[dict] = parent_item.data
    #             i = 0
    #             while i < len(annotations_list):
    #                 if annotations_list[i].get('group', None) == group:
    #                     del annotations_list[i]
    #                 else:
    #                     i += 1
    #         elif item.is_annotation():
    #             # remove annotation
    #             if parent_item.is_annotation_group():
    #                 annotations_list: list[dict] = parent_item.parent.data
    #             else:
    #                 annotations_list: list[dict] = parent_item.data
    #             annotation: dict = item.data
    #             annotations_list.remove(annotation)
    #         item.parent = None
        
    #     del parent_item.children[row: row + count]

    #     self.endRemoveRows()
        
    #     return True
    
    # def insertGroups(self, groups: list[str], row: int, parent_item: AnnotationTreeItem) -> bool:
    #     """ Insert empty groups.
    #     """
    #     num_rows: int = len(parent_item.children)
    #     if row < 0:
    #         # negative indexing
    #         row += num_rows
    #     if (row < 0) or (row > num_rows):
    #         return False
        
    #     if not parent_item.is_annotation_list():
    #         parent_widget: QWidget = QApplication.focusWidget()
    #         title = 'Invalid Insertion'
    #         text = f'Cannot insert groups in non-list "{parent_item.path}".'
    #         QMessageBox.warning(parent_widget, title, text)
    #         return False

    #     existing_groups: list[str] = [item.data for item in parent_item.children if item.is_annotation_group()]
    #     groups_to_insert = [group for group in groups if group not in existing_groups]
    #     if not groups_to_insert:
    #         return False
        
    #     existing_ungrouped_annotations: list[dict] = [item.data for item in parent_item.children if item.is_annotation()]
    #     n_existing_ungrouped_annotations = len(existing_ungrouped_annotations)

    #     # insert empty groups
    #     parent_index: QModelIndex = self.indexFromItem(parent_item)
    #     count: int = len(groups_to_insert)
    #     if row < n_existing_ungrouped_annotations:
    #         row = n_existing_ungrouped_annotations
    #     self.beginInsertRows(parent_index, row, row + count - 1)

    #     for i, group in zip(range(row, row + count), groups_to_insert):
    #         group_item = AnnotationTreeItem(group)
    #         parent_item.insert_child(i, group_item)

    #     self.endInsertRows()
    #     return True
    
    # def insertAnnotations(self, annotations: list[dict], row: int, parent_item: AnnotationTreeItem) -> None:
    #     """ `items` must be a flat list of
    #     """
    #     num_rows: int = len(parent_item.children)
    #     if row < 0:
    #         # negative indexing
    #         row += num_rows
    #     if (row < 0) or (row > num_rows):
    #         return False
        
    #     if parent_item.is_annotation():
    #         parent_item = parent_item.parent
        
    #     if parent_item.is_annotation_group():
    #         # if inserting into an existing group, all inserted annotations will belong to the existing group
    #         group: str = parent_item.data
    #         for annotation in annotations:
    #             annotation['group'] = group
    #         parent_item = parent_item.parent
        
    #     if not parent_item.is_annotation_list():
    #         # !?
    #         return False
        
    #     # insert groups as needed for new annotations
    #     groups: list[str] = list(set([ann['group'] for ann in annotations if ann.get('group', None)]))
    #     existing_groups: list[str] = [item.data for item in parent_item.children if item.is_annotation_group()]
    #     groups_to_insert: list[str] = [group for group in groups if group not in existing_groups]
    #     if groups_to_insert:
    #         row: int = len(parent_item.children)
    #         self.insertGroups(groups_to_insert, row, parent_item)

    #     # split annotations into groups
    #     ungrouped_annotations: list[dict] = []
    #     grouped_annotations: dict[str, list[dict]] = {}
    #     annotation: dict
    #     for annotation in annotations:
    #         group: str | None = annotation.get('group', None)
    #         if group:
    #             if group not in grouped_annotations:
    #                 grouped_annotations[group] = []
    #             grouped_annotations[group].append(annotation)
    #         else:
    #             ungrouped_annotations.append(annotation)
        
    #     existing_ungrouped_annotations: list[dict] = [item.data for item in parent_item.children if item.is_annotation()]
    #     n_existing_ungrouped_annotations = len(existing_ungrouped_annotations)
        
    #     # insert ungrouped annotations
    #     if ungrouped_annotations:
    #         parent_index: QModelIndex = self.indexFromItem(parent_item)
    #         if row > n_existing_ungrouped_annotations:
    #             row = n_existing_ungrouped_annotations
    #         count: int = len(ungrouped_annotations)
    #         self.beginInsertRows(parent_index, row, row + count - 1)
    #         for i, annotation in zip(range(row, row + count), ungrouped_annotations):
    #             parent_item.data.insert(i, annotation)
    #             parent_item.insert_child(i, AnnotationTreeItem(annotation))
    #         self.endInsertRows()
    #         n_existing_ungrouped_annotations += count
        
    #     # insert grouped annotations
    #     if grouped_annotations:
    #         for group, group_annotations in grouped_annotations.items():
    #             group_item: AnnotationTreeItem = None
    #             for item in parent_item.children:
    #                 if item.data == group:
    #                     group_item = item
    #                     break
    #             if not group_item:
    #                 continue
                
    #             group_index: QModelIndex = self.indexFromItem(group_item)
    #             row: int = len(group_item.children)
    #             count: int = len(group_annotations)
    #             self.beginInsertRows(group_index, row, row + count - 1)
    #             for annotation in group_annotations:
    #                 parent_item.data.append(annotation)
    #                 group_item.append_child(AnnotationTreeItem(annotation))
    #             self.endInsertRows()
        
    #     return True
    
    # def moveRows(self, src_parent_index: QModelIndex, src_row: int, count: int, dst_parent_index: QModelIndex, dst_row: int) -> bool:
    #     if count <= 0:
    #         return False
    #     num_src_rows: int = self.rowCount(src_parent_index)
    #     if (src_row < 0) or (src_row + count > num_src_rows):
    #         return False
    #     num_dst_rows: int = self.rowCount(dst_parent_index)
    #     if (dst_row < 0) or (dst_row > num_dst_rows):
    #         return False
        
    #     src_parent_item: AnnotationTreeItem = self.itemFromIndex(src_parent_index)
    #     dst_parent_item: AnnotationTreeItem = self.itemFromIndex(dst_parent_index)

    #     if src_parent_item is dst_parent_item:
    #         if src_row <= dst_row <= src_row + count:
    #             # nothing moved
    #             return False

    #     src_items_to_move: list[AnnotationTreeItem] = src_parent_item.children[src_row:src_row+count]
    #     print('src_items_to_move', src_items_to_move)
    #     src_annotations: list[dict] = []
    #     item: AnnotationTreeItem
    #     for item in src_items_to_move:
    #         leaf: AnnotationTreeItem
    #         for leaf in item.subtree_leaves():
    #             if leaf.is_annotation():
    #                 src_annotations.append(leaf.data)

    #     # remove from src
    #     self.removeRows(src_row, count, src_parent_index)

    #     # insert at dst
    #     self.insertAnnotations(src_annotations, dst_row, dst_parent_item)

    #     return True


def test_model():
    annotations = [
        {'type': 'region', 'position': {'lat': [0, 1]}},
        {'type': 'region', 'position': {'lon': [2, 3]}},
        {'type': 'region', 'position': {'lat': [4, 5], 'lon': [6, 7]}, 'group': 'Group A'},
        {'type': 'region', 'position': {'lon': [6, 7]}, 'group': 'Group A', 'text': 'some text\nsecond line'},
        {'type': 'region', 'position': {'lat': [8, 9]}, 'group': 'Group B'},
    ]

    app = QApplication()
    model = AnnotationTreeModel()
    model.setAnnotations(annotations)
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