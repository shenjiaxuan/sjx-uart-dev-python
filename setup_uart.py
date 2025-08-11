#!/usr/bin/env python3
"""
Cython 编译配置文件
用于将 uart_control.py 编译成 .so 文件
"""

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy

# 定义要编译的扩展模块
ext_modules = [
    Extension("uart_control", ["uart_control.pyx"])
]

# 配置编译选项
setup(
    name="UARTControl",
    ext_modules=cythonize(
        ext_modules,
        compiler_directives={
            'language_level': "3",  # Python 3 语法
            'boundscheck': False,    # 关闭边界检查，提升性能
            'cdivision': True        # 使用 C 语言除法规则
        }
    ),
    include_dirs=[numpy.get_include()],  # 包含 NumPy 头文件
    zip_safe=False
)