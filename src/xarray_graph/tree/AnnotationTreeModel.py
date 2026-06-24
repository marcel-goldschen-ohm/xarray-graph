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
                            try:
                                npoints = len(next(iter(item._data.get('position', {}).values()), []))
                            except TypeError:
                                npoints = 1
                            if npoints == 1:
                                return qta.icon('fa6s.arrow-down-long')
                            elif npoints == 2:
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

        if not dst_parent_item.isGroup():
            parent_widget: QWidget = QApplication.focusWidget()
            title = 'Invalid Move'
            text = f'Cannot move items into non-group "{dst_parent_item.path()}".'
            QMessageBox.warning(parent_widget, title, text)
            return False

        if src_parent_item is dst_parent_item:
            if src_row <= dst_row <= src_row + count:
                # nothing moved
                return False

        src_items_to_move: list[AnnotationTreeItem] = src_parent_item.children[src_row:src_row+count]
        if dst_parent_item is not self.rootItem():
            # cannot move items into a group that is not the root
            for item in src_items_to_move:
                if item.isGroup():
                    parent_widget: QWidget = QApplication.focusWidget()
                    title = 'Invalid Move'
                    text = f'Cannot nest group "{item.path()}" in non-root group "{dst_parent_item.path()}".'
                    QMessageBox.warning(parent_widget, title, text)
                    return False
        
        return super().moveRows(src_parent_index, src_row, count, dst_parent_index, dst_row)


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