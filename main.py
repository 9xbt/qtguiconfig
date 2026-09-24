#!/usr/bin/env python3
import sys, subprocess, signal, argparse, os
import tomllib, tomli_w
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit, QMenu
from PySide6.QtCore import QFile, QIODevice, Qt
from PySide6.QtGui import QAction, QIcon, QActionGroup

class MainWindow:
    def __init__(self, schema, config):
        ui_file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mainwindow.ui")
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

        self.schema_path = schema
        self.config_path = config
        self.target_group = None
        self.current = None

        if schema:
            self.open_path(schema)
        if config:
            self.open_path(config)

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
            help_label.setText(f"{opt["help"]} ({opt["name"]})")
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
        
        self.window.findChild(QAction, "actionSave").setEnabled(True)
        self.window.findChild(QAction, "actionSave_As").setEnabled(True)
        self.window.findChild(QAction, "actionReset").setEnabled(True)
    
    def load_config(self, data, tree):
        if not self.schema_path:
            QMessageBox.warning(self.window, "Load error - qtguiconfig", "Please load the schema first!")
            return

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
        
    def open_path(self, path):
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

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Open Config or Schema",
            "",
            "All Supported Files (*.toml *.config);;TOML schema (*.toml);;.config files (*.config);;All Files (*)"
        )
        if not path:
            return

        self.open_path(path)

    def save_config(self, path):
        tree = self.window.findChild(QTreeWidget, "treeWidget")

        for action in self.target_group.actions():
            if action.isChecked():
                target = action.text()

        # print(target)

        values = {"type": "config", "target": target}
        print("#pragma once\n")

        def walk(item):
            opt = item.data(0, Qt.UserRole)
            if opt["type"] == "bool":
                value = item.checkState(0) == Qt.Checked
                values[opt["name"]] = value
                print(f"#undef {opt["name"]}")
                print(f"#define {opt["name"]} {"1" if value else "0"}\n")
            elif opt["type"] == "value":
                value = opt.get("default")
                values[opt["name"]] = value
                print(f"#undef {opt["name"]}")
                print(f"#define {opt["name"]} {value}\n")

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
            ".config",
            ".config files (*.config);;All Files (*)"
        )
        if not path:
            return

        self.config_path = path
        self.save_config(self.config_path)

    def on_quit(self):
        app.quit()

    def on_reset(self):
        self.open_path(self.schema_path)

    def on_about(self):
        version = subprocess.check_output(["git", "describe", "--always", "--dirty"], text=True).strip()
        QMessageBox.information(self.window, "About qtguiconfig", "qtguiconfig " + version + "\n\nKconfig-like config tool in Python and Qt")

    def on_about_qt(self):
        QMessageBox.aboutQt(self.window, "About Qt")

def parse_args():
    parser = argparse.ArgumentParser(description="qtguiconfig - Kconfig-like config tool in Python and Qt")
    parser.add_argument("--schema", help="Path to schema TOML to load on startup")
    parser.add_argument("--config", help="Path to config TOML or .config to load on startup")
    parser.add_argument("--get", metavar="KEY", help="Dump a config value and exit")
    return parser.parse_args()

def query_conf(config, key):
    with open(config, "rb") as f:
        data = tomllib.load(f)
    if key not in data:
        print(f"qtguiconfig: {key} not found in config", file=sys.stderr)
        sys.exit(1)
    
    value = data[key]
    if (isinstance(value, bool)):
        print ("y" if value else "n")
    else:
        print(value)

if __name__ == "__main__":
    args = parse_args()
    if args.get:
        query_conf(args.config, args.get)
        sys.exit(0)

    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main_window = MainWindow(schema=args.schema, config=args.config)
    sys.exit(app.exec())
