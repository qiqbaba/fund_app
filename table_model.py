from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QRect, QSize, QPointF
from PySide6.QtGui import QColor, QBrush, QFont, QTextDocument, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QStyledItemDelegate, QCheckBox, QWidget, QVBoxLayout, 
                               QLineEdit, QPushButton, QHBoxLayout, QStyle)


class FundTableModel(QAbstractTableModel):
    """基金表格数据模型 - 基于 QAbstractTableModel"""
    
    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.headers = headers
        self.data_rows = []  # 存储行数据（每行是字典）
    
    def rowCount(self, parent=QModelIndex()):
        """返回行数"""
        return len(self.data_rows)
    
    def columnCount(self, parent=QModelIndex()):
        """返回列数"""
        return len(self.headers)
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """返回表头数据"""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.headers[section] if section < len(self.headers) else ""
        return None
    
    def data(self, index, role=Qt.DisplayRole):
        """返回单元格数据"""
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row < 0 or row >= len(self.data_rows) or col < 0 or col >= len(self.headers):
            return None
        
        row_data = self.data_rows[row]
        header = self.headers[col]
        cell_value = row_data.get(header, "-")
        
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return str(cell_value) if cell_value is not None else "-"
        
        # 排序角色 - 返回可排序的值
        if role == Qt.UserRole:
            return self._get_sortable_value(cell_value)
        
        # 原始历史数据角色 - 用于绘制图表
        if role == Qt.UserRole + 2:
            return row_data.get("_navs", [])
        
        return None
    
    def _get_sortable_value(self, cell_value):
        """将显示值转换为可排序的值（用于排序）"""
        if cell_value is None or cell_value == "-":
            return (0, "")  # 负数优先级最低，空字符串排最后
        
        cell_str = str(cell_value).strip()
        
        # 处理百分比
        if "%" in cell_str:
            parts = cell_str.replace("%", "").split()
            if parts:
                try:
                    return (2, float(parts[0]))
                except ValueError:
                    return (0, cell_str)
        
        # 处理数字
        try:
            return (2, float(cell_str))
        except ValueError:
            # 处理多行数据（如 "持有金额\n收益率"）
            first_line = cell_str.split('\n')[0].strip()
            try:
                return (2, float(first_line.replace("%", "")))
            except ValueError:
                return (1, cell_str)
    
    def sort(self, column, order=Qt.AscendingOrder):
        """排序"""
        if column < 0 or column >= len(self.headers):
            return
        
        header = self.headers[column]
        
        # 根据列排序数据
        reverse = order == Qt.DescendingOrder
        
        def get_sort_key(row_data):
            # 获取置顶状态
            is_pinned = row_data.get("_is_pinned", False)
            
            cell_value = row_data.get(header, "-")
            val = self._get_sortable_value(cell_value)
            
            # 置顶逻辑：置顶项始终在最上方
            # 在升序排列时，置顶项优先级为 0，普通项为 1
            # 在降序排列时，置顶项优先级为 1，普通项为 0
            pin_priority = 1 if is_pinned else 0
            if not reverse:
                pin_priority = 0 if is_pinned else 1
                
            return (pin_priority, val)
        
        self.layoutAboutToBeChanged.emit()
        self.data_rows.sort(key=get_sort_key, reverse=reverse)
        self.layoutChanged.emit()
    
    def add_row(self, row_data):
        """添加一行数据"""
        row_count = len(self.data_rows)
        self.beginInsertRows(QModelIndex(), row_count, row_count)
        self.data_rows.append(row_data)
        self.endInsertRows()
    
    def update_row(self, row, row_data):
        """更新指定行的数据"""
        if row < 0 or row >= len(self.data_rows):
            return
        
        self.data_rows[row] = row_data
        
        # 通知视图该行已更改
        start_index = self.index(row, 0)
        end_index = self.index(row, len(self.headers) - 1)
        self.dataChanged.emit(start_index, end_index)
    
    def clear_all(self):
        """清空所有数据"""
        if len(self.data_rows) > 0:
            self.beginRemoveRows(QModelIndex(), 0, len(self.data_rows) - 1)
            self.data_rows.clear()
            self.endRemoveRows()
    
    def get_row_data(self, row):
        """获取指定行的数据字典"""
        if row < 0 or row >= len(self.data_rows):
            return {}
        return self.data_rows[row]
    
    def find_row_by_code(self, code):
        """查找指定代码的行号（返回第一个匹配的行号）"""
        for i, row_data in enumerate(self.data_rows):
            if row_data.get("基金代码") == code:
                return i
        return -1
    
    def find_all_rows_by_code(self, code):
        """查找指定代码的所有行号"""
        rows = []
        for i, row_data in enumerate(self.data_rows):
            if row_data.get("基金代码") == code:
                rows.append(i)
        return rows

    def remove_row(self, row):
        """删除指定行"""
        if row < 0 or row >= len(self.data_rows):
            return False
        
        self.beginRemoveRows(QModelIndex(), row, row)
        self.data_rows.pop(row)
        self.endRemoveRows()
        return True

    def remove_row_by_code(self, code):
        """根据代码删除行（删除所有匹配的行）"""
        rows = self.find_all_rows_by_code(code)
        if not rows:
            return False
            
        # 从后往前删，避免索引偏移
        for row in sorted(rows, reverse=True):
            self.remove_row(row)
        return True


