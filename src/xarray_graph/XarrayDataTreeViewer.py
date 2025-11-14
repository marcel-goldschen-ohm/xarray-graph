""" Tree viewer with a XarrayDataTreeView and side widgets for interacting with the tree including an IPython console.

TODO:
- store/restore attrs view states
"""

from __future__ import annotations
import xarray as xr
import textwrap
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from xarray_graph import XarrayDataTreeModel, XarrayDataTreeView, IPythonConsole, XarrayDataTreeDebugView
from pyqt_ext.tree import KeyValueTreeItem, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeViewer(QSplitter):

    def __init__(self, datatree: xr.DataTree = None, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent: QObject = None, debug: bool = False) -> None:
        QSplitter.__init__(self, orientation, parent)

        if datatree is None:
            datatree = xr.DataTree()

        self._datatree_view = XarrayDataTreeView()
        model = XarrayDataTreeModel(datatree)
        model.setDetailsColumnVisible(False)
        self._datatree_view.setModel(model)

        self._info_view = QTextEdit()
        self._info_view.setReadOnly(True)

        self._attrs_view = KeyValueTreeView()
        self._attrs_view.setAlternatingRowColors(True)
        # self._attrs_view.setModel(KeyValueTreeModel(None))

        self._console = IPythonConsole()
        self._console.add_variable('dt', datatree)
        self._console.add_variable('ui', self) # for debugging

        if debug:
            self._debug_view = XarrayDataTreeDebugView(datatree=datatree)
            model.dataChanged.connect(lambda index0, index1: self._debug_view.updateView())
            self.view().wasRefreshed.connect(self._debug_view.updateView)

            self._update_debug_view_button = QPushButton("Update Debug View")
            self._update_debug_view_button.clicked.connect(self._debug_view.updateView)

            debug_widget = QWidget()
            debug_vbox = QVBoxLayout(debug_widget)
            debug_vbox.setContentsMargins(0, 0, 0, 0)
            debug_vbox.setSpacing(5)
            debug_vbox.addWidget(self._update_debug_view_button)
            debug_vbox.addWidget(self._debug_view)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._info_view, "Info")
        self._tabs.addTab(self._attrs_view, "Attrs")
        self._tabs.addTab(self._console, "Console")
        if debug:
            self._tabs.addTab(debug_widget, "Debug")
            self._tabs.setCurrentWidget(debug_widget)

        self.addWidget(self._datatree_view)
        self.addWidget(self._tabs)

        self._datatree_view.selectionWasChanged.connect(self.onSelectionChanged)
        self._datatree_view.finishedEditingAttrs.connect(self.onSelectionChanged)

        msg = """
        ----------------------------------------------------
        Variables: dt -> The Xarray DataTree
        Modules loaded at startup: numpy as np, xarray as xr
        ----------------------------------------------------
        """
        msg = textwrap.dedent(msg).strip()
        # need to delay a bit to let the console show
        QTimer.singleShot(100, lambda: self._console.print_message(msg))
    
    def view(self) -> XarrayDataTreeView:
        return self._datatree_view
    
    def datatree(self) -> xr.DataTree:
        return self.view().model().datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self.view().model().setDatatree(datatree)
        self._console.add_variable('dt', datatree)
        if hasattr(self, '_debug_view'):
            self._debug_view.setDatatree(datatree)
    
    def onSelectionChanged(self) -> None:
        dt: xr.DataTree = self.datatree()
        selected_paths: list[str] = self.view().selectedPaths()
        if len(selected_paths) == 0:
            # if nothing is selected, show info for the tree root node
            selected_paths = ['/']
        ordered_paths: list[str] = []
        node: xr.DataTree
        for node in dt.subtree:
            paths = [node.path] \
                + [f'{node.path}/{name}' for name in node.data_vars] \
                + [f'{node.path}/{name}' for name in node.coords]
            for path in paths:
                if path in selected_paths:
                    ordered_paths.append(path)

        # update info for selection
        info_text = ''
        for path in ordered_paths:
            obj = dt[path]
            if isinstance(obj, xr.DataTree):
                obj = obj.dataset
            if info_text:
                dashed_line: str = '-' * 50
                info_text += f'\n{dashed_line}\n\n'
            info_text += f'{path}:\n{obj}\n'
        self._info_view.setPlainText(info_text)

        # only show attrs key[value] tree view if a single item is selected
        if len(selected_paths) == 1:
            # show attrs for selected item
            obj: xr.DataTree | xr.DataArray = dt[path]
            if self._attrs_view.model() is None:
                self._attrs_view.setModel(KeyValueTreeModel(obj.attrs))
            else:
                self._attrs_view.model().setTreeData(obj.attrs)
            self._attrs_view.resizeAllColumnsToContents()
        else:
            # clear attrs
            self._attrs_view.setModel(None)


def test_live():
    dt = xr.DataTree()
    dt['child1'] = xr.tutorial.load_dataset('air_temperature')
    dt['child2'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    dt['child3/grandchild1/greatgrandchild2'] = xr.tutorial.load_dataset('tiny')
    dt['child3/grandchild2'] = xr.DataTree()
    print(dt)

    app = QApplication()
    viewer = XarrayDataTreeViewer(dt, Qt.Orientation.Horizontal, debug=True)
    viewer.resize(1200, 800)
    viewer.show()
    app.exec()
    print(dt)


if __name__ == '__main__':
    test_live()