from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QFormLayout, QMessageBox, QGroupBox, QTableWidget,
                               QTableWidgetItem, QHeaderView, QWidget, QCheckBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

class BacktestDialog(QDialog):
    def __init__(self, code, name, history_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"策略回测: {name} ({code})")
        self.resize(800, 600)
        
        self.code = code
        self.name = name
        # 数据按日期正序排列（最早的在前面）
        self.all_navs = history_data.get("navs", [])[::-1]
        self.all_dates = history_data.get("dates", [])[::-1]
        
        # 兼容旧数据：如果没有日期，生成虚拟日期
        if not self.all_dates and self.all_navs:
            self.all_dates = [f"D-{len(self.all_navs)-i}" for i in range(len(self.all_navs))]

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 参数设置组
        params_group = QGroupBox("回测参数设置")
        params_layout = QFormLayout()

        # 买入条件
        buy_layout = QHBoxLayout()
        buy_layout.addWidget(QLabel("当基金在"))
        self.buy_days_input = QLineEdit("5")
        self.buy_days_input.setFixedWidth(50)
        buy_layout.addWidget(self.buy_days_input)
        buy_layout.addWidget(QLabel("日内，下跌超过"))
        self.buy_drop_input = QLineEdit("3.0")
        self.buy_drop_input.setFixedWidth(50)
        buy_layout.addWidget(self.buy_drop_input)
        buy_layout.addWidget(QLabel("% 时买入"))
        buy_layout.addStretch()

        # 卖出条件
        sell_layout = QHBoxLayout()
        sell_layout.addWidget(QLabel("在买入后持有"))
        self.hold_min_days_input = QLineEdit("7")
        self.hold_min_days_input.setFixedWidth(40)
        sell_layout.addWidget(self.hold_min_days_input)
        sell_layout.addWidget(QLabel("至"))
        self.hold_max_days_input = QLineEdit("10")
        self.hold_max_days_input.setFixedWidth(40)
        sell_layout.addWidget(self.hold_max_days_input)
        sell_layout.addWidget(QLabel("日，若期间收益大于"))
        self.target_profit_input = QLineEdit("2.0")
        self.target_profit_input.setFixedWidth(50)
        sell_layout.addWidget(self.target_profit_input)
        sell_layout.addWidget(QLabel("% 则止盈。"))
        
        self.force_sell_checkbox = QCheckBox("若未达成则期满自动卖出")
        self.force_sell_checkbox.setChecked(False)
        sell_layout.addWidget(self.force_sell_checkbox)
        
        sell_layout.addStretch()

        early_sell_layout = QHBoxLayout()
        self.early_sell_checkbox = QCheckBox("若未到最低天数，但收益率达到")
        self.early_sell_checkbox.setChecked(True)
        early_sell_layout.addWidget(self.early_sell_checkbox)
        self.early_profit_input = QLineEdit("3.5")
        self.early_profit_input.setFixedWidth(40)
        early_sell_layout.addWidget(self.early_profit_input)
        early_sell_layout.addWidget(QLabel("% 也可以提前卖出"))
        early_sell_layout.addStretch()

        params_layout.addRow(buy_layout)
        params_layout.addRow(sell_layout)
        params_layout.addRow(early_sell_layout)
        
        btn_run = QPushButton("▶ 开始回测")
        btn_run.setStyleSheet("background-color: #0097e6; color: white; padding: 5px; font-weight: bold;")
        btn_run.clicked.connect(self.run_backtest)
        params_layout.addRow(btn_run)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # 结果统计组
        stats_group = QGroupBox("回测结果")
        stats_layout = QVBoxLayout()
        
        self.lbl_date_range = QLabel("回测数据范围: -")
        self.lbl_date_range.setStyleSheet("color: #34495e; margin-bottom: 5px;")
        stats_layout.addWidget(self.lbl_date_range)
        
        stats_inner_layout = QHBoxLayout()
        self.lbl_signals = QLabel("触发买入次数: -")
        self.lbl_wins = QLabel("成功止盈次数: -")
        self.lbl_win_rate = QLabel("胜率: -")
        self.lbl_avg_profit = QLabel("平均单次收益: -")
        self.lbl_avg_wins_per_yr = QLabel("平均每年止盈: -")
        self.lbl_max_hold = QLabel("最长持有天数: -")
        stats_inner_layout.addWidget(self.lbl_signals)
        stats_inner_layout.addWidget(self.lbl_wins)
        stats_inner_layout.addWidget(self.lbl_win_rate)
        stats_inner_layout.addWidget(self.lbl_avg_profit)
        stats_inner_layout.addWidget(self.lbl_avg_wins_per_yr)
        stats_inner_layout.addWidget(self.lbl_max_hold)
        
        stats_layout.addLayout(stats_inner_layout)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # 交易记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["买入日期", "买入净值", "卖出日期", "卖出净值", "持有天数", "收益率", "结果"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def run_backtest(self):
        try:
            buy_days = int(self.buy_days_input.text().strip())
            buy_drop = float(self.buy_drop_input.text().strip()) / 100.0
            hold_min = int(self.hold_min_days_input.text().strip())
            hold_max = int(self.hold_max_days_input.text().strip())
            target_profit = float(self.target_profit_input.text().strip()) / 100.0
            early_profit = float(self.early_profit_input.text().strip()) / 100.0
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字参数！")
            return

        if len(self.all_navs) < buy_days + 1:
            QMessageBox.information(self, "数据不足", "历史数据天数不足以进行回测。")
            return

        force_sell = self.force_sell_checkbox.isChecked()
        trades = []
        i = buy_days
        
        while i < len(self.all_navs):
            # 判断买入条件：过去 buy_days 天的最高点到今天的跌幅
            nav_today = self.all_navs[i]
            nav_past_max = max(self.all_navs[i - buy_days : i + 1])
            
            drop = (nav_today - nav_past_max) / nav_past_max
            
            if drop <= -buy_drop:
                # 触发买入
                buy_date = self.all_dates[i]
                buy_nav = nav_today
                
                # 寻找卖出点
                sell_idx = i
                sell_nav = buy_nav
                sell_date = buy_date
                success = False
                actual_hold = 0
                
                for j in range(1, len(self.all_navs) - i):
                    current_nav = self.all_navs[i + j]
                    profit = (current_nav - buy_nav) / buy_nav
                    
                    if j < hold_min:
                        if self.early_sell_checkbox.isChecked() and profit >= early_profit:
                            success = True
                            actual_hold = j
                            sell_idx = i + j
                            sell_nav = current_nav
                            sell_date = self.all_dates[i + j]
                            break
                    else:
                        if profit >= target_profit:
                            success = True
                            actual_hold = j
                            sell_idx = i + j
                            sell_nav = current_nav
                            sell_date = self.all_dates[i + j]
                            break
                        
                    if force_sell and j >= hold_max:
                        actual_hold = j
                        sell_idx = i + j
                        sell_nav = current_nav
                        sell_date = self.all_dates[i + j]
                        break
                else:
                    # 数据结束仍未触发止盈或期满
                    actual_hold = len(self.all_navs) - 1 - i
                    if actual_hold > 0:
                        sell_idx = len(self.all_navs) - 1
                        sell_nav = self.all_navs[sell_idx]
                        sell_date = self.all_dates[sell_idx]
                
                # 记录交易
                final_profit = (sell_nav - buy_nav) / buy_nav if buy_nav != 0 else 0
                trades.append({
                    "buy_date": buy_date,
                    "buy_nav": buy_nav,
                    "sell_date": sell_date,
                    "sell_nav": sell_nav,
                    "hold_days": actual_hold,
                    "profit": final_profit,
                    "success": success,
                    "is_force_sell": force_sell and not success and actual_hold >= hold_max
                })
                
                # 跳过持有期，继续下一次寻找
                i = sell_idx + 1
            else:
                i += 1

        self.update_results(trades)

    def update_results(self, trades):
        self.table.setRowCount(0)
        
        start_date = self.all_dates[0] if self.all_dates else "-"
        end_date = self.all_dates[-1] if self.all_dates else "-"
        total_days = len(self.all_dates)
        self.lbl_date_range.setText(f"<b>回测数据范围:</b> {start_date} 至 {end_date} (共 {total_days} 天历史数据)")
        
        if not trades:
            self.lbl_signals.setText("触发买入次数: 0")
            self.lbl_wins.setText("成功止盈次数: 0")
            self.lbl_win_rate.setText("胜率: 0.00%")
            self.lbl_avg_profit.setText("平均单次收益: 0.00%")
            self.lbl_avg_wins_per_yr.setText("平均每年止盈: 0.0次")
            self.lbl_max_hold.setText("最长持有天数: 0天")
            return
            
        wins = sum(1 for t in trades if t["success"])
        total = len(trades)
        win_rate = wins / total * 100
        avg_profit = sum(t["profit"] for t in trades) / total * 100
        years = total_days / 250.0 if total_days > 0 else 1.0
        avg_wins_per_yr = wins / years
        max_hold = max(t["hold_days"] for t in trades)
        
        self.lbl_signals.setText(f"触发买入次数: {total}")
        self.lbl_wins.setText(f"成功止盈次数: {wins}")
        self.lbl_win_rate.setText(f"胜率: {win_rate:.2f}%")
        self.lbl_avg_profit.setText(f"平均单次收益: {avg_profit:.2f}%")
        self.lbl_avg_wins_per_yr.setText(f"平均每年止盈: {avg_wins_per_yr:.1f}次")
        self.lbl_max_hold.setText(f"最长持有天数: {max_hold}天")
        
        for idx, t in enumerate(trades):
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(t["buy_date"]))
            self.table.setItem(idx, 1, QTableWidgetItem(f"{t['buy_nav']:.4f}"))
            self.table.setItem(idx, 2, QTableWidgetItem(t["sell_date"]))
            self.table.setItem(idx, 3, QTableWidgetItem(f"{t['sell_nav']:.4f}"))
            self.table.setItem(idx, 4, QTableWidgetItem(str(t["hold_days"])))
            
            profit_item = QTableWidgetItem(f"{t['profit']*100:.2f}%")
            if t['profit'] > 0:
                profit_item.setForeground(QColor("#c0392b")) # 红涨
            elif t['profit'] < 0:
                profit_item.setForeground(QColor("#27ae60")) # 绿跌
            self.table.setItem(idx, 5, profit_item)
            
            if t["success"]:
                result_text = "止盈"
            elif t.get("is_force_sell"):
                result_text = "期满卖出"
            else:
                result_text = "未达标(持有至最新)"
                
            result_item = QTableWidgetItem(result_text)
            if t["success"]:
                result_item.setForeground(QColor("#c0392b"))
            self.table.setItem(idx, 6, result_item)
