""" Measurement control panel UI.
"""

from __future__ import annotations
import numpy as np
import scipy as sp
import xarray as xr
import pint
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *


class MeasureControlPanel(QWidget):

    measurementChanged = Signal()
    previewToggled = Signal()
    measurementRequested = Signal()

    ureg = pint.UnitRegistry()
    ureg.formatter.default_format = '~'  # short format for symbols (e.g., "A" instead of "ampere")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle('Measure')

        # components
        self._label = QLabel('Measure')

        self._type_combobox = QComboBox()
        self._type_combobox.addItems(['Mean', 'Median'])
        self._type_combobox.insertSeparator(self._type_combobox.count())
        self._type_combobox.addItems(['Min', 'Max'])
        # self._type_combobox.insertSeparator(self._type_combobox.count())
        # self._type_combobox.addItems(['Peaks'])
        self._type_combobox.insertSeparator(self._type_combobox.count())
        self._type_combobox.addItems(['Standard Deviation', 'Variance'])
        self._type_combobox.currentIndexChanged.connect(lambda index: self._onMeasurementTypeChanged())

        self._avg_plus_minus_samples_spinbox = QSpinBox()
        self._avg_plus_minus_samples_spinbox.setMinimum(0)
        self._avg_plus_minus_samples_spinbox.setSpecialValueText('None')
        self._avg_plus_minus_samples_spinbox.setValue(0)
        self._avg_plus_minus_samples_spinbox.valueChanged.connect(lambda value: self.measurementChanged.emit())

        self._avg_plus_minus_samples_group = QGroupBox()
        form = QFormLayout(self._avg_plus_minus_samples_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        plus_minus_symbol = u'\u00b1'
        form.addRow(f'Mean {plus_minus_symbol} samples', self._avg_plus_minus_samples_spinbox)

        # self._peak_type_combobox = QComboBox()
        # self._peak_type_combobox.addItems(['Positive', 'Negative'])
        # self._peak_type_combobox.setCurrentText('Positive')
        # self._peak_type_combobox.currentIndexChanged.connect(lambda index: self.measurementChanged.emit())

        # self._max_num_peaks_per_region_spinbox = QSpinBox()
        # self._max_num_peaks_per_region_spinbox.setMinimum(0)
        # self._max_num_peaks_per_region_spinbox.setMaximum(1000000)
        # self._max_num_peaks_per_region_spinbox.setSpecialValueText('Any')
        # self._max_num_peaks_per_region_spinbox.setValue(0)
        # self._max_num_peaks_per_region_spinbox.valueChanged.connect(lambda value: self.measurementChanged.emit())

        # self._peak_threshold_edit = QLineEdit('0')
        # self._peak_threshold_edit.editingFinished.connect(lambda: self.measurementChanged.emit())

        # self._measure_peak_group = QGroupBox()
        # form = QFormLayout(self._measure_peak_group)
        # form.setContentsMargins(3, 3, 3, 3)
        # form.setSpacing(3)
        # form.setHorizontalSpacing(5)
        # form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # form.addRow('Peak type', self._peak_type_combobox)
        # form.addRow('Max # peaks', self._max_num_peaks_per_region_spinbox)
        # Delta_symbol = u'\u00b1'
        # form.addRow(f'{Delta_symbol} sample mean', self._avg_plus_minus_samples_spinbox)
        # form.addRow('Peak threshold', self._peak_threshold_edit)

        self._measure_in_ROIs_only_checkbox = QCheckBox('Measure within ROIs only')
        self._measure_in_ROIs_only_checkbox.setChecked(True)
        self._measure_in_ROIs_only_checkbox.stateChanged.connect(lambda state: self.measurementChanged.emit())

        self._measure_per_ROI_checkbox = QCheckBox('Measure for each ROI')
        self._measure_per_ROI_checkbox.setChecked(True)
        self._measure_in_ROIs_only_checkbox.setEnabled(not self._measure_per_ROI_checkbox.isChecked)
        self._measure_per_ROI_checkbox.stateChanged.connect(lambda state: self._measure_in_ROIs_only_checkbox.setEnabled(Qt.CheckState(state) == Qt.CheckState.Unchecked))
        self._measure_per_ROI_checkbox.stateChanged.connect(lambda state: self.measurementChanged.emit())

        self._preview_checkbox = QCheckBox('Preview', checked=True)
        self._preview_checkbox.stateChanged.connect(lambda state: self.previewToggled.emit())

        self._apply_button = QPushButton('Measure')
        self._apply_button.pressed.connect(lambda: self.measurementRequested.emit())

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self._preview_checkbox)
        buttons_layout.addWidget(self._apply_button)

        # layout
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        # vbox.addWidget(self._label)
        vbox.addWidget(self._type_combobox)
        vbox.addWidget(self._avg_plus_minus_samples_group)
        vbox.addSpacing(10)
        vbox.addWidget(self._measure_in_ROIs_only_checkbox)
        vbox.addWidget(self._measure_per_ROI_checkbox)
        vbox.addSpacing(10)
        vbox.addLayout(buttons_layout)
        vbox.addStretch()

        self.blockSignals(True)
        self._onMeasurementTypeChanged()
        self.blockSignals(False)
    
    def _onMeasurementTypeChanged(self):
        measurement_type = self._type_combobox.currentText()
        self._avg_plus_minus_samples_group.setVisible(measurement_type in ['Min', 'Max'])

        self.measurementChanged.emit()
    
    def measure(self, x: np.ndarray, y: np.ndarray) -> float | tuple[float, float]:
        measurement_type = self._type_combobox.currentText()
        
        if measurement_type == 'Mean':
            return np.nanmean(y)
        elif measurement_type == 'Median':
            return np.nanmedian(y)
        elif measurement_type == 'Min':
            i = np.argmin(y)
            n = self._avg_plus_minus_samples_spinbox.value()
            if n:
                return x[i], np.nanmean(y[max(0, i-n):min(i+n, len(y))])
            return x[i], y[i]
        elif measurement_type == 'Max':
            i = np.argmax(y)
            n = self._avg_plus_minus_samples_spinbox.value()
            if n:
                return x[i], np.nanmean(y[max(0, i-n):min(i+n, len(y))])
            return x[i], y[i]
        elif measurement_type == 'Standard Deviation':
            return np.nanstd(y)
        elif measurement_type == 'Variance':
            return np.nanvar(y)


def test_live():
    app = QApplication()
    ui = MeasureControlPanel()
    ui.show()
    app.exec()


if __name__ == '__main__':
    test_live()