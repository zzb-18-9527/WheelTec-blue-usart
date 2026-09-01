"""F32C 二维云台远控程序 - 主入口"""
import sys
import os
import traceback

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import qInstallMessageHandler
from gimbal_controller.connection.ble_manager import BLEManager
from gimbal_controller.connection.serial_manager import SerialManager
from gimbal_controller.ui.main_window import MainWindow
from gimbal_controller.ui.styles import MAIN_STYLE


LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")


def exception_hook(exctype, value, tb):
    """全局异常钩子，防止未捕获异常导致闪退"""
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    # 写入日志文件
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(err_msg)
    print(err_msg, file=sys.stderr)
    try:
        QMessageBox.critical(None, "程序错误",
                             f"发生未预期的错误:\n{value}\n\n日志已保存到:\n{LOG_FILE}")
    except Exception:
        pass


def main():
    # 安装全局异常钩子
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setStyleSheet(MAIN_STYLE)

    ble = BLEManager()
    serial_mgr = SerialManager()

    window = MainWindow(ble, serial_mgr)
    window.show()

    exit_code = app.exec_()

    # 清理
    try:
        ble.stop_event_loop()
    except Exception:
        pass
    try:
        serial_mgr.disconnect()
    except Exception:
        pass
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
