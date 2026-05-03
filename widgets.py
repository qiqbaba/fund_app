# widgets.py
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QLabel, 
                               QGroupBox, QGridLayout, QCheckBox, QHBoxLayout, 
                               QPushButton, QMessageBox, QTableWidgetItem)

class SettingsDialog(QDialog):
    """自定义设置弹窗"""
    def __init__(self, config, current_headers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义参数与列显示设置")
        self.resize(520, 250)
        self.config = config
        self.current_headers = current_headers
        
        layout = QFormLayout(self)
        
        self.drop_input = QLineEdit(", ".join(map(str, config.get("drop_days", [2, 4]))))
        self.pct_input = QLineEdit(", ".join(map(str, config.get("percentile_months", [1, 2, 3, 6, 12, 24]))))
        
        layout.addRow(QLabel("跌幅计算天数 (逗号分隔):"), self.drop_input)
        layout.addRow(QLabel("百分位计算月数 (逗号分隔):"), self.pct_input)
        
        self.col_group = QGroupBox("表格列显示设置 (取消勾选即可隐藏)")
        grid = QGridLayout()
        self.checkboxes = {}
        
        hidden_cols = config.get("hidden_columns", [])
        
        row, col = 0, 0
        for h in current_headers:
            if h == "操作": continue 
            cb = QCheckBox(h)
            cb.setChecked(h not in hidden_cols) 
            self.checkboxes[h] = cb
            grid.addWidget(cb, row, col)
            
            col += 1
            if col > 3: 
                col = 0
                row += 1
                
        self.col_group.setLayout(grid)
        layout.addRow(self.col_group)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存配置")
        save_btn.setStyleSheet("background-color: #0097e6; color: white;")
        save_btn.clicked.connect(self.save_and_accept)
        btn_layout.addWidget(save_btn)
        layout.addRow(btn_layout)

    def save_and_accept(self):
        try:
            drops = [int(x.strip()) for x in self.drop_input.text().split(",") if x.strip().isdigit()]
            pcts = [int(x.strip()) for x in self.pct_input.text().split(",") if x.strip().isdigit()]
            self.config["drop_days"] = drops if drops else [2, 4]
            self.config["percentile_months"] = pcts if pcts else [1, 2, 3, 6, 12, 24]
            
            hidden_cols = [h for h, cb in self.checkboxes.items() if not cb.isChecked()]
            self.config["hidden_columns"] = hidden_cols
            
            self.accept()
        except Exception:
            QMessageBox.warning(self, "错误", "请输入正确的数字格式！")


class SortableTableWidgetItem(QTableWidgetItem):
    """自定义表格元素，用于实现正确的数字/百分比/多行排序"""
    def __lt__(self, other):
        t1 = self.text()
        t2 = other.text()

        def get_val(text):
            if '\n' in text:
                text = text.split('\n')[-1]
            c = text.replace('%', '').replace('+', '').replace(',', '').strip()
            try: return float(c)
            except ValueError: return text 

        v1 = get_val(t1)
        v2 = get_val(t2)

        if type(v1) == type(v2): return v1 < v2
        if isinstance(v1, str) and isinstance(v2, float): return True
        else: return False