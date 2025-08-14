#!/usr/bin/env python3
"""UART Control 启动器"""
import sys
import os

# 确保当前目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uart_control

if __name__ == "__main__":
    uart_control.main()
