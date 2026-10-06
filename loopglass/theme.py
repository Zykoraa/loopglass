"""Terminal-inspired colors for the monitor's Qt window and tray menu."""

COLORS = {
    "background": "#0c1316",
    "surface": "#131e22",
    "raised": "#1b2a2e",
    "line": "#2b4246",
    "text": "#e4f5ef",
    "muted": "#9db8b2",
    "green": "#78f5a5",
    "cyan": "#6bdcf1",
    "amber": "#ffca72",
    "red": "#ff7884",
    "red_fill": "#c33e56",
}

WINDOW_STYLE = """
QMainWindow, QWidget#mainSurface {
    background: #0c1316;
}
QWidget {
    color: #e4f5ef;
    font-family: "Noto Sans";
    font-size: 12px;
}
QLabel#eyebrow {
    color: #78f5a5;
    font-family: "JetBrains Mono";
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel#heading {
    color: #f0fff8;
    font-family: "JetBrains Mono";
    font-size: 25px;
    font-weight: 700;
}
QLabel#countBadge {
    color: #082015;
    background: #78f5a5;
    border: 1px solid #a9ffca;
    border-radius: 10px;
    padding: 5px 12px;
    font-family: "JetBrains Mono";
    font-size: 12px;
    font-weight: 700;
}
QLabel#summary {
    color: #a8c4bd;
    font-family: "JetBrains Mono";
    font-size: 12px;
    padding: 1px 0 5px 0;
}
QTabWidget::pane {
    background: #131e22;
    border: 1px solid #2b4246;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    color: #a8c4bd;
    background: #172327;
    border: 1px solid #2b4246;
    border-bottom: 2px solid #2b4246;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 9px 14px;
    margin-right: 4px;
    font-family: "JetBrains Mono";
    font-weight: 600;
}
QTabBar::tab:hover {
    color: #6bdcf1;
    background: #203137;
}
QTabBar::tab:selected {
    color: #78f5a5;
    background: #1b2a2e;
    border-bottom: 2px solid #78f5a5;
}
QTabBar::tab:focus {
    border-color: #6bdcf1;
}
QTreeWidget {
    color: #e4f5ef;
    background: #131e22;
    alternate-background-color: #172428;
    border: none;
    outline: none;
    font-family: "JetBrains Mono";
    font-size: 12px;
    selection-background-color: #235154;
    selection-color: #f1fff9;
}
QTreeWidget::item {
    padding: 4px 6px;
    border-bottom: 1px solid #203237;
}
QTreeWidget::item:hover {
    background: #20373a;
}
QTreeWidget::item:selected, QTreeWidget::item:selected:active {
    background: #235154;
    color: #f1fff9;
}
QTreeWidget::item:focus {
    border: 1px solid #6bdcf1;
}
QHeaderView::section {
    color: #9ee8d0;
    background: #1b2a2e;
    border: none;
    border-right: 1px solid #2b4246;
    border-bottom: 1px solid #375458;
    padding: 8px 9px;
    font-family: "JetBrains Mono";
    font-size: 11px;
    font-weight: 700;
}
QPushButton {
    color: #d7ede7;
    background: #203137;
    border: 1px solid #3a575b;
    border-radius: 7px;
    padding: 8px 13px;
    font-weight: 700;
    min-height: 18px;
}
QPushButton:hover {
    color: #ffffff;
    background: #2a4145;
    border-color: #6bdcf1;
}
QPushButton:focus {
    border: 2px solid #6bdcf1;
}
QPushButton:pressed {
    background: #335257;
}
QPushButton:disabled {
    color: #708882;
    background: #1b282a;
    border-color: #2b3c3e;
}
QPushButton#openButton {
    color: #092016;
    background: #78f5a5;
    border-color: #a9ffca;
}
QPushButton#openButton:hover {
    background: #a9ffca;
}
QPushButton#openButton:disabled {
    color: #748c82;
    background: #22332c;
    border-color: #344b3c;
}
QPushButton#stopButton {
    color: #ff9fa8;
    background: #35232b;
    border-color: #b65868;
}
QPushButton#stopButton:hover {
    color: #fff0f0;
    background: #5a2d3b;
    border-color: #ff7884;
}
QPushButton#stopButton:disabled {
    color: #84666a;
    background: #2b2327;
    border-color: #49333b;
}
QPushButton#forceButton {
    color: #fff8f8;
    background: #c33e56;
    border-color: #ff8b9b;
}
QPushButton#forceButton:hover {
    background: #e1546b;
}
QPushButton#forceButton:disabled {
    color: #a98086;
    background: #54303a;
    border-color: #75515a;
}
QPushButton#refreshButton {
    color: #8ce8f5;
    background: #1c3138;
    border-color: #467a83;
}
QPushButton#refreshButton:hover {
    color: #d9faff;
    background: #294650;
    border-color: #6bdcf1;
}
QCheckBox {
    color: #b4d0c8;
    spacing: 8px;
}
QCheckBox:hover {
    color: #e4f5ef;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #72938d;
    border-radius: 4px;
    background: #18272a;
}
QCheckBox::indicator:checked {
    background: #78f5a5;
    border-color: #a9ffca;
}
QCheckBox:focus {
    color: #6bdcf1;
}
QSpinBox {
    color: #e4f5ef;
    background: #1b2a2e;
    border: 1px solid #466369;
    border-radius: 5px;
    padding: 4px 6px;
    selection-background-color: #235154;
}
QSpinBox:focus {
    border-color: #6bdcf1;
}
QStatusBar {
    color: #a8c4bd;
    background: #101a1d;
    border-top: 1px solid #2b4246;
    font-family: "JetBrains Mono";
    font-size: 11px;
}
QToolTip {
    color: #e4f5ef;
    background: #203137;
    border: 1px solid #6bdcf1;
    padding: 5px;
}
QScrollBar:vertical {
    background: #111c20;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3b5c5c;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #5a8b8b;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #111c20;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #3b5c5c;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
"""

MENU_STYLE = """
QMenu {
    color: #e4f5ef;
    background: #172327;
    border: 1px solid #3c5c60;
    padding: 5px;
    font-family: "JetBrains Mono";
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    color: #0c1316;
    background: #78f5a5;
}
QMenu::item:disabled {
    color: #77918b;
}
QMenu::separator {
    height: 1px;
    background: #3c5c60;
    margin: 5px 7px;
}
"""
