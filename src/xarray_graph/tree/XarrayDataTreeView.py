""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- open 1d or 2d array in table? editable? slice selection for 3d or higher dim?
- merge items?
"""

from __future__ import annotations
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import TreeView, XarrayDataTreeItem, XarrayDataTreeModel, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeView(TreeView):

    # finishedEditingAttrs = Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # icons
        self._node_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')
        self._index_coord_icon: QIcon = qta.icon('ph.asterisk-thin')
        self._unknown_icon: QIcon = qta.icon('fa6s.question')

        # self._info_shortcut = QShortcut(QKeySequence.StandardKey.Italic, self)
        # self._info_shortcut.activated.connect(lambda: self.infoDialog())

        # actions
        self._showDataVarsAction = QAction(
            text = 'Show Variables',
            icon = self._data_var_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide data_vars in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showCoordsAction = QAction(
            text = 'Show Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide inherited coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showDetailsColumnAction = QAction(
            text = 'Show Details Column',
            icon = qta.icon('fa6s.info'),
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show details column in the tree view. Uncheck to hide column.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )
    
    def setModel(self, model: XarrayDataTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        super().setModel(model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model: XarrayDataTreeModel = self.model()
        
        self._showDataVarsAction.blockSignals(True)
        self._showDataVarsAction.setChecked(model.isDataVarsVisible())
        self._showDataVarsAction.blockSignals(False)
        
        self._showCoordsAction.blockSignals(True)
        self._showCoordsAction.setChecked(model.isCoordsVisible())
        self._showCoordsAction.blockSignals(False)
        
        self._showInheritedCoordsAction.blockSignals(True)
        self._showInheritedCoordsAction.setChecked(model.isInheritedCoordsVisible())
        self._showInheritedCoordsAction.blockSignals(False)
        
        self._showDetailsColumnAction.blockSignals(True)
        self._showDetailsColumnAction.setChecked(model.isDetailsColumnVisible())
        self._showDetailsColumnAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model: XarrayDataTreeModel = self.model()
        self.storeViewState()
        model.setDataVarsVisible(self._showDataVarsAction.isChecked())
        model.setCoordsVisible(self._showCoordsAction.isChecked())
        model.setInheritedCoordsVisible(self._showInheritedCoordsAction.isChecked())
        model.setDetailsColumnVisible(self._showDetailsColumnAction.isChecked())
        self.restoreViewState()
    
    def treeData(self) -> xr.DataTree:
        model: XarrayDataTreeModel = self.model()
        return model.treeData()
    
    def setTreeData(self, data: xr.DataTree) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            model = XarrayDataTreeModel()
            model.setTreeData(data)
            self.setModel(model)
        else:
            self.storeViewState()
            model.setTreeData(data)
            self.restoreViewState()
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: XarrayDataTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: XarrayDataTreeItem = model.itemFromIndex(index)
        if item.isNode():
            icon: QIcon = self._node_icon
        elif item.isDataVar():
            icon: QIcon = self._data_var_icon
        elif item.isCoord():
            icon: QIcon = self._coord_icon
        else:
            # should never happen
            icon: QIcon = self._unknown_icon
        menu.addAction(QAction(f'{item.path()}:', parent=menu, icon=icon, iconVisibleInMenu=True, enabled=False)) # just a label
        # menu.addAction(QAction('Info', parent=menu, triggered=lambda checked, item=item: self.infoDialog(item)))
        # menu.addAction(QAction('Attrs', parent=menu, triggered=lambda checked, item=item: self.attrsDialog(item)))
        # if item.isVariable():
        #     menu.addAction(QAction('Data', parent=menu, enabled=False))
        # elif item.isNode():
        #     subtree_menu = QMenu('Subtree', parent=menu)
        #     subtree_menu.addAction(QAction('Rename Dimensions', parent=menu, triggered=lambda checked, item=item: self.renameDimensions(item)))
        #     subtree_menu.addAction(QAction('Rename Variables', parent=menu, triggered=lambda checked, item=item: self.renameVariables(item)))
        #     menu.addMenu(subtree_menu)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        self._clearSelectionAction.setEnabled(has_selection)
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = self.hasCopy()
        self._cutSelectionAction.setEnabled(has_selection)
        self._copySelectionAction.setEnabled(has_selection)
        self._pasteAction.setEnabled(has_copy)
        menu.addSeparator()
        menu.addAction(self._cutSelectionAction)
        menu.addAction(self._copySelectionAction)
        menu.addAction(self._pasteAction)

        # remove item(s)
        self._removeSelectedAction.setEnabled(has_selection)
        menu.addSeparator()
        menu.addAction(self._removeSelectedAction)

        # # combine items
        # if has_selection and len(self.selectedIndexes()) > 1:
        #     menu.addSeparator()
        #     combine_menu = QMenu('Combine')
        #     combine_menu.addAction(QAction('Merge', parent=menu, triggered=lambda checked: self.mergeSelection(), enabled=False))
        #     combine_menu.addAction(QAction('Concatenate', parent=menu, triggered=lambda checked: self.concatenateSelectedGroups()))
        #     menu.addMenu(combine_menu)
        
        # # insert new node
        # if item.isNode():
        #     menu.addSeparator()
        #     menu.addAction(QAction('New Child Node', parent=menu, icon=self._node_icon, iconVisibleInMenu=True, triggered=lambda checked, parent_item=item: self.appendNewChildNode(parent_item), enabled=has_selection))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # options
        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showInheritedCoordsAction)
        menu.addAction(self._showDetailsColumnAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    # def appendNewChildNode(self, parent_item: XarrayDataTreeItem) -> None:
    #     if not parent_item.is_group:
    #         return
    #     model: XarrayDataTreeModel = self.model()
    #     row: int = len(parent_item.children)
    #     count: int = 1
    #     parent_index: QModelIndex = model.indexFromItem(parent_item)
    #     model.insertRows(row, count, parent_index)
    
    # def infoDialog(self, item: XarrayDataTreeItem = None) -> None:
    #     if item is None:
    #         items = self.selectedItems()
    #         if not items:
    #             return
    #         item = items[0]
        
    #     info = str(item.data)

    #     font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    #     font.setPointSize(QFont().pointSize())
        
    #     textEdit = QTextEdit()
    #     textEdit.setFont(font)
    #     textEdit.setPlainText(info)
    #     textEdit.setReadOnly(True)

    #     dlg = QDialog(self)
    #     dlg.resize(max(self.width(), 800), self.height())
    #     # if self.window_decoration_offset is None:
    #     #     self._get_window_decoration_offset()
    #     # dlg.move(self.mapToGlobal(self.window_decoration_offset))
    #     dlg.move(self.mapToGlobal(QPoint(0, 0)))
    #     dlg.setWindowTitle(item.path)
        
    #     layout = QVBoxLayout(dlg)
    #     layout.setContentsMargins(0, 0, 0, 0)
    #     layout.addWidget(textEdit)

    #     dlg.exec()
    
    # def selectionInfoDialog(self) -> None:
    #     items: list[XarrayDataTreeItem] = self.selectedItems()
    #     if not items:
    #         return
        
    #     textEdit: QTextEdit = self.updateInfoTextEdit(items)

    #     if len(items) == 1:
    #         title = items[0].path
    #     else:
    #         title = 'Selected'

    #     dlg = QDialog(self)
    #     dlg.resize(max(self.width(), 800), self.height())
    #     # if self.window_decoration_offset is None:
    #     #     self._get_window_decoration_offset()
    #     # dlg.move(self.mapToGlobal(self.window_decoration_offset))
    #     dlg.move(self.mapToGlobal(QPoint(0, 0)))
    #     dlg.setWindowTitle(title)
        
    #     vbox = QVBoxLayout(dlg)
    #     vbox.setContentsMargins(0, 0, 0, 0)
    #     vbox.addWidget(textEdit)

    #     dlg.exec()
    
    # @staticmethod
    # def updateInfoTextEdit(items: list[XarrayDataTreeItem], text_edit: QTextEdit = None) -> QTextEdit:
    #     if not items:
    #         return
    #     if text_edit is None:
    #         text_edit = QTextEdit()
        
    #     text_edit.clear()
    #     text_edit.setReadOnly(True)
    #     sep = False
    #     item: XarrayDataTreeItem
    #     for item in items:
    #         data: xr.DataTree | xr.DataArray = item.data
    #         if isinstance(data, xr.DataTree):
    #             data = data.dataset
    #         if sep:
    #             # TODO: check if this works on Windows (see https://stackoverflow.com/questions/76710833/how-do-i-add-a-full-width-horizontal-line-in-qtextedit)
    #             text_edit.insertHtml('<br><hr><br>')
    #         else:
    #             sep = True
    #         text_edit.insertPlainText(f'{item.path}:\n{data}')

    #         # tc = self.result_text_box.textCursor()
    #         # # move the cursor to the end of the document
    #         # tc.movePosition(tc.End)
    #         # # insert an arbitrary QTextBlock that will inherit the previous format
    #         # tc.insertBlock()
    #         # # get the block format
    #         # fmt = tc.blockFormat()
    #         # # remove the horizontal ruler property from the block
    #         # fmt.clearProperty(fmt.BlockTrailingHorizontalRulerWidth)
    #         # # set (not merge!) the block format
    #         # tc.setBlockFormat(fmt)
    #         # # eventually, apply the cursor so that editing actually starts at the end
    #         # self.result_text_box.setTextCursor(tc)
        
    #     return text_edit
    
    # def attrsDialog(self, item: XarrayDataTreeItem) -> None:
    #     attrs_copy: dict = item.data.attrs.copy()

    #     model = KeyValueTreeModel()
    #     model.setRootData(attrs_copy)

    #     view = KeyValueTreeView()
    #     view.setAlternatingRowColors(True)
    #     view.setModel(model)
    #     view.showAll()

    #     dlg = QDialog(self)
    #     dlg.resize(max(self.width(), 800), self.height())
    #     # if self.window_decoration_offset is None:
    #     #     self._get_window_decoration_offset()
    #     # dlg.move(self.mapToGlobal(self.window_decoration_offset))
    #     dlg.move(self.mapToGlobal(QPoint(0, 0)))
    #     dlg.setWindowTitle(item.path)
        
    #     layout = QVBoxLayout(dlg)
    #     layout.setContentsMargins(0, 0, 0, 0)
    #     layout.addWidget(view)

    #     btns = QDialogButtonBox()
    #     btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
    #     btns.accepted.connect(dlg.accept)
    #     btns.rejected.connect(dlg.reject)
    #     layout.addWidget(btns)
        
    #     dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    #     dlg.setMinimumSize(QSize(400, 400))
    #     if dlg.exec() != QDialog.DialogCode.Accepted:
    #         return
        
    #     attrs: dict = model.rootData()
    #     item.data.attrs = attrs
        
    #     self.finishedEditingAttrs.emit()
    
    # @staticmethod
    # def updateAttrsTree(item: XarrayDataTreeItem, kv_view: KeyValueTreeView = None) -> KeyValueTreeView:
    #     if item is None:
    #         if kv_view:
    #             kv_view.setKeyValueMap({})
    #             return kv_view
    #         return
        
    #     if kv_view is None:
    #         kv_view = KeyValueTreeView()

    #     kv_view.setKeyValueMap(item.data.attrs)
    #     return kv_view
    
    # def renameDimensions(self, root_item: XarrayDataTreeItem) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if not model:
    #         return
    #     if not root_item.is_group:
    #         root_item = root_item.parent
    #     root_group: xr.DataTree = root_item.data
    #     root_group: xr.DataTree = xarray_utils._branch_root(root_group)
    #     while root_item.parent and root_item.data is not root_group:
    #         root_item = root_item.parent
        
    #     dims: list[str] = []
    #     for group in root_group.subtree:
    #         for dim in list(group.dims):
    #             if dim not in dims:
    #                 dims.append(dim)
        
    #     dim_lineedits: dict[str, QLineEdit] = {}
    #     for dim in dims:
    #         dim_lineedits[dim] = QLineEdit()
    #         dim_lineedits[dim].setPlaceholderText(dim)
        
    #     dlg = QDialog(self)
    #     dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    #     dlg.setWindowTitle('Rename Dimensions')
    #     vbox = QVBoxLayout(dlg)
    #     for dim in dims:
    #         vbox.addWidget(dim_lineedits[dim])
        
    #     buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    #     buttons.accepted.connect(dlg.accept)
    #     buttons.rejected.connect(dlg.reject)
    #     vbox.addWidget(buttons)

    #     if dlg.exec() != QDialog.DialogCode.Accepted:
    #         return
        
    #     renamed_dims = {}
    #     for dim in dims:
    #         new_dim = dim_lineedits[dim].text().strip()
    #         if new_dim and new_dim != dim:
    #             renamed_dims[dim] = new_dim
    #     if not renamed_dims:
    #         return
        
    #     xarray_utils.rename_dims(root_group, renamed_dims)
    #     self.refresh()
    
    # def renameVariables(self, root_item: XarrayDataTreeItem) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if not model:
    #         return
    #     if not root_item.is_group:
    #         root_item = root_item.parent
    #     root_group: xr.DataTree = root_item.data
        
    #     var_names: list[str] = []
    #     for group in root_group.subtree:
    #         for name in group.variables:
    #             if name not in var_names:
    #                 var_names.append(name)
        
    #     lineedits: dict[str, QLineEdit] = {}
    #     for name in var_names:
    #         lineedits[name] = QLineEdit()
    #         lineedits[name].setPlaceholderText(name)
        
    #     dlg = QDialog(self)
    #     dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    #     dlg.setWindowTitle('Rename Variables')
    #     vbox = QVBoxLayout(dlg)
    #     for name in var_names:
    #         vbox.addWidget(lineedits[name])
        
    #     buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    #     buttons.accepted.connect(dlg.accept)
    #     buttons.rejected.connect(dlg.reject)
    #     vbox.addWidget(buttons)

    #     if dlg.exec() != QDialog.DialogCode.Accepted:
    #         return
        
    #     var_renames = {}
    #     for name in var_names:
    #         new_name = lineedits[name].text().strip()
    #         if new_name and new_name != name:
    #             var_renames[name] = new_name
    #     if not var_renames:
    #         return
        
    #     xarray_utils.rename_vars(root_group, var_renames)
    #     self.refresh()
    
    # def mergeSelection(self) -> None:
    #     pass # TODO
    
    # def concatenateSelectedGroups(self, dim: str = None) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if not model:
    #         return
    #     items: list[XarrayDataTreeItem] = [item for item in self.selectedItems() if item.is_group]
    #     if not items or len(items) < 2:
    #         return
    #     if dim is None:
    #         title = 'Concatenate'
    #         label = 'Concatenate along dim:'
    #         dim, ok = QInputDialog.getText(self, title, label)
    #         if not ok:
    #             return
    #         dim = dim.strip()
    #         if not dim:
    #             return
    #     try:
    #         datasets: list[xr.Dataset] = [item.data.to_dataset() for item in items]
    #         concatenated_dataset: xr.Dataset = xr.concat(datasets, dim)
    #         parent_item: XarrayDataTreeItem = items[0].parent
    #         parent_group: xr.DataTree = parent_item.data
    #         name = xarray_utils.unique_name('Concat', list(parent_group.keys()))
    #         parent_group[name] = concatenated_dataset
    #         self.refresh()
    #     except Exception as err:
    #         model.popupWarningDialog(str(err))
    
    # def keyPressEvent(self, event: QKeyEvent):
        return super().keyPressEvent(event)


def test_live():
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

    view = XarrayDataTreeView()
    view.setModel(model)
    view.show()
    view.resize(800, 1000)
    view.showAll()
    view.move(50, 50)
    view.raise_()

    dt2 = dt.copy(deep=True)

    model2 = XarrayDataTreeModel()
    model2.setDataVarsVisible(True)
    model2.setCoordsVisible(True)
    model2.setInheritedCoordsVisible(True)
    model2.setDetailsColumnVisible(True)
    model2.setTreeData(dt2)

    view2 = XarrayDataTreeView()
    view2.setModel(model2)
    view2.show()
    view2.resize(800, 1000)
    view2.showAll()
    view2.move(900, 50)
    view2.raise_()

    app.exec()

    # print(dt)
    # print(dt2)


if __name__ == '__main__':
    test_live()
