# Copyright 2024 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import N_, P_, tooltip_format, register, CAPABILITIES, get_topic_name
from joulescope_ui.ui_util import comboBoxConfig, comboBoxSelectItemByText
from joulescope_ui.styles import styled_widget
from joulescope_ui.widgets.signal_record import signal_record_config_widget
from joulescope_ui.widgets.statistics_record.statistics_record_config_widget import StatisticsRecordConfigDialog
from joulescope_ui.widgets.waveform.interval_widget import IntervalWidget, str_to_float
from joulescope_ui.source_selector import SourceSelector
import logging


_STYLE = """\
<style>
table {
  border-collapse: collapse
}
th, td {
  padding: 5px;
  border: 1px solid;
}
</style>
"""
_DEVICE_TOOLTIP = tooltip_format(
    N_('Select the source device'),
    N_("The device to use for the start condition and stop condition."))

_RUN_MODE_SINGLE = N_('Single')
_RUN_MODE_CONTINUOUS = N_('Continuous')
_RUN_MODE_TOOLTIP = f"""\
<html><header>{_STYLE}</header>
<body>
<h3>{N_('Configure run mode')}</h3>
<p><table>
  <tr>
    <td>{_RUN_MODE_SINGLE}</td>
    <td>{N_('Perform one trigger sequence and then return to inactive mode.')}</td>
  </tr>
  <tr>
    <td>{_RUN_MODE_CONTINUOUS}</td>
    <td>{N_('Repeat the trigger sequence indefinitely until manually stopped.')}</td>
  </tr>
</table></p></body></html>
"""

_STATUS_INACTIVE = N_('Inactive')
_STATUS_SEARCHING = N_('Searching')
_STATUS_ACTIVE = N_('Active')
_STATUS_ACTIVE_DESCRIPTION = N_
_STATUS_TOOLTIP = f"""\
<html><header>{_STYLE}</header>
<body>
<h3>{N_('Start, stop and indicate status')}</h3>
<p><table>
  <tr>
    <td>{_STATUS_INACTIVE}</td>
    <td>{N_('Configure trigger options and then press to start.')}</td>
  </tr>
  <tr>
    <td>{_STATUS_SEARCHING}</td>
    <td>{N_('Look for the configured start condition. '
       'On match, perform the start actions and advance to active. '
       'Press to halt and return to inactive.')}</td>
  </tr>
  <tr>
    <td>{_STATUS_ACTIVE}</td>
    <td>{N_('Look for the configured stop condition. '
            'On match, perform the stop actions. '
            'For run mode single, transition to inactive. '
            'For run mode continuous, transition to searching. '
            'Press to halt and return to inactive.')}</td>
  </tr>
</table></p></body></html>
"""


def generate_map(value):
    m = {}
    for idx, args in enumerate(value):
        v = args[0]
        m[idx] = v
        for arg in args:
            m[arg] = v
    return m


_CONDITION_TYPE_LIST = [
    ['edge', N_('Edge')],
    ['duration', N_('Duration')],
]
_CONDITION_TYPES = generate_map(_CONDITION_TYPE_LIST)

_EDGE_CONDITION_LIST = [
    ['rising', '↑'],
    ['falling', '↓'],
    ['both', '↕'],
]
_EDGE_CONDITIONS = generate_map(_EDGE_CONDITION_LIST)

_DURATION_META_SIGNALS = [
    ['always', N_('Always')],
    ['never', N_('Never')],
]

_DURATION_CONDITION_LIST = [
    ['>', '>'],
    ['<', '<'],
    ['between', N_('between')],
    ['outside', N_('outside')],
]
_DURATION_CONDITIONS = generate_map(_DURATION_CONDITION_LIST)

_DIGITAL_DURATION_CONDITION_LIST = [
    ['0', '0'],
    ['1', '1'],
]
_DIGITAL_DURATION_CONDITIONS = generate_map(_DIGITAL_DURATION_CONDITION_LIST)

