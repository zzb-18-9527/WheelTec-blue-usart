"""全局 QSS 样式"""

MAIN_STYLE = """
QMainWindow {
    background-color: #2b2b2b;
    color: #e0e0e0;
}
QWidget {
    color: #e0e0e0;
    font-family: "Microsoft YaHei", "SimHei", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #555;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 18px;
    font-weight: bold;
    color: #8ecae6;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
}
QPushButton {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 16px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #4a4d50;
    border-color: #8ecae6;
}
QPushButton:pressed {
    background-color: #8ecae6;
    color: #1a1a2e;
}
QPushButton:disabled {
    background-color: #2b2b2b;
    color: #666;
    border-color: #3a3a3a;
}
QPushButton#btn_enable {
    background-color: #2d6a4f;
    border-color: #40916c;
    font-weight: bold;
    font-size: 14px;
}
QPushButton#btn_enable:hover {
    background-color: #40916c;
}
QPushButton#btn_enable[motor_active="true"] {
    background-color: #e63946;
    border-color: #ff6b6b;
}
QPushButton#btn_cw, QPushButton#btn_ccw {
    font-size: 15px;
    font-weight: bold;
    min-height: 36px;
}
QPushButton#btn_cw:pressed, QPushButton#btn_ccw:pressed {
    background-color: #e63946;
    color: white;
}
QLineEdit {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
    color: #e0e0e0;
}
QLineEdit:focus {
    border-color: #8ecae6;
}
QLabel#lbl_angle_01, QLabel#lbl_angle_02 {
    font-size: 22px;
    font-weight: bold;
    color: #f9c74f;
    padding: 4px;
}
QLabel#lbl_status {
    font-size: 14px;
    padding: 4px;
}
QLabel#lbl_connected {
    color: #06d6a0;
}
QLabel#lbl_disconnected {
    color: #e63946;
}
QComboBox {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
    color: #e0e0e0;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #999;
    selection-background-color: #8ecae6;
    selection-color: #000000;
}
QTextEdit {
    background-color: #1a1a2e;
    border: 1px solid #444;
    border-radius: 4px;
    font-family: "Consolas", monospace;
    font-size: 12px;
    color: #b5e48c;
}
QSpinBox, QDoubleSpinBox {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px;
    color: #e0e0e0;
}
QScrollArea {
    border: none;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background-color: #8ecae6;
    border-radius: 3px;
}
"""
