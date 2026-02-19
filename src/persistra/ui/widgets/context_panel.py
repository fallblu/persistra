from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel, 
                               QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, 
                               QScrollArea)
from PySide6.QtCore import Qt

class ContextPanel(QWidget):
    """
    Inspector panel that displays and edits parameters for the selected node.
    Ref: README.md Section 4.3
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        self.header = QLabel("Context: No Selection")
        self.header.setStyleSheet("font-weight: bold; padding: 5px; background-color: #333; color: white;")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.header)
        
        # Scroll Area for Parameters
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # Container for Form
        self.form_widget = QWidget()
        self.form_layout = QFormLayout(self.form_widget)
        self.form_layout.setContentsMargins(10, 10, 10, 10)
        self.form_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.form_widget)
        self.main_layout.addWidget(self.scroll_area)
        
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
            return

        # 2. Update Header
        # In the real backend, node.operation is an object instance
        op_name = node.operation.__class__.__name__
        self.header.setText(f"Context: {op_name}")
        
        # 3. Build Widgets via Factory Pattern
        # FIX: Iterate directly over 'node.parameters' (List[Parameter])
        # In the real backend, 'node.parameters' is a list of Parameter objects, not a dict.
        for param in node.parameters:
            # The value is stored in the 'value' attribute of the Parameter object.
            # If 'value' is not set, fall back to 'default'.
            current_val = getattr(param, 'value', param.default)
            
            widget = self._create_widget_for_param(param, current_val)
            if widget:
                label = QLabel(param.name)
                # Tooltip for description if available
                if hasattr(param, 'description'):
                    label.setToolTip(param.description)
                    
                self.form_layout.addRow(label, widget)

    def _create_widget_for_param(self, param, value):
        """
        Factory method to generate the correct QWidget based on parameter type.
        """
        p_type = param.__class__.__name__
        
        # --- Integer Parameter ---
        if p_type == "IntParam":
            widget = QSpinBox()
            # Use getattr to safely access attributes that might vary between Mock/Real backends
            widget.setRange(getattr(param, 'min_val', -9999), getattr(param, 'max_val', 9999))
            widget.setValue(int(value))
            # Two-way binding
            widget.valueChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        # --- Float Parameter ---
        elif p_type == "FloatParam":
            widget = QDoubleSpinBox()
            widget.setRange(getattr(param, 'min_val', -9999.0), getattr(param, 'max_val', 9999.0))
            widget.setSingleStep(0.1)
            widget.setValue(float(value))
            widget.valueChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        # --- Choice/Dropdown Parameter ---
        elif p_type == "ChoiceParam":
            widget = QComboBox()
            options = getattr(param, 'options', [])
            widget.addItems(options)
            # Select current value
            if value in options:
                widget.setCurrentText(value)
            widget.currentTextChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget

        # --- String Parameter ---
        elif p_type == "StringParam":
            widget = QLineEdit()
            widget.setText(str(value))
            widget.textChanged.connect(lambda v, n=param.name: self._on_param_changed(n, v))
            return widget
            
        return None

    def _on_param_changed(self, param_name, new_value):
        """
        Callback to update the model when UI changes.
        """
        if self.current_node:
            print(f"ContextPanel: Setting {param_name} -> {new_value}")
            self.current_node.set_parameter(param_name, new_value)
