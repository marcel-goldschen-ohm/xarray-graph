import time
import os
import sys
import traceback
import threading
import faulthandler
from pathlib import Path

# disable pydevd file validation to avoid warning messages
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

# use lazy importing
os.environ["PYTHONLAZYIMPORTS"] = "1"

from qtpy.QtCore import Qt, QSize
from qtpy.QtWidgets import QApplication, QSplashScreen
from qtawesome import icon
from xarray_graph.io.io import detach_datatree_backend

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from qtpy.QtGui import QPixmap


_CRASH_LOG_PATH: Path | None = None
_CRASH_LOG_FILE = None


def _install_crash_diagnostics() -> None:
    global _CRASH_LOG_PATH, _CRASH_LOG_FILE

    log_dir = Path.home() / 'Library' / 'Logs' / 'xarray-graph'
    log_dir.mkdir(parents=True, exist_ok=True)
    _CRASH_LOG_PATH = log_dir / 'crash.log'
    _CRASH_LOG_FILE = open(_CRASH_LOG_PATH, 'a', buffering=1)

    def _log(line: str) -> None:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        _CRASH_LOG_FILE.write(f'[{timestamp}] {line}\n')

    _log('--- app start ---')

    def _excepthook(exc_type, exc_value, exc_tb):
        _log('Uncaught Python exception:')
        traceback.print_exception(exc_type, exc_value, exc_tb, file=_CRASH_LOG_FILE)
        _CRASH_LOG_FILE.flush()

    def _threading_excepthook(args):
        _log(f'Uncaught exception in thread {args.thread.name}:')
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=_CRASH_LOG_FILE)
        _CRASH_LOG_FILE.flush()

    sys.excepthook = _excepthook
    threading.excepthook = _threading_excepthook

    # Capture C-level faults (segfault/abort/etc.) that bypass Python exceptions.
    faulthandler.enable(_CRASH_LOG_FILE, all_threads=True)


def _install_qt_message_filter() -> None:
    """Suppress a known Qt warning emitted by some Qt6/PySide combinations.

    The warning is noisy and non-fatal:
    QObject::connect(QStyleHints, QStyleHints): unique connections require ...
    """
    try:
        from qtpy.QtCore import qInstallMessageHandler
    except Exception:
        return

    def _handler(msg_type, context, message):
        if "QObject::connect(QStyleHints, QStyleHints): unique connections require" in message:
            return
        if _CRASH_LOG_FILE is not None:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            _CRASH_LOG_FILE.write(f'[{timestamp}] [Qt] {message}\n')
        print(message)

    qInstallMessageHandler(_handler)


def _close_all_window_datatrees(ui) -> None:
    """Close datatree backends before interpreter teardown."""
    try:
        windows = tuple(ui.window_mgr.windows())
    except Exception:
        windows = (ui,)

    for window in windows:
        try:
            dt = window.datatree()
        except Exception:
            continue
        detach_datatree_backend(dt, materialize=False)


def xtree():
    run_app('xarray-tree')


def xgraph():
    run_app('xarray-graph')


def run_app(app_name: str):
    # print('-'*82)
    _install_crash_diagnostics()

    app = QApplication()
    app.setQuitOnLastWindowClosed(False)
    _install_qt_message_filter()

    if _CRASH_LOG_FILE is not None:
        app.aboutToQuit.connect(lambda: _CRASH_LOG_FILE.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] aboutToQuit\n"))

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
        ui = XarrayDataTreeViewer.newWindow()
        ui.setWindowTitle('xarray-tree')
    elif app_name == 'xarray-graph':
        from xarray_graph.apps.XarrayGraph import XarrayGraph
        ui = XarrayGraph.newWindow()
        ui.setWindowTitle('xarray-graph')
    print(f'[{time.time() - t0:.2f} sec] {app_name} init')
    
    ui.show()
    splash.finish(ui)

    app.aboutToQuit.connect(lambda: _close_all_window_datatrees(ui))

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
            detach_datatree_backend(dt, materialize=True)
            ui.setDatatree(dt)
            ui._datatree_view.viewAll()
        except Exception as err:
            QMessageBox.critical(ui, 'Failed to load example', str(err))

    return app.exec()


if __name__ == '__main__':
    # status = xtree()
    status = xgraph()
    sys.exit(status)
