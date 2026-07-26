import time
import os

# disable pydevd file validation to avoid warning messages
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

from qtpy.QtCore import Qt, QSize
from qtpy.QtWidgets import QApplication, QSplashScreen
from qtawesome import icon

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from qtpy.QtGui import QPixmap


def xtree():
    run_app('xarray-tree')


def xgraph():
    run_app('xarray-graph')


def run_app(app_name: str):
    # print('-'*82)
    app = QApplication()
    app.setQuitOnLastWindowClosed(False)

    # t0 = time.time()
    splash_pix: QPixmap = icon('ph.cube-thin').pixmap(QSize(256, 256))
    splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    splash.raise_()
    splash.repaint() # !? needed to ensure splash screen is painted before the main window is shown despite the call to app.processEvents() below
    splash.showMessage(f"\tLoading system resources...\t", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
    app.processEvents() # force Qt to paint the splash screen immediately
    # print(f'[{time.time() - t0:.2f} sec] Splash screen')
    
    t0 = time.time()
    if app_name == 'xarray-tree':
        from xarray_graph.apps.XarrayDataTreeViewer import XarrayDataTreeViewer
        ui = XarrayDataTreeViewer.new()
        ui.setWindowTitle('xarray-tree')
    elif app_name == 'xarray-graph':
        from xarray_graph.apps.XarrayGraph import XarrayGraph
        ui = XarrayGraph.new()
        ui.setWindowTitle('xarray-graph')
    print(f'[{time.time() - t0:.2f} sec] {app_name} init')
    
    ui.show()
    splash.finish(ui)

    # MacOS specific warning for users of Magnet window management software
    import platform
    if platform.system() == 'Darwin':
        from qtpy.QtWidgets import QMessageBox
        QMessageBox.warning(None, 'Magnet Warning', 'If you are using the window management software Magnet, you may need to disable it for this app to work properly.')
    
    # example data
    from qtpy.QtWidgets import QMessageBox
    answer = QMessageBox.question(ui, 'Example?', 'Load example data?')
    url = 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc'
    if answer == QMessageBox.StandardButton.Yes:
        try:
            from requests import get
            req = get(url, stream=True)
            if req.status_code != 200:
                raise ValueError(f'Failed to download example data: request status code = {req.status_code}')
            import xarray as xr
            from io import BytesIO
            dt: xr.DataTree = xr.open_datatree(BytesIO(req.content), engine='h5netcdf')
            ui.setDatatree(dt)
            ui._datatree_view.viewAll()
        except Exception as err:
            QMessageBox.critical(ui, 'Failed to load example', str(err))

    return app.exec()


if __name__ == '__main__':
    import sys
    # status = xtree()
    status = xgraph()
    sys.exit(status)
