# 行人检测事件时间轴可视化工具

这是一个用于可视化行人检测事件日志的Python工具，可以生成类似智能城市传感器平台的时间轴图表。

## 功能特点

- 📊 **时间轴可视化**：将事件以垂直条形图的形式展示在24小时时间轴上
- 🎨 **美观界面**：深色主题，紫色配色方案，类似专业监控平台
- 🖱️ **交互功能**：鼠标悬停显示详细事件信息
- 📅 **日期范围选择**：支持自定义时间范围查看
- 💾 **导出图表**：可将图表保存为高分辨率PNG图片

## 依赖库

请先安装必要的Python库：

```bash
pip install matplotlib numpy
```

## 文件说明

- **visualize_motion_events.py** - 核心可视化类库
- **process_log_file.py** - 处理日志文件的命令行工具
- **sample.log** - 示例日志数据

## 使用方法

### 方法1：命令行处理日志文件

使用命令行工具处理日志文件：

```bash
# 显示所有事件
python process_log_file.py your_log_file.log

# 显示特定日期范围的事件
python process_log_file.py your_log_file.log 10/13/2025 10/14/2025

# 使用示例数据
python process_log_file.py sample.log
```

### 方法2：在代码中使用

```python
from visualize_motion_events import MotionEventVisualizer
from datetime import datetime
import matplotlib.pyplot as plt

# 读取日志数据
with open('your_log_file.log', 'r') as f:
    log_data = f.read()

# 创建可视化器
visualizer = MotionEventVisualizer(log_data)

# 生成可视化（可选择日期范围）
start = datetime(2025, 10, 13, 0, 0, 0)
end = datetime(2025, 10, 14, 23, 59, 59)
visualizer.visualize(start_date=start, end_date=end)

# 保存图表
visualizer.save_figure('output.png', dpi=300)

# 显示图表
plt.show()
```

## 日志格式要求

日志应包含以下格式的行：

```
MM/DD/YYYY HH:MM:SS [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
```

示例：
```
10/13/2025 22:00:20 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
```

## 输出示例

生成的图表包含：

- 标题：San Jose Smart City Sensor Platform - Motion Detected Events
- X轴：时间（24小时格式）
- Y轴：事件数量
- 日期范围显示
- 总事件数统计
- 紫色垂直条形图表示每小时的事件数量

### 交互功能

- **鼠标悬停**：将鼠标悬停在条形图上，会显示该时间点的详细信息
  - 事件数量
  - 精确时间戳

## 自定义配置

### 修改颜色主题

在 `visualize_motion_events.py` 中的 `visualize()` 方法：

```python
# 背景颜色
fig.patch.set_facecolor('#2b2b2b')  # 图表背景
ax.set_facecolor('#1e1e1e')         # 绘图区背景

# 条形图颜色
color='#b088d4'  # 紫色
```

### 修改图表尺寸

```python
visualizer.visualize(figsize=(16, 8))  # 宽度, 高度（英寸）
```

### 修改时间刻度间隔

```python
# 主刻度间隔（小时）
ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))  # 每6小时一个主刻度

# 次刻度间隔（小时）
ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))  # 每1小时一个次刻度
```

### 修改导出分辨率

```python
visualizer.save_figure('output.png', dpi=300)  # DPI值越高，分辨率越高
```

## 常见问题

### Q: 为什么没有显示事件？
A: 请检查：
- 日志格式是否正确
- 日期范围是否包含事件数据
- 日志文件编码是否为UTF-8

### Q: 如何调整条形图的宽度？
A: 在 `visualize()` 方法中修改 `width` 参数：

```python
bars = ax.bar(timestamps, counts, width=0.03)  # 调整这个值
```

### Q: 如何更改时间格式？
A: 修改 `DateFormatter` 的格式字符串：

```python
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))  # 24小时制
ax.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p'))  # 12小时制
```

## 示例数据统计

使用提供的示例数据：

- **总事件数**: 96个事件
- **日期范围**: 2025年10月12日 - 2025年10月15日
- **每日事件数**:
  - 10/12/2025: 6个事件
  - 10/13/2025: 42个事件
  - 10/14/2025: 28个事件
  - 10/15/2025: 20个事件

## 技术细节

### 核心类：MotionEventVisualizer

- `parse_log_data()` - 使用正则表达式解析日志
- `visualize()` - 生成matplotlib图表
- `add_hover_annotation()` - 添加交互式提示
- `save_figure()` - 保存图表为图片

### 数据处理流程

1. 读取日志数据
2. 正则表达式提取时间戳
3. 按小时分组统计
4. 生成完整时间范围（填充0值）
5. 绘制条形图
6. 添加交互功能

## 扩展功能建议

可以进一步扩展的功能：

- 支持多个摄像头数据对比
- 添加事件类型筛选
- 导出为PDF报告
- 实时监控模式
- 数据库集成
- Web界面展示

## 许可证

本工具仅供学习和开发使用。

## 联系方式

如有问题或建议，请联系开发团队。
