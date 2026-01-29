""" Embedded IPython console widget.

TODO:
- fix bug where multiple?? instances of console crash during application exit. Presumably something is not getting cleaned up correctly, but stop_channels() and shutdown_kernel() do not seem to fix this.
"""

# from __future__ import annotations
# from qtpy.QtGui import QCloseEvent#, QShowEvent
from qtpy.QtWidgets import QApplication
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
# from qtconsole.manager import QtKernelManager


class IPythonConsole(RichJupyterWidget):
    """ Embedded IPython console widget.

    !!! The console is designed as a singleton, so you should only create one instance of this class. If you need to show the console in multiple places, consider creating a wrapper class that contains an instance of this console and shows/hides it as needed.
    
    To update another UI element when code is executed in the console,
    connect to the `executed` signal:
        self.executed.connect(your_update_function)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.start()
        # self.exit_requested.connect(self.stop)
        QApplication.instance().aboutToQuit.connect(self.stop)
    
    def start(self) -> None:
        manager = QtInProcessKernelManager()
        # manager = QtKernelManager()
        manager.start_kernel()
        client = manager.client()
        client.start_channels()
        self.kernel_manager = manager
        self.kernel_client = client
    
    def stop(self) -> None:
        self.kernel_client.stop_channels()
        self.kernel_manager.shutdown_kernel()
    
    def pushVariables(self, variables: dict):
        """ Given a dictionary containing name / value pairs, push those variables to the IPython console widget
        """
        self.kernel_manager.kernel.shell.push(variables)

    def addVariable(self, name: str, value: object) -> None:
        """ Add a variable to the console's namespace.
        """
        self.kernel_manager.kernel.shell.push({name: value})
    
    def clearTerminal(self):
        """ Clears the terminal
        """
        self._control.clear()
    
    def printMessage(self, message: str, dedent: bool = True) -> None:
        """ Print message to the console.
        """
        if dedent:
            import textwrap
            message = textwrap.dedent(message).strip()
        self._append_plain_text(message, before_prompt=True)

    # def showEvent(self, event: QShowEvent):
    #     """ This method is called when the widget is shown.
    #     """
    #     super().showEvent(event) # Call the base class implementation

    #     # show custom message if it exists
    #     msg: str = getattr(self, '_one_time_message_on_show', None)
    #     if msg:
    #         self.print_message(msg)
    #         # so we don't keep displaying the message
    #         delattr(self, '_one_time_message_on_show')

    # def closeEvent(self, event: QCloseEvent) -> None:
    #     self.stop()
    
    
def test_live():
    from qtpy.QtWidgets import QApplication
    from qtpy.QtCore import QTimer
    import numpy as np

    app = QApplication()
    console = IPythonConsole()

    console.execute('import numpy as np', hidden=True)
    # console._set_input_buffer('') # seems silly to have to call this?

    data = np.random.rand(4, 3)
    console.addVariable('data', data)
    console.addVariable('self', console)

    console.executed.connect(lambda: print("Code executed in console."))

    msg = """
    ----------------------------------------------------
    Variables:
      self -> This console
      data -> Data array
    Modules loaded at startup: numpy as np
    ----------------------------------------------------
    """
    # need to delay a bit to let the console show first
    QTimer.singleShot(100, lambda: console.printMessage(msg))
    
    console.show()
    app.exec()


if __name__ == '__main__':
    test_live()