_SIGNAL_UNITS = {
    'i': 'A',
    'v': 'V',
    'p': 'W',
}

_SI_PREFIX = {
    'n': 1e-9,
    'µ': 1e-6,
    'm': 1e-3,
    '': 1e0,
    None: 1e0,
    'k': 1e3,
}


SETTINGS = {
    'source': {
        'dtype': 'str',
        'brief': N_('The source instrument.'),
        'default': None,
    },
    'mode': {
        'dtype': 'str',
        'brief': 'The trigger mode.',
        'default': 'single',
        'options': [
            ['single', _RUN_MODE_SINGLE],
            ['continuous', _RUN_MODE_CONTINUOUS],
        ],
    },
    'status': {
        'dtype': 'str',
        'brief': 'Arm the trigger.',
        'default': 'inactive',
        'options': [
            ['inactive', _STATUS_INACTIVE],
            ['searching', _STATUS_SEARCHING],
            ['active', _STATUS_ACTIVE],
        ],
        'flags': ['ro', 'hide', 'tmp'],
    },
    'config': {
        'dtype': 'obj',
        'brief': 'The trigger configuration.',
        'default': None,
    },
}


def _is_digital_signal(s):
    return s in ['0', '1', '2', '3', 'T']


def _grid_row_set_visible(layout, row, visible):
    visible = bool(visible)
    for col in range(layout.columnCount()):
        item = layout.itemAtPosition(row, col)
        if item is not None:
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)


class ConditionWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._signal_list = []
        self._value_scale = None
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.addWidget(QtWidgets.QLabel(N_('Type')), 0, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Signal')), 1, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Condition')), 2, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Duration')), 3, 0, 1, 1)

        self._type = QtWidgets.QComboBox()
        comboBoxConfig(self._type, [x[1] for x in _CONDITION_TYPE_LIST])
        self._type.currentIndexChanged.connect(self._visibility_update)

        self._layout.addWidget(self._type, 0, 1, 1, 1)

        self._source_widget = QtWidgets.QWidget()
        self._source_layout = QtWidgets.QHBoxLayout(self._source_widget)
        self._source_layout.setContentsMargins(0, 0, 0, 0)
        self._signal = QtWidgets.QComboBox()
        self._signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._signal.currentIndexChanged.connect(self._visibility_update)
        self._source_layout.addWidget(self._signal)
        self._layout.addWidget(self._source_widget, 1, 1, 1, 1)

        self._condition_widget = QtWidgets.QWidget()
        self._condition_layout = QtWidgets.QHBoxLayout(self._condition_widget)
        self._condition_layout.setContentsMargins(0, 0, 0, 0)
        self._condition = QtWidgets.QComboBox()
        self._condition.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._condition.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        self._condition_layout.addWidget(self._condition)
        self._condition.currentIndexChanged.connect(self._visibility_update)

        self._value1 = QtWidgets.QLineEdit('0')
        self._value1_validator = QtGui.QDoubleValidator(self)
        self._value1.setValidator(self._value1_validator)
        self._condition_layout.addWidget(self._value1)

        self._value2 = QtWidgets.QLineEdit('0')
        self._value2_validator = QtGui.QDoubleValidator(self)
        self._value2.setValidator(self._value2_validator)
        self._condition_layout.addWidget(self._value2)

        self._value_units = QtWidgets.QComboBox()
        self._value_units.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._value_units.currentIndexChanged.connect(self._on_value_units)
        self._condition_layout.addWidget(self._value_units)

        spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._condition_layout.addItem(spacer)
        self._layout.addWidget(self._condition_widget, 2, 1, 1, 1)

        self._duration = IntervalWidget(self, 1)
        self._layout.addWidget(self._duration, 3, 1, 1, 1)

        signals = [
            self._type.currentIndexChanged,
            self._signal.currentIndexChanged,
            self._condition.currentIndexChanged,
            self._value1.textChanged,
            self._value2.textChanged,
            self._value_units.currentIndexChanged,
            self._duration.value_changed,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)
        self._visibility_update()

    @QtCore.Slot(object)
    def _on_config_update(self, value=None):
        cfg = self.config
        self.config_changed.emit(cfg)

    def _condition_list_get(self):
        type_idx = self._type.currentIndex()
        signal = self._signal_list_with_meta()[self._signal.currentIndex()][0]
        if type_idx == 0:
            return _EDGE_CONDITION_LIST
        elif _is_digital_signal(signal):
            return _DIGITAL_DURATION_CONDITION_LIST
        elif signal in _DURATION_META_SIGNALS:
            return None
        else:
            return _DURATION_CONDITION_LIST

    @property
    def config(self):
        type_name = _CONDITION_TYPE_LIST[self._type.currentIndex()][0]
        signal = self._signal_list_with_meta()[self._signal.currentIndex()][0]
        condition_list = self._condition_list_get()
        if condition_list is None:
            condition = None
        else:
            condition = condition_list[self._condition.currentIndex()][0]

        v1 = str_to_float(self._value1.text())
        v2 = str_to_float(self._value2.text())
        v_unit = self._value_units.currentText()
        v_unit = '' if len(v_unit) <= 1 else v_unit[0]
        v_scale = _SI_PREFIX[v_unit]
        v1 *= v_scale
        v2 *= v_scale

        return {
            'type': type_name,
            'signal': signal,
            'condition': condition,
            'value1': v1,
            'value2': v2,
            'value_unit': v_unit,
            'duration': self._duration.value,
        }

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        type_name = value.get('type', 'edge')
        condition_types = [x[0] for x in _CONDITION_TYPE_LIST]
        block = self._type.blockSignals(True)
        self._type.setCurrentIndex(condition_types.index(type_name))
        self._type.blockSignals(block)
        self._visibility_update()

        signal_list = self._signal_list_with_meta()
        signals = [x[0] for x in signal_list]
        signal_idx = signals.index(value.get('signal'))
        signal = signal_list[signal_idx][0]
        block = self._signal.blockSignals(True)
        self._signal.setCurrentIndex(signal_idx)
        self._signal.blockSignals(block)
        self._visibility_update()

        condition = value['condition']
        condition_list = self._condition_list_get()
        try:
            condition_idx = [x[0] for x in condition_list].index(condition)
            self._condition.setCurrentIndex(condition_idx)
        except IndexError:
            pass
        self._visibility_update()

        v_unit = value.get('value_unit', '')
        unit = _SIGNAL_UNITS.get(signal, None)
        if unit is not None:
            comboBoxSelectItemByText(self._value_units, v_unit + unit, block=True)
            self._value_units_update()
        v_scale = _SI_PREFIX[v_unit]
        block = self._value1.blockSignals(True)
        self._value1.setText(f'{value["value1"] / v_scale:g}')
        self._value1.blockSignals(block)
        block = self._value2.blockSignals(True)
        self._value2.setText(f'{value["value2"] / v_scale:g}')
        self._value2.blockSignals(block)

        self._duration.value = value['duration']

    def _value_units_update(self):
        self._value_scale = 1.0 if self._value_scale is None else float(self._value_scale)
        value = self._value_units.currentText()
        prefix = '' if len(value) <= 1 else value[0]
        scale = _SI_PREFIX[prefix]
        for w in [self._value1, self._value2]:
            v = str_to_float(w.text()) * (self._value_scale / scale)
            w.setText(f'{v:g}')
        self._value_scale = scale

    @QtCore.Slot()
    def _visibility_update(self):
        type_index = self._type.currentIndex()
        _grid_row_set_visible(self._layout, 3, type_index != 0)

        signal_list = self._signal_list_with_meta()
        comboBoxConfig(self._signal, [s[1] for s in signal_list])
        try:
            signal = signal_list[self._signal.currentIndex()][0]
        except IndexError:
            return
        if signal in ['always', 'never']:
            _grid_row_set_visible(self._layout, 2, False)
            return
        _grid_row_set_visible(self._layout, 2, True)
        is_digital = _is_digital_signal(signal)
        condition_list = self._condition_list_get()
        if condition_list is None:
            self._condition.clear()
        else:
            comboBoxConfig(self._condition, [x[1] for x in condition_list])

        if type_index == 0:  # edge
            visibility = [not is_digital, False, not is_digital]
        elif type_index == 1:  # duration
            if is_digital:
                duration = _DIGITAL_DURATION_CONDITIONS[self._condition.currentIndex()]
            else:
                duration = _DURATION_CONDITIONS[self._condition.currentIndex()]
            if duration in ['0', '1']:
                visibility = [False, False, False]
            elif duration in ['between', 'outside']:
                visibility = [True, True, True]
            else:
                visibility = [True, False, not is_digital]
        self._value1.setVisible(visibility[0])
        self._value2.setVisible(visibility[1])

        try:
            unit = _SIGNAL_UNITS.get(signal, None)
        except (IndexError, ValueError, KeyError):
            unit = None
        if unit is None:
            self._value_units.clear()
        else:
            prefixes = ['m', ''] if signal == 'v' else ['n', 'µ', 'm', '']
            unit_enum = [prefix + unit for prefix in prefixes]
            comboBoxConfig(self._value_units, unit_enum, unit)
            self._value_units_update()
        self._value_units.setVisible(visibility[2] and signal not in ['r'])

    def _signal_list_with_meta(self):
        if self._type.currentIndex() == 1:  # duration
            return self._signal_list + _DURATION_META_SIGNALS
        else:
            return list(self._signal_list)

    def on_signal_list(self, value):
        self._signal_list = value
        self._visibility_update()

    @QtCore.Slot(int)
    def _on_value_units(self, index):
        self._value_units_update()


class StartActionsWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._output_list = []
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)

        self._sample_record = QtWidgets.QCheckBox()
        self._layout.addWidget(self._sample_record, 0, 0, 1, 1)
        self._sample_record1 = QtWidgets.QHBoxLayout()
        self._sample_record1.addWidget(QtWidgets.QLabel(N_('Record samples')))
        self._sample_record_config = QtWidgets.QPushButton(N_('Config'))
        self._sample_record_config.pressed.connect(self._on_sample_record_config)
        self._sample_record1.addWidget(self._sample_record_config)
        self._layout.addLayout(self._sample_record1, 0, 1, 1, 1)
        self._sample_record_pre = IntervalWidget(None, 0.1, name=N_('Start buffer'))
        self._layout.addWidget(self._sample_record_pre, 1, 1, 1, 1)
        self._sample_record_post = IntervalWidget(None, 1.0, name=N_('Stop delay'))
        self._layout.addWidget(self._sample_record_post, 2, 1, 1, 1)

        self._stats_record = QtWidgets.QCheckBox()
        self._layout.addWidget(self._stats_record, 3, 0, 1, 1)
        self._stats_record1 = QtWidgets.QHBoxLayout()
        self._stats_record1.addWidget(QtWidgets.QLabel(N_('Record statistics')))
        self._stats_record_config = QtWidgets.QPushButton(N_('Config'))
        self._stats_record_config.pressed.connect(self._on_statistics_record_config)
        self._stats_record1.addWidget(self._stats_record_config)
        self._layout.addLayout(self._stats_record1, 3, 1, 1, 1)
        self._stats_record_pre = IntervalWidget(None, 1.0, name=N_('Start buffer'))
        self._layout.addWidget(self._stats_record_pre, 4, 1, 1, 1)
        self._stats_record_post = IntervalWidget(None, 1.0, name=N_('Stop delay'))
        self._layout.addWidget(self._stats_record_post, 5, 1, 1, 1)

        self._output = QtWidgets.QCheckBox()
        self._layout.addWidget(self._output, 6, 0, 1, 1)
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel(N_('Set output')))
        self._output_signal = QtWidgets.QComboBox()
        self._output_signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._output_value = QtWidgets.QComboBox()
        comboBoxConfig(self._output_value, ['0', '1'], '1')
        output_layout.addWidget(self._output_signal)
        self._output_arrow = QtWidgets.QLabel('→')
        self._output_arrow.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(self._output_arrow)
        output_layout.addWidget(self._output_value)
        self._layout.addLayout(output_layout, 6, 1, 1, 1, QtCore.Qt.AlignmentFlag.AlignTop)

        self._single_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._single_marker, 7, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add single marker')), 7, 1, 1, 1)

        self._layout.setColumnStretch(1, 1)

        self._checkboxes = ['sample_record', 'stats_record', 'output', 'single_marker']

        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.toggled.connect(self._on_config_update)
        signals = [
            self._sample_record_pre.value_changed,
            self._sample_record_post.value_changed,
            self._stats_record_pre.value_changed,
            self._stats_record_post.value_changed,
            self._output_signal.currentIndexChanged,
            self._output_value.currentIndexChanged,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)
        self._visibility_update()

    @QtCore.Slot()
    def _on_sample_record_config(self):
        signal_record_config_widget.SignalRecordConfigDialog()

    def _on_statistics_record_config(self):
        StatisticsRecordConfigDialog()

    def _visibility_update(self):
        sample_record = self._sample_record.isChecked()
        self._sample_record_config.setVisible(sample_record)
        _grid_row_set_visible(self._layout, 1, sample_record)
        _grid_row_set_visible(self._layout, 2, sample_record)

        stats_record = self._stats_record.isChecked()
        self._stats_record_config.setVisible(stats_record)
        _grid_row_set_visible(self._layout, 4, stats_record)
        _grid_row_set_visible(self._layout, 5, stats_record)

        output = self._output.isChecked()
        for w in [self._output_signal, self._output_arrow, self._output_value]:
            w.setVisible(output)

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self.config
        self._visibility_update()
        self.config_changed.emit(cfg)

    @property
    def config(self):
        rv = {
            'sample_record_pre': self._sample_record_pre.value,
            'sample_record_post': self._sample_record_post.value,
            'stats_record_pre': self._stats_record_pre.value,
            'stats_record_post': self._stats_record_post.value,
            'output_signal': self._output_signal.currentText(),
            'output_value': self._output_value.currentIndex(),
        }
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            rv[checkbox_name] = checkbox.isChecked()
        return rv

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.setChecked(value[checkbox_name])
        self._sample_record_pre.value = value['sample_record_pre']
        self._sample_record_post.value = value['sample_record_post']
        self._stats_record_pre.value = value['stats_record_pre']
        self._stats_record_post.value = value['stats_record_post']
        comboBoxSelectItemByText(self._output_signal, value['output_signal'])
        block = self._output_value.blockSignals(True)
        self._output_value.setCurrentIndex(value['output_value'])
        self._output_value.blockSignals(block)
        self._visibility_update()

    def on_output_list(self, value):
        self._output_list = value
        comboBoxConfig(self._output_signal, value)


class StopActionsWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._output_list = []
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)

        self._output = QtWidgets.QCheckBox()
        self._layout.addWidget(self._output, 0, 0, 1, 1)
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel(N_('Set output')))
        self._output_signal = QtWidgets.QComboBox()
        self._output_signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._output_value = QtWidgets.QComboBox()
        comboBoxConfig(self._output_value, ['0', '1'], '0')
        output_layout.addWidget(self._output_signal)
        self._output_arrow = QtWidgets.QLabel('→')
        self._output_arrow.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(self._output_arrow)
        output_layout.addWidget(self._output_value)
        self._layout.addLayout(output_layout, 0, 1, 1, 1, QtCore.Qt.AlignmentFlag.AlignTop)

        self._single_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._single_marker, 1, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add single marker')), 1, 1, 1, 1)

        self._dual_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._dual_marker, 2, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add dual markers')), 2, 1, 1, 1)

        self._buffer_stop = QtWidgets.QCheckBox()
        self._layout.addWidget(self._buffer_stop, 3, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel('Stop sample buffer'), 3, 1, 1, 1)
        self._buffer_stop_delay = IntervalWidget(None, 1.0, name=N_('Delay'))
        self._layout.addWidget(self._buffer_stop_delay, 4, 1, 1, 1)

        self._layout.setColumnStretch(1, 1)
        self._checkboxes = ['output', 'single_marker', 'dual_marker', 'buffer_stop']

        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.toggled.connect(self._on_config_update)
        signals = [
            self._output_signal.currentIndexChanged,
            self._output_value.currentIndexChanged,
            self._buffer_stop_delay.value_changed,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)
        self._visibility_update()

    def _visibility_update(self):
        output = self._output.isChecked()
        for w in [self._output_signal, self._output_arrow, self._output_value]:
            w.setVisible(output)

        _grid_row_set_visible(self._layout, 4, self._buffer_stop.isChecked())

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self.config
        self._visibility_update()
        self.config_changed.emit(cfg)

    @property
    def config(self):
        rv = {
            'output_signal': self._output_signal.currentText(),
            'output_value': self._output_value.currentIndex(),
            'buffer_stop_delay': self._buffer_stop_delay.value,
        }
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            rv[checkbox_name] = checkbox.isChecked()
        return rv

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.setChecked(value.get(checkbox_name, False))
        comboBoxSelectItemByText(self._output_signal, value.get('output_signal', '0'))
        block = self._output_value.blockSignals(True)
        self._output_value.setCurrentIndex(value.get('output_value', 0))
        self._output_value.blockSignals(block)
        self._buffer_stop_delay.value = value.get('buffer_stop_delay', 0.0)

    def on_output_list(self, value):
        self._output_list = value
        comboBoxConfig(self._output_signal, value)


