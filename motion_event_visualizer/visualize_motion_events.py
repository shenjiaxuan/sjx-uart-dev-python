"""
行人检测事件时间轴可视化工具
基于日志数据生成类似智能城市传感器平台的事件时间轴图表
"""

import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import SpanSelector
from collections import defaultdict
import numpy as np


class MotionEventVisualizer:
    """行人检测事件可视化器"""

    def __init__(self, log_data):
        """
        初始化可视化器

        Args:
            log_data: 日志数据字符串或日志数据列表
        """
        self.events = []
        self.parse_log_data(log_data)

    def parse_log_data(self, log_data):
        """
        解析日志数据，提取时间戳

        Args:
            log_data: 日志数据字符串或列表
        """
        # 正则表达式匹配时间戳格式：MM/DD/YYYY HH:MM:SS
        pattern = r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\s+\[INFO\]:\s+Processing pedestrian alert from right camera'

        if isinstance(log_data, str):
            lines = log_data.split('\n')
        else:
            lines = log_data

        for line in lines:
            match = re.search(pattern, line)
            if match:
                timestamp_str = match.group(1)
                try:
                    # 解析时间戳
                    timestamp = datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S')
                    self.events.append(timestamp)
                except ValueError as e:
                    print(f"警告: 无法解析时间戳 '{timestamp_str}': {e}")

        print(f"成功解析 {len(self.events)} 个事件")

    def visualize(self, start_date=None, end_date=None, figsize=(14, 6)):
        """
        创建事件时间轴可视化图表

        Args:
            start_date: 开始日期 (datetime对象)
            end_date: 结束日期 (datetime对象)
            figsize: 图表尺寸
        """
        if not self.events:
            print("错误: 没有事件数据可供可视化")
            return

        # 如果没有指定日期范围，使用事件的日期范围
        if start_date is None:
            start_date = min(self.events).replace(hour=0, minute=0, second=0)
        if end_date is None:
            end_date = max(self.events).replace(hour=23, minute=59, second=59)

        # 过滤指定日期范围内的事件
        filtered_events = [e for e in self.events if start_date <= e <= end_date]

        if not filtered_events:
            print(f"警告: 在 {start_date} 到 {end_date} 范围内没有事件")
            return

        # 创建图表
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor('#2b2b2b')
        ax.set_facecolor('#1e1e1e')

        # 按小时分组事件
        hourly_events = defaultdict(list)
        for event in filtered_events:
            # 将事件归入所属的小时
            hour_key = event.replace(minute=0, second=0, microsecond=0)
            hourly_events[hour_key].append(event)

        # 准备绘图数据
        timestamps = []
        counts = []

        # 生成完整的时间范围（每小时一个点）
        current = start_date.replace(minute=0, second=0, microsecond=0)
        while current <= end_date:
            timestamps.append(current)
            count = len(hourly_events.get(current, []))
            counts.append(count)
            current += timedelta(hours=1)

        # 绘制垂直条形图
        bars = ax.bar(timestamps, counts, width=0.03, color='#b088d4',
                      edgecolor='#b088d4', linewidth=0.5, alpha=0.8)

        # 设置标题和标签
        ax.set_title('San Jose Smart City Sensor Platform - Motion Detected Events',
                     fontsize=14, color='white', pad=20, loc='left')
        ax.set_xlabel('Time', fontsize=10, color='white')
        ax.set_ylabel('Events', fontsize=10, color='white')

        # 设置x轴格式
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))

        # 设置网格
        ax.grid(True, axis='y', alpha=0.2, color='gray', linestyle='-', linewidth=0.5)
        ax.grid(True, axis='x', alpha=0.1, color='gray', linestyle='-', linewidth=0.5)

        # 设置坐标轴颜色
        ax.tick_params(colors='white', which='both')
        ax.spines['bottom'].set_color('#555555')
        ax.spines['top'].set_color('#555555')
        ax.spines['left'].set_color('#555555')
        ax.spines['right'].set_color('#555555')

        # 添加日期范围显示
        date_range = f"From: {start_date.strftime('%m/%d/%Y')}  To: {end_date.strftime('%m/%d/%Y')}"
        ax.text(0.5, 1.05, date_range, transform=ax.transAxes,
                fontsize=10, color='white', ha='center')

        # 添加图例
        legend_label = f'Motion detected: {len(filtered_events)} events'
        ax.plot([], [], color='#b088d4', linewidth=10, label=legend_label)
        ax.legend(loc='upper left', framealpha=0.3, facecolor='#2b2b2b',
                 edgecolor='#555555', fontsize=9)

        # 添加鼠标悬停提示功能
        self.add_hover_annotation(fig, ax, timestamps, counts, hourly_events)

        plt.tight_layout()

        return fig, ax

    def add_hover_annotation(self, fig, ax, timestamps, counts, hourly_events):
        """
        添加鼠标悬停显示详细信息的功能

        Args:
            fig: 图表对象
            ax: 坐标轴对象
            timestamps: 时间戳列表
            counts: 事件计数列表
            hourly_events: 按小时分组的事件字典
        """
        # 创建注释框
        annot = ax.annotate("", xy=(0, 0), xytext=(20, 20),
                           textcoords="offset points",
                           bbox=dict(boxstyle="round", fc="#3b3b3b", ec="#b088d4", alpha=0.9),
                           arrowprops=dict(arrowstyle="->", color="#b088d4"),
                           color='white', fontsize=9)
        annot.set_visible(False)

        def hover(event):
            """鼠标悬停事件处理"""
            if event.inaxes == ax:
                # 查找最近的时间点
                if event.xdata is not None:
                    # 转换为时区无关的datetime对象
                    x_date = mdates.num2date(event.xdata).replace(tzinfo=None)

                    # 找到最近的小时
                    min_diff = float('inf')
                    nearest_time = None
                    nearest_count = 0

                    for ts, cnt in zip(timestamps, counts):
                        diff = abs((x_date - ts).total_seconds())
                        if diff < min_diff:
                            min_diff = diff
                            nearest_time = ts
                            nearest_count = cnt

                    # 如果鼠标足够接近某个数据点
                    if min_diff < 3600 and nearest_count > 0:  # 1小时内
                        # 获取该小时的详细事件
                        events_in_hour = hourly_events.get(nearest_time, [])

                        # 构建提示文本
                        text = f"Motion detected: {nearest_count}\n"
                        text += f"{nearest_time.strftime('%m/%d/%Y %H:%M:%S')}"

                        annot.xy = (mdates.date2num(nearest_time), nearest_count)
                        annot.set_text(text)
                        annot.set_visible(True)
                        fig.canvas.draw_idle()
                        return

            annot.set_visible(False)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect("motion_notify_event", hover)

    def save_figure(self, filename='motion_events_timeline.png', dpi=300):
        """
        保存图表到文件

        Args:
            filename: 文件名
            dpi: 分辨率
        """
        plt.savefig(filename, dpi=dpi, facecolor='#2b2b2b', edgecolor='none')
        print(f"图表已保存到: {filename}")


