"""
QAbstractTableModel 和自定义代理，用于数据和显示的分离
数据存储在字典列表中，颜色/字体等格式在渲染时动态计算
"""

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QCheckBox, QWidget, QHBoxLayout, QVBoxLayout, QPushButton


class FundTableModel(QAbstractTableModel):
    """基金表格数据模型"""
    
    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.headers = headers
        self.data_rows = []  # 列表，每个元素是一行数据字典
        
    def rowCount(self, parent=QModelIndex()):
        return len(self.data_rows)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)
    
    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None
    
    def data(self, index, role):
        if not index.isValid() or index.row() >= len(self.data_rows):
            return None
        
        row_data = self.data_rows[index.row()]
        col = index.column()
        
        if role == Qt.DisplayRole:
            key = self.headers[col]
            return row_data.get(key, "-")
        
        elif role == Qt.UserRole:  # 原始数据，用于排序
            key = self.headers[col]
            return row_data.get(key, "-")
        
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        
        return None
    
    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        
        row_data = self.data_rows[index.row()]
        key = self.headers[index.column()]
        
        if role == Qt.EditRole:
            row_data[key] = value
            self.dataChanged.emit(index, index, [role])
            return True
        
        return False
    
    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled
    
    def insertRow(self, row, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row)
        self.data_rows.insert(row, {})
        self.endInsertRows()
        return True
    
    def removeRow(self, row, parent=QModelIndex()):
        if 0 <= row < len(self.data_rows):
            self.beginRemoveRows(parent, row, row)
            self.data_rows.pop(row)
            self.endRemoveRows()
            return True
        return False
    
    def add_row(self, row_data):
        """在末尾添加一行"""
        row = len(self.data_rows)
        self.insertRow(row)
        for col, header in enumerate(self.headers):
            idx = self.index(row, col)
            self.setData(idx, row_data.get(header, "-"), Qt.EditRole)
    
    def update_row(self, row, row_data):
        """更新指定行的所有数据"""
        if 0 <= row < len(self.data_rows):
            self.data_rows[row] = row_data
            start_idx = self.index(row, 0)
            end_idx = self.index(row, len(self.headers) - 1)
            self.dataChanged.emit(start_idx, end_idx, [Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole, Qt.BackgroundRole])
    
    def get_row_data(self, row):
        """获取指定行的完整数据"""
        if 0 <= row < len(self.data_rows):
            return self.data_rows[row].copy()
        return {}
    
    def set_row_data(self, row, data_dict):
        """设置行数据字典"""
        if 0 <= row < len(self.data_rows):
            self.data_rows[row] = data_dict
    
    def find_row_by_code(self, code):
        """查找基金代码所在的行号"""
        for i, row_data in enumerate(self.data_rows):
            if row_data.get("基金代码") == code:
                return i
        return -1
    
    def find_all_rows_by_code(self, code):
        """查找基金代码所在的所有行号"""
        rows = []
        for i, row_data in enumerate(self.data_rows):
            if row_data.get("基金代码") == code:
                rows.append(i)
        return rows
    
    def clear_all(self):
        """清空所有数据"""
        if self.data_rows:
            self.beginRemoveRows(QModelIndex(), 0, len(self.data_rows) - 1)
            self.data_rows.clear()
            self.endRemoveRows()


