from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel, 
                               QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, 
                               QScrollArea, QTabWidget, QPlainTextEdit)
from PySide6.QtCore import Qt

from persistra.ui.widgets.log_view import LogView


class ContextPanel(QWidget):
    """
    Inspector panel that displays and edits parameters for the selected node.
    Uses a tab bar at the top with Parameters, Info, and Log tabs.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        self.header = QLabel("Context: No Selection")
        self.header.setStyleSheet("font-weight: bold; padding: 5px;")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.header)
        
        # Tab Widget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # --- Parameters tab ---
        self._params_widget = QWidget()
        params_outer = QVBoxLayout(self._params_widget)
        params_outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self.form_widget = QWidget()
        self.form_layout = QFormLayout(self.form_widget)
        self.form_layout.setContentsMargins(10, 10, 10, 10)
        self.form_layout.setSpacing(10)

        self.scroll_area.setWidget(self.form_widget)
        params_outer.addWidget(self.scroll_area)
        self.tabs.addTab(self._params_widget, "Parameters")

        # --- Info tab ---
        self._info_widget = QWidget()
        info_layout = QVBoxLayout(self._info_widget)
        info_layout.setContentsMargins(10, 10, 10, 10)
        self.info_label = QLabel("Select a node to view info.")
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        info_layout.addWidget(self.info_label)
        self.tabs.addTab(self._info_widget, "Info")

        # --- Log tab ---
        self.log_widget = LogView()
        self.tabs.addTab(self.log_widget, "Log")

        # Current Node Reference
        self.current_node = None

    def set_node(self, node):
        """
        Rebuilds the UI based on the node's parameters.
        """
        self.current_node = node
        
        # 1. Clear previous widgets
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        if node is None:
            self.header.setText("Context: No Selection")
            self.info_label.setText("Select a node to view info.")
            self.log_widget.text_edit.clear()
            return

        # 2. Update Header
        op_name = node.operation.__class__.__name__
        self.header.setText(f"Context: {op_name}")
        
        # 3. Build Parameter widgets
        for param in node.parameters:
            current_val = getattr(param, 'value', param.default)
            
            widget = self._create_widget_for_param(param, current_val)
            if widget:
                label = QLabel(param.name)
                if hasattr(param, 'description'):
                    label.setToolTip(param.description)
                    
                self.form_layout.addRow(label, widget)

        # 4. Update Info tab
        op = node.operation
        info_lines = [
            f"<b>Name:</b> {op.name}",
            f"<b>Category:</b> {op.category}",
            f"<b>Description:</b> {getattr(op, 'description', 'N/A')}",
            f"<b>State:</b> {node.state.value}",
            "",
            "<b>Inputs:</b>",
        ]
        for s in node.input_sockets:
            info_lines.append(f"  • {s.name} ({s.socket_type})")
        info_lines.append("")
        info_lines.append("<b>Outputs:</b>")
        for s in node.output_sockets:
            info_lines.append(f"  • {s.name} ({s.socket_type})")
        self.info_label.setText("<br>".join(info_lines))

        # Switch to Parameters tab on new selection
        self.tabs.setCurrentIndex(0)

    def _create_widget_for_param(self, param, value):
        """
        Factory method to generate the correct QWidget based on parameter type.
        """
        p_type = param.__class__.__name__
        
        if p_type == "IntParam":
            widget = QSpinBox()
            widget.setRange(getattr(param, 'min_val', -9999), getattr(param, 'max_val', 9999))
            widget.setValue(int(value))
            widget.valueChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        elif p_type == "FloatParam":
            widget = QDoubleSpinBox()
            widget.setRange(getattr(param, 'min_val', -9999.0), getattr(param, 'max_val', 9999.0))
            widget.setSingleStep(0.1)
            widget.setValue(float(value))
            widget.valueChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        elif p_type == "ChoiceParam":
            widget = QComboBox()
            options = getattr(param, 'options', [])
            widget.addItems(options)
            if value in options:
                widget.setCurrentText(value)
            widget.currentTextChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        elif p_type == "StringParam":
            widget = QLineEdit()
            widget.setText(str(value))
            widget.textChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        elif p_type == "BoolParam":
            from PySide6.QtWidgets import QCheckBox
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.toggled.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget
            
        return None

    def _on_param_changed(self, param_name, new_value):
        """
        Callback to update the model when UI changes.
        """
        if self.current_node:
            self.current_node.set_parameter(param_name, new_value)
