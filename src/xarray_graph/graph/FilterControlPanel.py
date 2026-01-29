""" Filter control panel UI.
"""

from __future__ import annotations
import numpy as np
import scipy as sp
import xarray as xr
import pint
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *


class FilterControlPanel(QWidget):

    filterChanged = Signal()
    previewToggled = Signal()
    filterRequested = Signal()

    ureg = pint.UnitRegistry()
    ureg.formatter.default_format = '~'  # short format for symbols (e.g., "A" instead of "ampere")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle('Filter')

        # components
        self._label = QLabel('Filter')

        self._type_combobox = QComboBox()
        self._type_combobox.addItems(['Gaussian', 'Median', 'Bessel', 'Butterworth', 'FIR'])
        self._type_combobox.setCurrentText('Gaussian')
        self._type_combobox.currentIndexChanged.connect(lambda index: self._onFilterTypeChanged())
        self._type_combobox.setEnabled(False) # only Gaussian filter working at the moment

        self._band_type_combobox = QComboBox()
        self._band_type_combobox.addItems(['Lowpass', 'Bandpass', 'Highpass'])
        self._band_type_combobox.currentIndexChanged.connect(lambda index: self.filterChanged.emit())

        self._cutoff_edit = QLineEdit('')
        self._cutoff_edit.setPlaceholderText('single [, band]')
        self._cutoff_edit.setToolTip('single [, band]')
        self._cutoff_edit.editingFinished.connect(lambda: self.filterChanged.emit())

        self._cutoff_units_edit = QLineEdit('')
        self._cutoff_units_edit.setPlaceholderText('cylces / sample interval')#\u0394x')
        self._cutoff_units_edit.setToolTip('if not specified, defaults to: cylces / sample interval')
        self._cutoff_units_edit.editingFinished.connect(lambda: self.filterChanged.emit())

        self._band_group = QGroupBox()
        form = QFormLayout(self._band_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(self._band_type_combobox)
        form.addRow('Cutoff', self._cutoff_edit)
        form.addRow('Cutoff units', self._cutoff_units_edit)

        self._preview_checkbox = QCheckBox('Preview', checked=True)
        self._preview_checkbox.stateChanged.connect(lambda state: self.previewToggled.emit())

        self._apply_button = QPushButton('Apply')
        self._apply_button.pressed.connect(lambda: self.filterRequested.emit())

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self._preview_checkbox)
        buttons_layout.addWidget(self._apply_button)

        # layout
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        # vbox.addWidget(self._label)
        vbox.addWidget(self._type_combobox)
        vbox.addWidget(self._band_group)
        vbox.addLayout(buttons_layout)
        vbox.addStretch()

        self.blockSignals(True)
        self._onFilterTypeChanged()
        self.blockSignals(False)
    
    def _onFilterTypeChanged(self) -> None:
        filter_type = self._type_combobox.currentText()

        if filter_type == 'Gaussian':
            self._band_type_combobox.blockSignals(True)
            self._band_type_combobox.setCurrentText('Lowpass')
            self._band_type_combobox.setEnabled(False)
            self._band_type_combobox.blockSignals(False)
        
        self.filterChanged.emit()
    
    def filter(self, x: xr.DataArray, y: xr.DataArray) -> xr.DataArray:
        filter_type = self._type_combobox.currentText()
        band_type = self._band_type_combobox.currentText()
        cutoffs = [float(fc) for fc in self._cutoff_edit.text().split(',') if fc.strip() != '']
        if not cutoffs:
            return
        cutoff_units = self._cutoff_units_edit.text().strip()
        
        dx = (x.data[1] - x.data[0])  # !!! assumes constant sample rate
        xunits = x.attrs.get('units', None)

        if filter_type == 'Gaussian':
            # must be lowpass
            lowpass_cutoff = cutoffs[0]
            if cutoff_units and xunits:
                lowpass_cutoff *= self.ureg(cutoff_units)
                dx *= self.ureg(xunits)
                lowpass_cycles_per_sample = (lowpass_cutoff.to(f'1/{xunits}') * dx).magnitude
            else:
                lowpass_cycles_per_sample = lowpass_cutoff
            sigma = 1 / (2 * np.pi * lowpass_cycles_per_sample)
            filtered = sp.ndimage.gaussian_filter1d(y.data, sigma)
        
        return y.copy(data=filtered)


def test_live():
    app = QApplication()
    ui = FilterControlPanel()
    ui.show()
    app.exec()


if __name__ == '__main__':
    test_live()