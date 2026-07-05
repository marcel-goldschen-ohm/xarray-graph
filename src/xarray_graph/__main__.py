from qtpy.QtCore import QSize, QTimer
from qtpy.QtGui import QPixmap, Qt
from qtpy.QtWidgets import QApplication, QSplashScreen
from qtawesome import icon


def show_ui_and_close_splash(ui, splash: QSplashScreen):
    ui.show()
    splash.finish(ui)


def xtree():
    app = QApplication()
    app.setQuitOnLastWindowClosed(False)

    splash_pix: QPixmap = icon('ph.cube-thin').pixmap(QSize(256, 256))
    splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    splash.showMessage("xarray-tree: Loading system resources...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
    app.processEvents() # Force Qt to paint the splash screen immediately

    from xarray_graph.apps import XarrayDataTreeViewer

    ui = XarrayDataTreeViewer.new()
    ui.setWindowTitle('xarray-tree')
    QTimer.singleShot(2000, lambda: show_ui_and_close_splash(ui, splash))

    show_warnings()
    load_datatree(ui, 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc', ask=True)
    return app.exec()


def xgraph():
    app = QApplication()
    app.setQuitOnLastWindowClosed(False)

    splash_pix: QPixmap = icon('ph.cube-thin').pixmap(QSize(256, 256))
    splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    splash.showMessage("xarray-graph: Loading system resources...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
    app.processEvents() # Force Qt to paint the splash screen immediately

    from xarray_graph.apps import XarrayGraph

    ui = XarrayGraph.new()
    ui.setWindowTitle('xarray-graph')
    QTimer.singleShot(2000, lambda: show_ui_and_close_splash(ui, splash))

    show_warnings()
    load_datatree(ui, 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc', ask=True)
    return app.exec()


def show_warnings() -> None:
    import platform
    if platform.system() == 'Darwin':
        from qtpy.QtWidgets import QMessageBox
        QMessageBox.warning(None, 'Magnet Warning', 'If you are using the window management software Magnet, please disable it for this app to work properly.')


def load_datatree(ui, url: str = 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc', ask: bool = True) -> None:
    import requests, io
    import xarray as xr
    from qtpy.QtWidgets import QMessageBox
    from xarray_graph.apps import XarrayDataTreeViewer # ui: XarrayDataTreeViewer

    if ask:
        answer = QMessageBox.question(ui, 'Example?', 'Load example data?')
    if (ask == False) or (answer == QMessageBox.StandardButton.Yes):
        try:
            req = requests.get(url, stream=True)
            if req.status_code != 200:
                raise ValueError(f'Failed to download example data: request status code = {req.status_code}')
            dt: xr.DataTree = xr.open_datatree(io.BytesIO(req.content), engine='h5netcdf')
            ui.setDatatree(dt)
            ui._datatree_view.showAll()
        except Exception as err:
            QMessageBox.critical(ui, 'Failed to load example', str(err))


if __name__ == '__main__':
    import sys
    # status = xtree()
    status = xgraph()
    sys.exit(status)
