# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Allow the user to configure the source devices displayed on the waveform.

WARNING: this widget and feature is still under development.
"""

from joulescope_ui import N_, tooltip_format
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui.ui_util import comboBoxConfig
from PySide6 import QtCore, QtGui, QtWidgets
import logging

log = logging.getLogger(__name__)
_BUTTON_SIZE = (20, 20)
_TOOLTIP_TRACE_BUTTON = tooltip_format(
    N_("Enable trace"),
    N_("""\
    Click to toggle this trace.
    
    When enabled, the waveform will display this trace.
    
    When disabled, the waveform will hide this trace."""))
_TOOLTIP_TRACE_SOURCE = tooltip_format(
    N_("Select the source"),
    N_("""\
    Select the source for this trace.
    
    "default" will use the default source which is normally configured
    using the Device Control widget."""))


class _Trace(QtWidgets.QFrame):

    def __init__(self, parent, index):
        self._index = index
        self._menu = []
        self._subsources = []
        self._subsource = None
        self._priority = None
        self._parent = parent
        super().__init__(parent)
        self.setProperty('active', False)
        self.setObjectName(f'trace_widget_{index + 1}')
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformSourceTraceLayout")
        self._layout.setContentsMargins(10, 1, 10, 1)
        self._layout.setSpacing(5)

        trace = QtWidgets.QPushButton(self)
        self._trace = trace
        trace.setObjectName(f'trace_{index + 1}')
        trace.setToolTip(_TOOLTIP_TRACE_BUTTON)
        trace.setFixedSize(*_BUTTON_SIZE)
        trace.setCheckable(True)
        self._layout.addWidget(trace)
        trace.clicked.connect(self._on_clicked)

        name = QtWidgets.QLabel(self)
        self._name = name
        name.setToolTip(_TOOLTIP_TRACE_SOURCE)
        name.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        name.mousePressEvent = self._on_name_mousePressEvent
        self._layout.addWidget(name)

    @property
    def topic(self):
        return self._parent.topic

    @property
    def pubsub(self):
        return self._parent.pubsub

    @QtCore.Slot(bool)
    def _on_clicked(self, checked):
        self._on_enable(checked)

    def _name_menu_factory(self, subsource):
        topic = f'{self.topic}/settings/trace_subsources'
        def on_action():
            value = self.pubsub.query(topic)
            if value[self._index] != subsource:
                value = list(value)
                value[self._index] = subsource
                self.pubsub.publish(topic, value)
        return on_action

    def _update(self):
        if self._priority is None or self._subsource is None:
            self._name.setText(N_('off'))
        else:
            device = self._subsource.split('.')[-1]
            self._name.setText(device)
        self.setProperty('active', self._priority == 0)
        self.style().unpolish(self)
        self.style().polish(self)

    def on_subsources(self, subsources):
        self._subsources = list(subsources)

    def on_trace_subsource(self, subsource):
        self._subsource = subsource
        self._update()

    def on_trace_priority(self, priority):
        self._priority = priority
        if priority == 0:
            block_signals_state = self._trace.blockSignals(True)
            self._trace.setChecked(True)
            self._trace.blockSignals(block_signals_state)
        self._update()

    def _on_enable(self, enabled):
        topic = f'{self.topic}/settings/trace_priority'
        value = list(self.pubsub.query(topic))
        if enabled:
            value = [None if x is None else x - 1 for x in value]
            value[self._index] = 0
            self._name.setText(self._subsource)
        else:
            value[self._index] = None
            self._name.setText('off')
        self.pubsub.publish(topic, value)

    def _on_name_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._on_enable(True)
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            self._menu.clear()
            self._menu = [menu]
            for fullname in ['default'] + self._subsources:
                subsource = fullname.split('.')[-1]
                a = QtGui.QAction(subsource, menu)
                a.triggered.connect(self._name_menu_factory(fullname))
                menu.addAction(a)
                self._menu.append(a)
            menu.popup(event.globalPos())
        event.accept()


class WaveformSourceWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        self._traces = []
        self._parent = parent
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.setObjectName("WaveformSourceWidget")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformSourceLayout")
        self._layout.setContentsMargins(-1, 1, -1, 1)
        self._layout.setSpacing(10)

        self._spacer_l = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer_l)

        for i in range(4):
            t = _Trace(self, i)
            self._layout.addWidget(t)
            self._traces.append(t)

        self._spacer_r = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer_r)

        self._subscribers = []

    @property
    def topic(self):
        return self._parent.topic

    @property
    def pubsub(self):
        return self._parent.pubsub

    def _on_subsources(self, topic, value):
        for idx, trace in enumerate(self._traces):
            trace.on_subsources(value)

    def _on_trace_subsources(self, topic, value):
        for idx, trace in enumerate(self._traces):
            trace.on_trace_subsource(value[idx])

    def _on_trace_priority(self, topic, value):
        print(f'trace priority: {value}')
        for idx, trace in enumerate(self._traces):
            trace.on_trace_priority(value[idx])

    def on_pubsub_register(self, pubsub):
        topic = self.topic
        self._subscribers = [
            [f'{topic}/settings/subsources', self._on_subsources, ['pub', 'retain']],
            [f'{topic}/settings/trace_subsources', self._on_trace_subsources, ['pub', 'retain']],
            [f'{topic}/settings/trace_priority', self._on_trace_priority, ['pub', 'retain']],
        ]
        for topic, fn, flags in self._subscribers:
            pubsub.subscribe(topic, fn, flags)

    def on_pubsub_unregister(self, pubsub):
        for topic, fn, flags in self._subscribers:
            pubsub.unsubscribe(topic, fn, flags)