def main():
    """主函数 - 示例用法"""

    # 示例日志数据
    sample_log = """
10/12/2025 14:47:35 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/12/2025 14:54:28 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/12/2025 17:34:08 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/12/2025 19:20:25 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/12/2025 21:06:19 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/12/2025 22:52:36 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/13/2025 00:38:54 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/13/2025 01:22:27 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/13/2025 01:25:15 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/13/2025 01:32:08 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/13/2025 22:00:20 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/14/2025 08:31:53 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
10/14/2025 12:04:27 [INFO]: Processing pedestrian alert from right camera (cam_in_use=2)
"""

    print("=" * 60)
    print("行人检测事件时间轴可视化工具")
    print("=" * 60)

    # 创建可视化器
    visualizer = MotionEventVisualizer(sample_log)

    # 方法1: 可视化所有事件
    print("\n生成完整时间范围的可视化图表...")
    visualizer.visualize()

    # 方法2: 可视化特定日期范围
    # start = datetime(2025, 10, 13, 0, 0, 0)
    # end = datetime(2025, 10, 14, 23, 59, 59)
    # visualizer.visualize(start_date=start, end_date=end)

    # 保存图表
    visualizer.save_figure('motion_events_timeline.png')

    # 显示图表
    plt.show()

    print("\n提示: 将鼠标悬停在条形图上可以查看详细信息")


if __name__ == '__main__':
    main()
