#!/bin/bash

echo "=== UART Control 编译脚本 ==="
echo "工作目录: $(pwd)"
echo "开始时间: $(date)"

# 1. 复制 .py 文件为 .pyx
echo ""
echo "步骤 1: 创建 Cython 源文件..."
cp uart_control.py uart_control.pyx
echo "✓ 创建完成"

# 2. 编译模块
echo ""
echo "步骤 2: 编译 Cython 模块..."
python3 setup_uart.py build_ext --inplace

# 3. 检查编译结果
echo ""
echo "步骤 3: 检查编译结果..."
SO_FILE=$(ls uart_control*.so 2>/dev/null | head -n 1)
if [ -n "$SO_FILE" ]; then
    echo "✓ ${SO_FILE} 编译成功"
else
    echo "✗ uart_control.so 编译失败"
    exit 1
fi

# 4. 创建启动脚本
echo ""
echo "步骤 4: 创建启动脚本..."

cat > run_uart_control.py << 'EOF'
#!/usr/bin/env python3
"""UART Control 启动器"""
import sys
import os

# 确保当前目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uart_control

if __name__ == "__main__":
    uart_control.main()
EOF

echo "✓ 启动脚本创建完成"

# 5. 设置执行权限
echo ""
echo "步骤 5: 设置执行权限..."
chmod +x run_uart_control.py
chmod +x build_uart.sh
echo "✓ 权限设置完成"

# 6. 清理编译中间文件
echo ""
echo "步骤 6: 清理中间文件..."
rm -rf build/
rm -f uart_control.c
rm -f uart_control.pyx
echo "✓ 清理完成"

# 7. 显示结果
echo ""
echo "=== 编译完成 ==="
echo ""
echo "编译后的模块文件："
ls -lh uart_control*.so 2>/dev/null
echo ""
echo "启动脚本："
ls -lh run_uart_control.py
echo ""
echo "配置文件："
ls -lh *.json 2>/dev/null
echo ""
echo "=========================================="
echo "使用方法："
echo "  python3 run_uart_control.py    # 运行UART控制程序"
echo "=========================================="
echo ""
echo "完成时间: $(date)"