class SectionWidget(QtWidgets.QFrame):

    def __init__(self, parent, heading: str, body: QtWidgets.QFrame):
        super().__init__(parent=parent)
        self.setObjectName('SectionWidget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        heading = QtWidgets.QLabel(heading)
        heading.setProperty('section_heading', True)
        self._layout.addWidget(heading)
        body.setProperty('section_body', True)
        self._layout.addWidget(body)


@register
@styled_widget(N_('Trigger'))
class TriggerWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    SETTINGS = SETTINGS

    def __init__(self, parent=None):
        self._connected = False
        self._log = logging.getLogger(__name__)
        super().__init__(parent=parent)
        self.setObjectName('jls_info_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(6)

        self._source_selector = SourceSelector(self, 'signal_stream')
        self._source_selector.source_changed.connect(self._on_source_changed)
        self._source_selector.sources_changed.connect(self._on_sources_changed)
        self._source_selector.resolved_changed.connect(self._on_resolved_changed)

        self._error = QtWidgets.QLabel(N_('No sources found'))
        self._error.setVisible(False)
        self._layout.addWidget(self._error)

        self._header = QtWidgets.QWidget()
        self._header_layout = QtWidgets.QHBoxLayout(self._header)
        self._source = QtWidgets.QComboBox()
        self._source.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._source.setToolTip(_DEVICE_TOOLTIP)
        self._header_layout.addWidget(self._source)
        header_spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._header_layout.addItem(header_spacer)

        self._run_mode_button = QtWidgets.QPushButton()
        self._run_mode_button.setObjectName('run_mode')
        self._run_mode_button.setFlat(True)
        self._run_mode_button.setFixedSize(32, 32)
        self._run_mode_button.setCheckable(True)
        self._run_mode_button.setToolTip(_RUN_MODE_TOOLTIP)
        self._header_layout.addWidget(self._run_mode_button)
        self._run_mode_button.toggled.connect(self._on_config_update)

        self._status_button = QtWidgets.QPushButton()
        self._status_button.setObjectName('status')
        self._status_button.setProperty('status', 'inactive')
        self._status_button.setFlat(True)
        self._status_button.setFixedSize(32, 32)
        self._status_button.setCheckable(True)
        self._status_button.setToolTip(_STATUS_TOOLTIP)
        self._status_button.pressed.connect(self._on_status_button_pressed)
        self._header_layout.addWidget(self._status_button)
        self._layout.addWidget(self._header)

        self._start_condition = ConditionWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Start Condition'), self._start_condition))

        self._start_actions = StartActionsWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Start Actions'), self._start_actions))

        self._stop_condition = ConditionWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Stop Condition'), self._stop_condition))

        self._stop_actions = StopActionsWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Stop Actions'), self._stop_actions))

        for w in [self._start_condition, self._start_actions, self._stop_condition, self._stop_actions]:
            w.config_changed.connect(self._on_config_changed)

        spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(spacer)

    def _status_update(self, status):
        self._status_button.setProperty('status', status)
        style = self._status_button.style()
        style.unpolish(self._status_button)
        style.polish(self._status_button)

    def _activate(self):
        self._status_update('searching')

    @QtCore.Slot()
    def _on_status_button_pressed(self):
        status = self._status_button.property('status')
        if status == 'inactive':
            self._activate()
        elif status in ['searching', 'active']:
            self._deactivate()
        else:
            self._log.error('invalid status: %s', status)

    def _connect(self):
        resolved = self._source_selector.resolved()
        if resolved is None:
            self._connected = False
        else:
            topic = f'{get_topic_name(resolved)}/settings/signals'
            signals = self.pubsub.enumerate(topic)
            signal_names = [[s, self.pubsub.query(f'{topic}/{s}/name')] for s in signals]
            self._start_condition.on_signal_list(signal_names)
            self._stop_condition.on_signal_list(signal_names)
            output = self.pubsub.enumerate(f'{get_topic_name(resolved)}/settings/out')
            self._start_actions.on_output_list(output)
            self._stop_actions.on_output_list(output)
            self._connected, was_connected = True, self._connected
            if not was_connected:
                self._config_set(self.config)
        for item in range(self._layout.count()):
            w = self._layout.itemAt(item).widget()
            if w is not None:
                w.setVisible((w is self._error) ^ (resolved is not None))

    @QtCore.Slot(object)
    def _on_source_changed(self, value):
        self._connect()

    @QtCore.Slot(object)
    def _on_sources_changed(self, value):
        comboBoxConfig(self._source, value)

    @QtCore.Slot(object)
    def _on_resolved_changed(self, value):
        self._connect()

    @QtCore.Slot(object)
    def _on_config_changed(self, config):
        self.config = self._config_get()

    def _config_get(self):
        return {
            'run_mode': self._run_mode_button.isChecked(),
            'start_condition': self._start_condition.config,
            'start_actions': self._start_actions.config,
            'stop_condition': self._stop_condition.config,
            'stop_actions': self._stop_actions.config,
        }

    def _config_set(self, value):
        if not self._connected:
            return
        if value is None:
            return
        self._run_mode_button.setChecked(value.get('run_mode', False))
        self._start_condition.config = value['start_condition']
        self._start_actions.config = value['start_actions']
        self._stop_condition.config = value['stop_condition']
        self._stop_actions.config = value['stop_actions']

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self._config_get()
        if cfg != self.config:
            self._config_set(cfg)
            self.config = cfg

    def on_setting_config(self, value):
        if value != self.config:
            self._config_set(value)

    def on_pubsub_register(self, pubsub):
        topic = f'{self.topic}/settings/source'
        self._source_selector.on_pubsub_register(pubsub, topic)
