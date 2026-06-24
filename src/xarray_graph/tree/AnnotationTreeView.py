""" Tree view for a `AnnotationTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.
"""

from __future__ import annotations
from copy import deepcopy
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import AnnotationTreeItem, AnnotationTreeModel, TreeView, KeyValueTreeModel, KeyValueTreeView


class AnnotationTreeView(TreeView):

    _copied_annotations: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        TreeView.__init__(self, *args, **kwargs)

        self._cut_icon = qta.icon('mdi.content-cut')
        self._copy_icon = qta.icon('mdi.content-copy')
        self._paste_icon = qta.icon('mdi.content-paste')

        self._cut_shortcut = QShortcut(QKeySequence.StandardKey.Cut, self)
        self._cut_shortcut.activated.connect(self.cutSelection)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.activated.connect(self.copySelection)

        self._paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self._paste_shortcut.activated.connect(lambda: self.pasteCopy())

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragAndDropEnabled(True)
    
    def annotations(self) -> list[dict] | dict[str, list[dict]]:
        model: AnnotationTreeModel = self.model()
        return model.annotations()
    
    def setAnnotations(self, annotations: list[dict] | dict[str, list[dict]]) -> None:
        model: AnnotationTreeModel = self.model()
        if model is None:
            model = AnnotationTreeModel()
            model.setAnnotations(annotations)
            self.setModel(model)
        else:
            self.storeViewState()
            model.setAnnotations(annotations)
            self.restoreViewState()
    
    def selectedAnnotations(self) -> list[dict]:
        model: AnnotationTreeModel = self.model()
        if model is None:
            return []
        annotations = []
        item: AnnotationTreeItem
        for item in self.selectedItems():
            leaf: AnnotationTreeItem
            for leaf in item.subtree_leaves():
                if leaf.isAnnotation():
                    annotation: dict = leaf._data
                    if annotation not in annotations:
                        annotations.append(annotation)
        return annotations

    def setSelectedAnnotations(self, annotations: list[dict]) -> None:
        model: AnnotationTreeModel = self.model()
        if model is None:
            return
        root: AnnotationTreeItem = model.rootItem()
        self.selectionModel().clearSelection()
        toSelect = QItemSelection()
        item: AnnotationTreeItem
        for item in root.subtree_leaves():
            if item is root:
                continue
            if item.isAnnotation():
                annotation: dict = item._data
                if annotation in annotations:
                    index: QModelIndex = model.indexFromItem(item)
                    toSelect.select(index, index)
        if toSelect.indexes():
            flags = (
                QItemSelectionModel.SelectionFlag.Select |
                QItemSelectionModel.SelectionFlag.Rows
            )
            self.selectionModel().select(toSelect, flags)
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: AnnotationTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: AnnotationTreeItem = model.itemFromIndex(index)

        if item.isAnnotation():
            menu.addAction(QAction('Edit', parent=menu, triggered=lambda checked, item=item: self.editAnnotation(item)))
            menu.addSeparator()
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste (annotations only)
        has_copy: bool = self.hasCopy()
        menu.addSeparator()
        menu.addAction(QAction('Cut', parent=menu, icon=self._cut_icon, iconVisibleInMenu=True, triggered=lambda checked: self.cutSelection(), enabled=has_selection))
        menu.addAction(QAction('Copy', parent=menu, icon=self._copy_icon, iconVisibleInMenu=True, triggered=lambda checked: self.copySelection(), enabled=has_selection))
        menu.addAction(QAction('Paste', parent=menu, icon=self._paste_icon, iconVisibleInMenu=True, triggered=lambda checked, parent_item=item: self.pasteCopy(parent_item), enabled=has_copy))
        
        # remove item(s)
        menu.addSeparator()
        menu.addAction(QAction('Remove', parent=menu, triggered=lambda checked: self.removeSelectedItems(), enabled=has_selection))
        
        # insert new item
        if item.isRoot() or item.parent.isRoot():
            parent_item: AnnotationTreeItem = item if item.isRoot() else item.parent
            menu.addSeparator()
            menu.addAction(QAction('New Group', parent=menu, triggered=lambda checked, parent_item=parent_item, row=len(parent_item.children): self.insertNewGroup(parent_item, row)))
        
        # group selected
        if has_selection:
            menu.addSeparator()
            menu.addAction(QAction('Group Selected', parent=menu, triggered=lambda checked: self.groupSelected()))
            menu.addAction(QAction('Ungroup Selected', parent=menu, triggered=lambda checked: self.ungroupSelected()))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items: list[AnnotationTreeItem] = []
        for item in self.selectedItems():
            for leaf_item in item.subtree_leaves():
                if leaf_item not in items:
                    items.append(leaf_item)
        if not items:
            return
        # copy the annotation dicts
        AnnotationTreeView._copied_annotations = [deepcopy(item._data) for item in items if item.isAnnotation()]
    
    def pasteCopy(self, parent_item: AnnotationTreeItem = None) -> None:
        model: AnnotationTreeModel = self.model()
        if not model:
            return
        annotations = [deepcopy(ann) for ann in AnnotationTreeView._copied_annotations]
        if not annotations:
            return
        if parent_item is None:
            items = self.selectedItems()
            if not items:
                return
            parent_item = items[0]
            if parent_item.isAnnotation():
                parent_item = parent_item.parent
        # paste items
        row: int = len(parent_item.children)
        # TODO...
        # model.insertAnnotations(annotations, row, parent_item)
    
    def hasCopy(self) -> bool:
        if AnnotationTreeView._copied_annotations:
            return True
        return False
    
    def editAnnotation(self, item: AnnotationTreeItem) -> None:
        if not item.isAnnotation():
            return
        annotation: dict = item._data
        model = KeyValueTreeModel()
        model.setTreeData(annotation)
        view = KeyValueTreeView()
        view.setAlternatingRowColors(True)
        view.setModel(model)
        view.showAll()
        
        dialog = QDialog(parent=self)
        dialog.setWindowTitle('Edit Annotation')
        vbox = QVBoxLayout(dialog)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)
        vbox.addWidget(view)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        vbox.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
    
    def insertNewGroup(self, parent_item: AnnotationTreeItem, row: int) -> None:
        if not parent_item.isRoot():
            return
        model: AnnotationTreeModel = self.model()
        annotations: list[dict] = parent_item._data
        group_names = list(set([ann['group'] for ann in annotations if ann.get('group', None)]))
        # in case we have any empty group nodes
        child_item: AnnotationTreeItem
        for child_item in parent_item.children:
            if child_item.isGroup():
                group_name = child_item.group()
                if group_name not in group_names:
                    group_names.append(group_name)
        # insert new empty group node with unique name
        group_name = xarray_utils.unique_name('Group', group_names)
        new_item = AnnotationTreeItem([], group_name)
        model.insertItems([new_item], row, parent_item)
    
    def groupSelected(self) -> None:
        pass # TODO
        # items: list[AnnotationTreeItem] = self.selectedItems()
        # if not items:
        #     return
        # title = 'Group'
        # label = 'Group name:'
        # group, ok = QInputDialog.getText(self, title, label)
        # group = group.strip()
        # if not ok or not group:
        #     return
        # for item in items:
        #     if item.is_annotation():
        #         item.data['group'] = group
        # self.refresh()
    
    def ungroupSelected(self) -> None:
        pass # TODO
        # items: list[AnnotationTreeItem] = self.selectedItems()
        # if not items:
        #     return
        # for item in items:
        #     if item.is_annotation():
        #         if 'group' in item.data:
        #             del item.data['group']
        # self.refresh()


def test_live():

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

    view = AnnotationTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 800))
    view.move(QPoint(100, 100))
    view.showAll()
    view.raise_()

    app.exec()

    print(model.rootItem())
    print(annotations)

if __name__ == '__main__':
    test_live()
