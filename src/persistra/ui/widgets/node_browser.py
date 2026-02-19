from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DragTreeWidget(QTreeWidget):
    """QTreeWidget subclass that handles drag with custom MIME text payload."""

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item or item.childCount() > 0:
            return  # category header — not draggable

        class_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not class_name:
            return

        mime_data = QMimeData()
        mime_data.setText(class_name)

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        pixmap = QPixmap(120, 30)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setBrush(QColor("#444"))
        painter.setPen(QColor("#FFF"))
        painter.drawRect(0, 0, 119, 29)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, item.text(0))
        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(supportedActions)


class NodeBrowser(QWidget):
    """
    Searchable tree-based operation browser.

    Operations are grouped by category. Typing in the search bar filters the
    tree in real-time (matches against operation name, description, and
    category). Leaf items can be dragged onto the canvas to create nodes.
    """

    # Category → color (dark-mode defaults; light mode is handled by ThemeManager)
    CATEGORY_COLORS = {
        "Input / Output": "#4A9EBF",
        "Preprocessing": "#6A9F5B",
        "TDA": "#9B6BB5",
        "Machine Learning": "#BF8A4A",
        "Visualization": "#BF5A5A",
        "Utility": "#7A7A8A",
        "Templates": "#5AAFAF",
        "Plugins": "#AF8A5A",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("\U0001f50d Search operations...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._filter_tree)
        layout.addWidget(self.search_bar)

        # Tree widget
        self.tree = DragTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        # Map: category name -> QTreeWidgetItem (top-level)
        self._category_items: dict[str, QTreeWidgetItem] = {}
        # Map: leaf QTreeWidgetItem -> operation class name
        self._op_items: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_operation(self, name: str, category: str = "Utility", description: str = "", class_name: str = ""):
        """Add an operation leaf under its category group."""
        if category not in self._category_items:
            cat_item = QTreeWidgetItem(self.tree, [category])
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            color = self.CATEGORY_COLORS.get(category, "#7A7A8A")
            cat_item.setForeground(0, QColor(color))
            self._category_items[category] = cat_item

        parent = self._category_items[category]
        leaf = QTreeWidgetItem(parent, [name])
        leaf.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        leaf.setData(0, Qt.ItemDataRole.UserRole, class_name or name)
        leaf.setToolTip(0, description or name)
        self._op_items[id(leaf)] = class_name or name

    def populate_from_registry(self, registry):
        """Populate the tree from an OperationRegistry."""
        categories = registry.by_category()
        for cat_name in sorted(categories.keys()):
            for op_cls in sorted(categories[cat_name], key=lambda c: c.name):
                self.add_operation(
                    op_cls.name, cat_name,
                    getattr(op_cls, "description", ""),
                    class_name=op_cls.__name__,
                )
        self.tree.expandAll()

    # ------------------------------------------------------------------
    # Search / filter
    # ------------------------------------------------------------------

    def _filter_tree(self, text: str):
        """Show only operations whose name, description, or category match *text*."""
        query = text.lower()
        for cat_name, cat_item in self._category_items.items():
            any_visible = False
            for i in range(cat_item.childCount()):
                child = cat_item.child(i)
                display_name = (child.text(0) or "").lower()
                tooltip = (child.toolTip(0) or "").lower()
                matches = (
                    not query
                    or query in display_name
                    or query in tooltip
                    or query in cat_name.lower()
                )
                child.setHidden(not matches)
                if matches:
                    any_visible = True
            cat_item.setHidden(not any_visible)