class FundTableDelegate(QStyledItemDelegate):
    """自定义代理，处理颜色、字体等动态渲染"""
    
    def __init__(self, table_type="my_fund", parent=None):
        """
        Args:
            table_type: "my_fund" | "ranking" | "valuation"
        """
        super().__init__(parent)
        self.table_type = table_type
    
    def paint(self, painter, option, index):
        """自定义绘制逻辑"""
        if not index.isValid():
            return
        
        # 获取模型数据
        model = index.model()
        row_data = model.data_rows[index.row()] if hasattr(model, 'data_rows') else {}
        col = index.column()
        header = model.headers[col] if col < len(model.headers) else ""
        
        # 获取文本内容
        text = index.data(Qt.DisplayRole) or "-"
        
        # 根据列头决定颜色和字体
        color, bg_color, font = self._get_cell_style(header, text, row_data)
        
        # 设置背景颜色
        if bg_color:
            painter.fillRect(option.rect, bg_color)
        else:
            painter.fillRect(option.rect, option.palette.base())
        
        # 设置文本颜色和字体
        painter.setPen(color)
        painter.setFont(font)
        
        # 居中绘制文本
        painter.drawText(option.rect, Qt.AlignCenter | Qt.TextWordWrap, text)
    
    def _get_cell_style(self, header, text, row_data):
        """
        根据列头和内容决定颜色、背景色和字体
        返回 (color, bg_color, font)
        """
        default_color = QColor("#000000")
        default_font = QFont("Arial", 10)
        
        # 涨跌类 - 红涨绿跌
        if "涨跌" in header or header in ["今日收益/\n收益率", "实时估值"]:
            try:
                # 处理多行文本（如"100.5\n+2.3%"）
                if '\n' in text:
                    last_line = text.split('\n')[-1]
                else:
                    last_line = text
                
                val_str = last_line.replace('%', '').replace('+', '').replace(',', '').strip()
                val = float(val_str)
                
                if val > 0:
                    return QColor("#ff4757"), None, default_font  # 红色涨
                elif val < 0:
                    return QColor("#2ed573"), None, default_font  # 绿色跌
                else:
                    return default_color, None, default_font  # 无涨跌
            except (ValueError, IndexError):
                pass
        
        # 百分位 - 低位绿底，高位红字
        elif "百分位" in header:
            try:
                val_str = text.replace('%', '').strip()
                val = float(val_str)
                
                if val <= 25:
                    bg = QColor("#2ed573")
                    color = QColor("white")
                    font = QFont("Arial", 10, QFont.Bold)
                    return color, bg, font
                elif val >= 75:
                    return QColor("#ff4757"), None, default_font  # 红色高位
                else:
                    return QColor("#57606f"), None, default_font  # 灰色中位
            except (ValueError, IndexError):
                pass
        
        # 估值标签（高/低）
        elif header == "估值":
            if "高" in text:
                return QColor("#ff4757"), None, QFont("Arial", 9, QFont.Bold)
            elif "低" in text:
                return QColor("#2ed573"), None, QFont("Arial", 9, QFont.Bold)
        
        # 基金名称（在估值表中根据估值颜色）
        elif header == "基金名称":
            if self.table_type == "valuation":
                is_high = "高" in row_data.get("估值", "")
                color = QColor("#ff4757") if is_high else QColor("#2ed573")
                return color, None, default_font
        
        # 板块（在排行榜中根据是否为涨榜）
        elif header == "基金板块" and self.table_type == "ranking":
            # 可根据 row_data 判断是否为涨榜
            pass
        
        return default_color, None, default_font
    
    def sizeHint(self, option, index):
        """返回单元格的建议尺寸"""
        return QSize(100, 55)


class CheckboxCellWidget(QWidget):
    """自定义复选框单元格"""
    
    def __init__(self, is_checked=False, on_change=None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.on_change = on_change
        
        if on_change:
            self.checkbox.stateChanged.connect(self._on_state_changed)
        
        layout.addWidget(self.checkbox)
    
    def _on_state_changed(self, state):
        if self.on_change:
            self.on_change(state == 2)  # 2 = Qt.Checked
    
    def set_checked(self, is_checked):
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(is_checked)
        self.checkbox.blockSignals(False)
    
    def is_checked(self):
        return self.checkbox.isChecked()


class HoldingInputWidget(QWidget):
    """自定义持有信息输入单元格"""
    
    def __init__(self, amount="", yield_rate="", on_change=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(2)
        
        self.amt_input = QLineEdit(str(amount) if amount else "")
        self.amt_input.setPlaceholderText("金额")
        self.amt_input.setStyleSheet("background: transparent; border: 1px solid #ced6e0; border-radius: 3px; padding: 1px 3px; font-size: 11px;")
        
        self.yld_input = QLineEdit(str(yield_rate) if yield_rate else "")
        self.yld_input.setPlaceholderText("收益率%")
        self.yld_input.setStyleSheet("background: transparent; border: 1px solid #ced6e0; border-radius: 3px; padding: 1px 3px; font-size: 11px;")
        
        self.on_change = on_change
        
        if on_change:
            self.amt_input.editingFinished.connect(lambda: self._on_amt_changed())
            self.yld_input.editingFinished.connect(lambda: self._on_yld_changed())
        
        layout.addWidget(self.amt_input)
        layout.addWidget(self.yld_input)
    
    def _on_amt_changed(self):
        if self.on_change:
            self.on_change('amount', self.amt_input.text())
    
    def _on_yld_changed(self):
        if self.on_change:
            self.on_change('yield_rate', self.yld_input.text())
    
    def set_amount(self, amount):
        self.amt_input.blockSignals(True)
        self.amt_input.setText(str(amount) if amount else "")
        self.amt_input.blockSignals(False)
    
    def set_yield_rate(self, yield_rate):
        self.yld_input.blockSignals(True)
        self.yld_input.setText(str(yield_rate) if yield_rate else "")
        self.yld_input.blockSignals(False)
    
    def get_amount(self):
        return self.amt_input.text()
    
    def get_yield_rate(self):
        return self.yld_input.text()


class ActionButtonWidget(QWidget):
    """自定义操作按钮单元格"""
    
    def __init__(self, text="", style="", on_click=None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        
        self.btn = QPushButton(text)
        self.btn.setStyleSheet(style or "background-color: #2ed573; color: white; border-radius: 3px; padding:2px;")
        self.on_click = on_click
        
        if on_click:
            self.btn.clicked.connect(on_click)
        
        layout.addWidget(self.btn)
    
    def set_text(self, text):
        self.btn.setText(text)
    
    def set_enabled(self, enabled):
        self.btn.setEnabled(enabled)
    
    def set_style(self, style):
        self.btn.setStyleSheet(style)
    
    def get_button(self):
        return self.btn
