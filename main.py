#!/usr/bin/env python3
import sys, subprocess, signal
import tomllib, tomli_w
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit, QMenu
from PySide6.QtCore import QFile, QIODevice, Qt
from PySide6.QtGui import QAction, QIcon, QActionGroup

class MainWindow:
    def __init__(self):
        ui_file_name = "mainwindow.ui"
        ui_file = QFile(ui_file_name)
        if not ui_file.open(QIODevice.ReadOnly):
            print(f"Cannot open {ui_file_name}: {ui_file.errorString()}")
            sys.exit(-1)
        loader = QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)

        self.schema_path = None
        self.config_path = None
        self.target_group = None
        self.current = None
        self.connect_actions()
        self.window.findChild(QLineEdit, "itemLineEdit").hide()
        self.window.show()

    def connect_actions(self):
        self.window.findChild(QAction, "actionOpen").triggered.connect(self.on_open)
        self.window.findChild(QAction, "actionSave").triggered.connect(self.on_save)
        self.window.findChild(QAction, "actionSave_As").triggered.connect(self.on_save_as)
        self.window.findChild(QAction, "actionQuit").triggered.connect(self.on_quit)
        self.window.findChild(QAction, "actionReset").triggered.connect(self.on_reset)
        self.window.findChild(QAction, "actionAbout").triggered.connect(self.on_about)
        self.window.findChild(QAction, "actionAbout_Qt").triggered.connect(self.on_about_qt)
        self.window.findChild(QTreeWidget, "treeWidget").currentItemChanged.connect(self.on_current_changed)
        self.window.findChild(QLineEdit, "itemLineEdit").textChanged.connect(self.on_text_changed)

    def load_toml(self, path: str):
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            QMessageBox.warning(self.window, "Load error - qtguiconfig", f"Failed to load file: {e}")
            return None
        return (data.get("type"), data)

    def on_current_changed(self, current, previous):
        if (current):
            opt = current.data(0, Qt.UserRole)
            title_label = self.window.findChild(QLabel, "itemTitleLabel")
            title_label.setText(opt["prompt"])
            title_label.show()
            help_label = self.window.findChild(QLabel, "itemHelpLabel")
            help_label.setText(opt["help"])
            help_label.show()
            textbox = self.window.findChild(QLineEdit, "itemLineEdit")
            textbox.setVisible(opt["type"] == "value")
            if opt["type"] == "value":
                textbox.setText(opt["default"])
        else:
            self.window.findChild(QLabel, "itemTitleLabel").hide()
            self.window.findChild(QLabel, "itemHelpLabel").hide()
            self.window.findChild(QLineEdit, "itemLineEdit").hide()
        self.current = current

    def on_text_changed(self, text):
        opt = self.current.data(0, Qt.UserRole)
        opt["default"] = text
        self.current.setData(0, Qt.UserRole, opt)

    def load_schema(self, data, tree):
        if tree.topLevelItem(0):
            reply = QMessageBox.warning(
                self.window,
                "Reset to Defaults - qtguiconfig",
                "This will discard all current changes and reset every option to its default value. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        options = data.get("option", [])
        targets = data.get("target", [])

        menu = self.window.findChild(QMenu, "menuTarget")

        if self.target_group:
            for action in self.target_group.actions():
                self.target_group.removeAction(action)
            menu.clear()

        self.target_group = QActionGroup(self.window)
        self.target_group.setExclusive(True)

        for target in targets:
            action = QAction(target["name"], self.window)
            action.setCheckable(True)
            action.setChecked(True if target.get("default") else False)
            menu.addAction(action)
            self.target_group.addAction(action)

        tree.clear()

        items = {}

        for opt in options:
            # print(opt["name"], opt["type"], opt.get("default"))
            
            item = QTreeWidgetItem([opt["prompt"]])
            if opt["type"] == "bool":
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked if opt.get("default") else Qt.Unchecked)
            if opt["type"] == "none":
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            item.setData(0, Qt.UserRole, opt)
            items[opt["name"]] = item

        for opt in options:
            item = items[opt["name"]]
            parent = opt.get("parent")

            if parent and parent in items:
                items[parent].addChild(item)
            else:
                tree.addTopLevelItem(item)

        item = tree.topLevelItem(0)
        if not item:
            QMessageBox.warning(self.window, "Warning - qtguiconfig", "The schema appears to be empty")
            self.schema_path = None
        else:
            self.window.findChild(QAction, "actionSave").setEnabled(True)
            self.window.findChild(QAction, "actionSave_As").setEnabled(True)
            self.window.findChild(QAction, "actionReset").setEnabled(True)
    
    def load_config(self, data, tree):
        if not self.schema_path:
            QMessageBox.warning(self.window, "Load error - qtguiconfig", "Please load the schema first!")

        values = {k: v for k, v in data.items() if k != "type"}

        def walk(item):
            opt = item.data(0, Qt.UserRole)
            name = opt.get("name")
            if name in values:
                value = values[name]
                if opt["type"] == "bool":
                    item.setCheckState(0, Qt.Checked if value else Qt.Unchecked)
                elif opt["type"] == "value":
                    opt["default"] = value
                    item.setData(0, Qt.UserRole, opt)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i))

        self.window.setWindowTitle(self.config_path + " - qtguiconfig")
        
    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Open Config or Schema",
            "",
            "TOML files (*.toml);;All Files (*)"
        )
        if not path:
            return

        kind, data = self.load_toml(path)
        if data is None:
            return
        
        tree = self.window.findChild(QTreeWidget, "treeWidget")
        if kind == "schema":
            self.schema_path = path
            self.load_schema(data, tree)
        elif kind == "config":
            self.config_path = path
            self.load_config(data, tree)

    def save_config(self, path):
        tree = self.window.findChild(QTreeWidget, "treeWidget")

        for action in self.target_group.actions():
            if action.isChecked():
                target = action.text()

        # print(target)

        values = {"type": "config", "target": target}

        def walk(item):
            opt = item.data(0, Qt.UserRole)
            if opt["type"] == "bool":
                values[opt["name"]] = item.checkState(0) == Qt.Checked
            elif opt["type"] == "value":
                values[opt["name"]] = opt.get("default")

            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i))

        with open(path, "wb") as f:
            tomli_w.dump(values, f)

        self.window.setWindowTitle(self.config_path + " - qtguiconfig")

    def on_save(self):
        if not self.config_path:
            self.on_save_as()
        else:
            self.save_config(self.config_path)
            QMessageBox.information(self.window, "qtguiconfig", f"Saved to {self.config_path!r}")

    def on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save Config",
            "",
            "TOML files (*.toml);;All Files (*)"
        )
        if not path:
            return

        self.config_path = path
        self.save_config(self.config_path)

    def on_quit(self):
        app.quit()

    def on_reset(self):
        kind, data = self.load_toml(self.schema_path)
        if data is None:
            return
        
        tree = self.window.findChild(QTreeWidget, "treeWidget")
        self.load_schema(data, tree)

    def on_about(self):
        version = subprocess.check_output(["git", "describe", "--always", "--dirty"], text=True).strip()
        QMessageBox.information(self.window, "About qtguiconfig", "qtguiconfig " + version + "\n\nKconfig-like config tool in Python and Qt")

    def on_about_qt(self):
        QMessageBox.aboutQt(self.window, "About Qt")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main_window = MainWindow()
    sys.exit(app.exec())