class FundTableDelegate(QStyledItemDelegate):
    """基金表格代理 - 用于自定义渲染和换行"""
    
    def __init__(self, table_type="my_fund", parent=None):
        super().__init__(parent)
        self.table_type = table_type  # my_fund, ranking, valuation
    
    def paint(self, painter, option, index):
        """自定义绘制，支持换行"""
        if not index.isValid():
            super().paint(painter, option, index)
            return
        
        # 获取单元格数据
        data = index.data(Qt.DisplayRole)
        if data is None:
            data = ""
        
        # 获取表头以判断列类型
        model = index.model()
        column = index.column()
        header = model.headers[column] if column < len(model.headers) else ""
        
        # 绘制背景
        # 获取状态
        is_selected = option.state & QStyle.State_Selected
        is_focused = option.state & QStyle.State_HasFocus
        is_hovered = option.state & QStyle.State_MouseOver
        
        # 1. 确定并绘制基础背景色 (包含红绿百分位、置顶色等)
        bg_color = self._get_background_color(data, header)
        if not bg_color:
            is_pinned = index.model().get_row_data(index.row()).get("_is_pinned", False)
            if is_pinned and header != "操作":
                bg_color = QColor("#f0f7ff") 
        
        if bg_color:
            painter.fillRect(option.rect, bg_color)
        else:
            painter.fillRect(option.rect, option.palette.base())
            
        # 2. 处理选中和悬停效果 (使用半透明叠加，不遮挡原有颜色)
        if is_selected:
            # 透明度改为 15% (约 38/255)
            selection_color = QColor(52, 152, 219, 38) 
            painter.fillRect(option.rect, selection_color)
            
            # 绘制选中行的外边框 (不绘制单元格内部垂直边框)
            border_pen = QPen(QColor(52, 152, 219, 120), 1)
            painter.setPen(border_pen)
            
            # 上下边框
            painter.drawLine(option.rect.topLeft(), option.rect.topRight())
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
            
            # 如果是第一列，画左边框
            if index.column() == 0:
                painter.drawLine(option.rect.topLeft(), option.rect.bottomLeft())
            
            # 如果是最后一列，画右边框
            if index.column() == model.columnCount() - 1:
                painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
                
        elif is_hovered:
            painter.fillRect(option.rect, QColor(0, 0, 0, 10)) # 极浅的黑色叠加层 (约 4%)
            
        # 如果有焦点，画一个点状边框 (可选，如果觉得干扰可以去掉，目前保留以增强可访问性)
        if is_focused:
            pen = QPen(QColor(52, 152, 219, 180), 1, Qt.DotLine)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        
        # 确定字体
        font = self._get_font(data, header)
        painter.setFont(font)
        
        # 确定文本颜色 - 选中时不再强制变白，保留原有的红绿颜色逻辑
        text_color = self._get_text_color(data, header)
        painter.setPen(text_color)
        
        # 对"基金名称"和"基金板块"列启用换行
        if header in ["基金名称", "基金板块"]:
            # 使用QTextDocument处理换行和对齐
            doc = QTextDocument()
            doc.setTextWidth(option.rect.width() - 4)
            # 将颜色转换为 hex 格式
            color_name = text_color.name()
            doc.setHtml(f"<div style='text-align: center; margin: 0; padding: 0; color: {color_name};'>{str(data)}</div>")
            
            painter.save()
            painter.translate(option.rect.x() + 2, option.rect.y() + 2)
            doc.drawContents(painter, QRect(0, 0, option.rect.width() - 4, option.rect.height() - 4))
            painter.restore()
        elif header == "趋势":
            # 绘制迷你走势图 (Sparkline)
            navs = index.data(Qt.UserRole + 2) # 从 UserRole + 2 获取原始数据
            if navs and isinstance(navs, list) and len(navs) > 1:
                # 即使选中也使用原始颜色，因为现在的选中效果很淡
                line_color = QColor("#0097e6")
                self._draw_sparkline(painter, option.rect, navs, line_color)
            else:
                painter.drawText(option.rect, Qt.AlignCenter, "-")
        else:
            # 其他列保持原来的绘制方式
            text = str(data)
            # 在序号列显示置顶标识
            if header == "序号" and is_pinned:
                text = "📌"
            painter.drawText(option.rect.adjusted(2, 2, -2, -2), Qt.AlignCenter | Qt.AlignVCenter, text)

    def _draw_sparkline(self, painter, rect, navs, line_color=QColor("#0097e6")):
        """在单元格内绘制迷你趋势图"""
        # 反转数据为正序 (原始数据通常是倒序)
        data = navs[::-1]
        if len(data) > 60: # 如果数据太多，进行采样以提高性能和显示效果
            step = len(data) // 60
            data = data[::step]
            
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 计算绘图区域，留出边距
        margin = 3
        draw_rect = rect.adjusted(margin, margin, -margin, -margin)
        
        # 计算极值
        max_v = max(data)
        min_v = min(data)
        v_range = max_v - min_v if max_v != min_v else 1.0
        
        # 转换坐标
        points = QPolygonF()
        x_step = draw_rect.width() / (len(data) - 1)
        for i, v in enumerate(data):
            x = draw_rect.left() + i * x_step
            y = draw_rect.bottom() - (v - min_v) / v_range * draw_rect.height()
            points.append(QPointF(x, y))
            
        # 画折线
        painter.setPen(QPen(line_color, 1.5))
        painter.drawPolyline(points)
        
        # 画起终点（可选）
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#27ae60")) # 起点绿色
        painter.drawEllipse(points[0], 2, 2)
        painter.setBrush(QColor("#e74c3c")) # 终点红色
        painter.drawEllipse(points[-1], 2, 2)
        
        painter.restore()
    
    def sizeHint(self, option, index):
        """计算单元格大小，支持换行自适应高度"""
        if not index.isValid():
            return super().sizeHint(option, index)
        
        model = index.model()
        column = index.column()
        header = model.headers[column] if column < len(model.headers) else ""
        
        # 对需要换行的列计算自适应高度
        if header in ["基金名称", "基金板块", "持有金额/\n收益率"]:
            data = index.data(Qt.DisplayRole)
            if data:
                doc = QTextDocument()
                # 根据列类型设置合适的文本宽度
                width_map = {"基金名称": 176, "基金板块": 96, "持有金额/\n收益率": 81}
                text_width = width_map.get(header, 100)
                doc.setTextWidth(text_width)
                doc.setHtml(f"<div>{str(data)}</div>")
                doc.adjustSize()
                
                # 返回自适应高度，加上padding
                height = int(doc.size().height()) + 4
                return QSize(text_width, max(height, 35))
        
        if header == "趋势":
            return QSize(80, 35)
        
        return super().sizeHint(option, index)
    
    def _get_background_color(self, data, header):
        """根据数据返回背景色"""
        if "百分位" in header:
            try:
                value = float(str(data).replace("%", "").strip())
                if value >= 80:
                    return QColor("#e74c3c")  # 高位红色背景
                elif value <= 20:
                    return QColor("#27ae60")  # 低位绿色背景
            except ValueError:
                pass
        
        # 估值榜状态颜色
        if self.table_type == "valuation":
            if header == "持有金额/\n收益率":
                if "低估" in str(data):
                    return QColor("#27ae60")  # 绿色背景
                elif "高估" in str(data):
                    return QColor("#e74c3c")  # 红色背景
                elif "适中" in str(data):
                    return QColor("#7f8c8d")  # 灰色背景
        return None  # 使用默认背景
    
    def _get_font(self, data, header):
        """根据数据返回字体"""
        font = QFont()
        font.setPointSize(9)
        
        # 对于百分位列，极端数值加粗；对于操作列，始终加粗
        if "百分位" in header:
            try:
                value = float(str(data).replace("%", "").strip())
                if value >= 80 or value <= 20:  # 高位或低位加粗
                    font.setBold(True)
            except ValueError:
                pass
        elif header == "操作":
            font.setBold(True)
            
        return font
    
    def _get_text_color(self, data, header):
        """根据数据返回文本颜色"""
        # 涨跌幅 - 红涨绿跌
        if "涨跌" in header or "收益" in header:
            try:
                value_str = str(data).strip().split('\n')[0]  # 取第一行
                value = float(value_str.replace("%", "").replace("+", "").replace(",", ""))
                if value > 0:
                    return QColor("#e74c3c")  # 红色上涨
                elif value < 0:
                    return QColor("#27ae60")  # 绿色下跌
            except ValueError:
                pass
        
        # 百分位 - 如果有背景色，则使用白色文字以增强对比度
        if "百分位" in header:
            try:
                value = float(str(data).replace("%", "").strip())
                if value >= 80 or value <= 20:
                    return QColor("#ffffff")  # 极端值背景深，使用白色文字
            except ValueError:
                pass
        
        # 估值榜状态颜色 - 使用白色文字增强对比
        if self.table_type == "valuation":
            if header == "持有金额/\n收益率":
                if any(x in str(data) for x in ["低估", "高估", "适中"]):
                    return QColor("#ffffff")
        
        # 操作列颜色
        if header == "操作":
            data_str = str(data)
            if "删除" in data_str:
                return QColor("#e74c3c")  # 红色
            elif "关注" in data_str:
                return QColor("#0097e6")  # 蓝色
            elif "已添加" in data_str:
                return QColor("#95a5a6")  # 灰色
        
        return QColor("#000000")  # 默认黑色


class CheckboxCellWidget(QWidget):
    """复选框单元格"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.checkbox = QCheckBox()
        layout = QHBoxLayout(self)
        layout.addWidget(self.checkbox)
        layout.setContentsMargins(0, 0, 0, 0)
    
    def isChecked(self):
        return self.checkbox.isChecked()
    
    def setChecked(self, checked):
        self.checkbox.setChecked(checked)


class HoldingInputWidget(QWidget):
    """持有信息输入小部件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("金额")
        
        self.yield_input = QLineEdit()
        self.yield_input.setPlaceholderText("收益率")
        
        layout.addWidget(self.amount_input)
        layout.addWidget(self.yield_input)
    
    def get_amount(self):
        return self.amount_input.text()
    
    def get_yield(self):
        return self.yield_input.text()
    
    def set_amount(self, amount):
        self.amount_input.setText(str(amount))
    
    def set_yield(self, yield_rate):
        self.yield_input.setText(str(yield_rate))


class ActionButtonWidget(QWidget):
    """操作按钮小部件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        
        self.btn_action = QPushButton("操作")
        layout.addWidget(self.btn_action)
    
    def set_text(self, text):
        self.btn_action.setText(text)
    
    def get_text(self):
        return self.btn_action.text()
