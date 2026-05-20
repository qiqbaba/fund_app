from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QFormLayout, QMessageBox, QGroupBox, QTableWidget,
                               QTableWidgetItem, QHeaderView, QCheckBox, QProgressBar)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from threads import BatchOptimalStrategyFinder

class BatchBacktestWidget(QWidget):
    def __init__(self, get_fund_lists_cb, history_cache, db, parent=None):
        super().__init__(parent)
        
        self.get_fund_lists_cb = get_fund_lists_cb
        self.history_cache = history_cache
        self.db = db
        self.batch_trades_cache = {} # code -> (name, trades, date_range)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 参数设置组
        params_group = QGroupBox("回测参数设置 (将应用于所有自选基金)")
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

        # 提前止盈条件
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
        
        self.use_opt_checkbox = QCheckBox("🔥 优先应用每只基金在本地的个性化最优参数 (若无则使用上述通用参数)")
        self.use_opt_checkbox.setChecked(True)
        self.use_opt_checkbox.setStyleSheet("color: #d35400; font-weight: bold; margin-top: 5px;")
        params_layout.addRow(self.use_opt_checkbox)
        
        # 测试范围
        scope_group = QGroupBox("选择要测试的基金列表")
        scope_layout = QHBoxLayout()
        self.cb_tab0 = QCheckBox("🔥 特别关注")
        self.cb_tab0.setChecked(True)
        self.cb_tab1 = QCheckBox("⭐ 我的自选")
        self.cb_tab1.setChecked(True)
        self.cb_tab2 = QCheckBox("📈 今日涨跌榜")
        self.cb_tab3 = QCheckBox("💎 估值榜")
        
        scope_layout.addWidget(self.cb_tab0)
        scope_layout.addWidget(self.cb_tab1)
        scope_layout.addWidget(self.cb_tab2)
        scope_layout.addWidget(self.cb_tab3)
        scope_layout.addStretch()
        scope_group.setLayout(scope_layout)
        params_layout.addRow(scope_group)
        
        btn_run = QPushButton("▶ 开始批量回测")
        btn_run.setStyleSheet("background-color: #0097e6; color: white; padding: 5px; font-weight: bold;")
        btn_run.clicked.connect(self.run_batch_backtest)
        
        self.btn_optimize_all = QPushButton("🔍 批量自动寻优最佳参数")
        self.btn_optimize_all.setStyleSheet("background-color: #f39c12; color: white; padding: 5px; font-weight: bold;")
        self.btn_optimize_all.clicked.connect(self.run_batch_optimize)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_run)
        btn_layout.addWidget(self.btn_optimize_all)
        params_layout.addRow(btn_layout)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 结果统计表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["基金代码", "基金名称", "回测参数", "触发次数", "成功止盈", "胜率", "平均单次收益", "年均止盈", "最长持有"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.show_fund_details)
        layout.addWidget(self.table)

    def run_batch_backtest(self):
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

        force_sell = self.force_sell_checkbox.isChecked()
        early_sell = self.early_sell_checkbox.isChecked()
        use_opt = self.use_opt_checkbox.isChecked()

        # 确定测试的基金列表
        fund_lists = self.get_fund_lists_cb()
        test_funds_dict = {}
        if self.cb_tab0.isChecked():
            for code, name in fund_lists.get("特别关注", []):
                test_funds_dict[code] = name
        if self.cb_tab1.isChecked():
            for code, name in fund_lists.get("我的自选基金", []):
                test_funds_dict[code] = name
        if self.cb_tab2.isChecked():
            for code, name in fund_lists.get("今日指数ETF独立涨跌榜", []):
                test_funds_dict[code] = name
        if self.cb_tab3.isChecked():
            for code, name in fund_lists.get("估值榜", []):
                test_funds_dict[code] = name

        test_funds = list(test_funds_dict.items())

        if not test_funds:
            QMessageBox.information(self, "提示", "没有符合条件的基金需要测试。")
            return

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(test_funds))
        self.progress_bar.setValue(0)
        
        self.batch_trades_cache.clear()

        results = []
        for idx, (code, name) in enumerate(test_funds):
            self.progress_bar.setValue(idx)
            
            # 使用最优参数
            cur_buy_days = buy_days
            cur_buy_drop = buy_drop
            cur_hold_min = hold_min
            cur_hold_max = hold_max
            cur_target_profit = target_profit
            cur_early_profit = early_profit
            
            if use_opt:
                opt = self.db.get_optimal_strategy(code)
                if opt:
                    cur_buy_days = opt["buy_days"]
                    cur_buy_drop = opt["buy_drop"] / 100.0
                    cur_hold_min = opt["hold_min"]
                    cur_hold_max = opt["hold_max"]
                    cur_target_profit = opt["target_profit"] / 100.0
                    cur_early_profit = cur_target_profit
            
            history_data = self.history_cache.get(code)
            if not history_data:
                history_data = self.db.get_history(code)
                
            if not history_data or not history_data.get("navs"):
                continue
                
            all_navs = history_data.get("navs", [])[::-1]
            all_dates = history_data.get("dates", [])[::-1]
            
            if len(all_navs) < cur_buy_days + 1:
                continue

            # 开始单只基金的回测
            trades = []
            i = cur_buy_days
            while i < len(all_navs):
                nav_today = all_navs[i]
                nav_past_max = max(all_navs[i - cur_buy_days : i + 1])
                drop = (nav_today - nav_past_max) / nav_past_max
                
                if drop <= -cur_buy_drop:
                    buy_nav = nav_today
                    success = False
                    actual_hold = 0
                    sell_idx = i
                    sell_nav = buy_nav
                    sell_date = all_dates[i]
                    
                    for j in range(1, len(all_navs) - i):
                        current_nav = all_navs[i + j]
                        profit = (current_nav - buy_nav) / buy_nav
                        
                        target = cur_target_profit + 0.015 if j < 7 else cur_target_profit
                        
                        if j < cur_hold_min:
                            early_target = cur_early_profit + 0.015 if j < 7 else cur_early_profit
                            if early_sell and profit >= early_target:
                                success = True
                                actual_hold = j
                                sell_idx = i + j
                                sell_nav = current_nav
                                sell_date = all_dates[sell_idx]
                                break
                        else:
                            if profit >= target:
                                success = True
                                actual_hold = j
                                sell_idx = i + j
                                sell_nav = current_nav
                                sell_date = all_dates[sell_idx]
                                break
                                
                        if force_sell and j >= cur_hold_max:
                            actual_hold = j
                            sell_idx = i + j
                            sell_nav = current_nav
                            sell_date = all_dates[sell_idx]
                            break
                    else:
                        actual_hold = len(all_navs) - 1 - i
                        if actual_hold > 0:
                            sell_idx = len(all_navs) - 1
                            sell_nav = all_navs[sell_idx]
                            sell_date = all_dates[sell_idx]
                    
                    final_profit = (sell_nav - buy_nav) / buy_nav if buy_nav != 0 else 0
                    if actual_hold < 7:
                        final_profit -= 0.015
                        
                    trades.append({
                        "buy_date": all_dates[i],
                        "buy_nav": buy_nav,
                        "sell_date": sell_date,
                        "sell_nav": sell_nav,
                        "hold_days": actual_hold,
                        "profit": final_profit,
                        "success": success,
                        "is_force_sell": force_sell and not success and actual_hold >= cur_hold_max
                    })
                    
                    i = sell_idx + 1
                else:
                    i += 1
            
            # 统计结果
            total_trades = len(trades)
            
            start_date = all_dates[0] if all_dates else "-"
            end_date = all_dates[-1] if all_dates else "-"
            total_days = len(all_dates)
            self.batch_trades_cache[code] = (name, trades, start_date, end_date, total_days)
            
            if total_trades > 0:
                wins = sum(1 for t in trades if t["success"])
                win_rate = wins / total_trades * 100
                avg_profit = sum(t["profit"] for t in trades) / total_trades * 100
                years = total_days / 250.0 if total_days > 0 else 1.0
                avg_wins_per_yr = wins / years
                max_hold = max(t["hold_days"] for t in trades)
                param_str = f"买跌({cur_buy_days}天>{cur_buy_drop*100:.1f}%) 盈(>{cur_target_profit*100:.1f}%)"
                results.append((code, name, param_str, total_trades, wins, win_rate, avg_profit, avg_wins_per_yr, max_hold))

        self.progress_bar.setValue(len(test_funds))
        self.progress_bar.setVisible(False)
        
        # 填充表格
        self.table.setRowCount(len(results))
        for r_idx, res in enumerate(results):
            code, name, param_str, total_trades, wins, win_rate, avg_profit, avg_wins_per_yr, max_hold = res
            
            self.table.setItem(r_idx, 0, QTableWidgetItem(code))
            self.table.setItem(r_idx, 1, QTableWidgetItem(name))
            self.table.setItem(r_idx, 2, QTableWidgetItem(param_str))
            
            item_total = QTableWidgetItem()
            item_total.setData(Qt.DisplayRole, total_trades)
            self.table.setItem(r_idx, 3, item_total)
            
            item_wins = QTableWidgetItem()
            item_wins.setData(Qt.DisplayRole, wins)
            self.table.setItem(r_idx, 4, item_wins)
            
            item_rate = QTableWidgetItem()
            item_rate.setData(Qt.DisplayRole, win_rate)
            item_rate.setText(f"{win_rate:.2f}%")
            self.table.setItem(r_idx, 5, item_rate)
            
            item_profit = QTableWidgetItem()
            item_profit.setData(Qt.DisplayRole, avg_profit)
            item_profit.setText(f"{avg_profit:.2f}%")
            if avg_profit > 0:
                item_profit.setForeground(QColor("#c0392b"))
            elif avg_profit < 0:
                item_profit.setForeground(QColor("#27ae60"))
            self.table.setItem(r_idx, 6, item_profit)
            
            item_avg_wins = QTableWidgetItem()
            item_avg_wins.setData(Qt.DisplayRole, avg_wins_per_yr)
            item_avg_wins.setText(f"{avg_wins_per_yr:.1f}")
            self.table.setItem(r_idx, 7, item_avg_wins)
            
            item_max_hold = QTableWidgetItem()
            item_max_hold.setData(Qt.DisplayRole, max_hold)
            item_max_hold.setText(f"{max_hold}")
            self.table.setItem(r_idx, 8, item_max_hold)
            
        self.table.setSortingEnabled(True)

    def show_fund_details(self, index):
        row = index.row()
        code = self.table.item(row, 0).text()
        
        cache_data = self.batch_trades_cache.get(code)
        if not cache_data:
            return
            
        name, trades, start_date, end_date, total_days = cache_data
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"回测明细: {name} ({code})")
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(f"<b>回测数据范围:</b> {start_date} 至 {end_date} (共 {total_days} 天历史数据)")
        info_label.setStyleSheet("color: #34495e; padding: 5px;")
        layout.addWidget(info_label)
        
        detail_table = QTableWidget()
        detail_table.setColumnCount(7)
        detail_table.setHorizontalHeaderLabels(["买入日期", "买入净值", "卖出日期", "卖出净值", "持有天数", "收益率", "结果"])
        detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(detail_table)
        
        detail_table.setRowCount(len(trades))
        for idx, t in enumerate(trades):
            detail_table.setItem(idx, 0, QTableWidgetItem(t["buy_date"]))
            detail_table.setItem(idx, 1, QTableWidgetItem(f"{t['buy_nav']:.4f}"))
            detail_table.setItem(idx, 2, QTableWidgetItem(t["sell_date"]))
            detail_table.setItem(idx, 3, QTableWidgetItem(f"{t['sell_nav']:.4f}"))
            detail_table.setItem(idx, 4, QTableWidgetItem(str(t["hold_days"])))
            
            profit_item = QTableWidgetItem(f"{t['profit']*100:.2f}%")
            if t['profit'] > 0:
                profit_item.setForeground(QColor("#c0392b"))
            elif t['profit'] < 0:
                profit_item.setForeground(QColor("#27ae60"))
            detail_table.setItem(idx, 5, profit_item)
            
            if t["success"]:
                result_text = "止盈"
            elif t.get("is_force_sell"):
                result_text = "期满卖出"
            else:
                result_text = "未达标(持有至最新)"
                
            result_item = QTableWidgetItem(result_text)
            if t["success"]:
                result_item.setForeground(QColor("#c0392b"))
            detail_table.setItem(idx, 6, result_item)
            
        dialog.exec()

    def run_batch_optimize(self):
        fund_lists = self.get_fund_lists_cb()
        test_funds_dict = {}
        if self.cb_tab0.isChecked():
            for code, name in fund_lists.get("特别关注", []):
                test_funds_dict[code] = name
        if self.cb_tab1.isChecked():
            for code, name in fund_lists.get("我的自选基金", []):
                test_funds_dict[code] = name
        if self.cb_tab2.isChecked():
            for code, name in fund_lists.get("今日指数ETF独立涨跌榜", []):
                test_funds_dict[code] = name
        if self.cb_tab3.isChecked():
            for code, name in fund_lists.get("估值榜", []):
                test_funds_dict[code] = name

        test_funds = list(test_funds_dict.items())

        if not test_funds:
            QMessageBox.information(self, "提示", "没有符合条件的基金需要寻优。")
            return

        self.btn_optimize_all.setEnabled(False)
        self.btn_optimize_all.setText("正在准备批量寻优...")
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(test_funds))
        self.progress_bar.setValue(0)
        
        self.batch_finder = BatchOptimalStrategyFinder(test_funds, self.history_cache, self.db)
        self.batch_finder.progress_signal.connect(self.on_batch_optimize_progress)
        self.batch_finder.result_signal.connect(self.on_batch_optimize_result)
        self.batch_finder.start()
        
    def on_batch_optimize_progress(self, current, total, name):
        self.progress_bar.setValue(current)
        self.btn_optimize_all.setText(f"正在寻优 ({current}/{total}): {name}")
        
    def on_batch_optimize_result(self, result):
        self.progress_bar.setVisible(False)
        self.btn_optimize_all.setEnabled(True)
        self.btn_optimize_all.setText("🔍 批量自动寻优最佳参数")
        
        success_count = result.get("success_count", 0)
        total = result.get("total_funds", 0)
        
        QMessageBox.information(self, "批量寻优完成", f"批量寻优完成！\n成功为 {success_count} 只基金找到并保存最优参数，共检查 {total} 只。")
        self.run_batch_backtest()
