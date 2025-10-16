"""
处理实际日志文件并生成可视化图表
读取日志文件，提取行人检测事件，生成时间轴图表
"""

import sys
from datetime import datetime
from visualize_motion_events import MotionEventVisualizer


def read_log_file(file_path):
    """
    读取日志文件

    Args:
        file_path: 日志文件路径

    Returns:
        日志内容字符串
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"错误: 找不到文件 '{file_path}'")
        return None
    except Exception as e:
        print(f"错误: 读取文件时出错: {e}")
        return None


def main():
    """主函数"""

    print("=" * 70)
    print("行人检测事件时间轴可视化工具 - 日志文件处理")
    print("=" * 70)

    # 检查命令行参数
    if len(sys.argv) < 2:
        print("\n使用方法:")
        print(f"  python {sys.argv[0]} <日志文件路径> [开始日期] [结束日期]")
        print("\n示例:")
        print(f"  python {sys.argv[0]} sensor.log")
        print(f"  python {sys.argv[0]} sensor.log 10/13/2025 10/14/2025")
        print("\n如果不提供日期参数，将显示所有事件的时间范围")
        sys.exit(1)

    log_file = sys.argv[1]

    # 读取日志文件
    print(f"\n正在读取日志文件: {log_file}")
    log_data = read_log_file(log_file)

    if log_data is None:
        sys.exit(1)

    # 创建可视化器
    print("正在解析日志数据...")
    visualizer = MotionEventVisualizer(log_data)

    if not visualizer.events:
        print("错误: 没有找到任何事件数据")
        sys.exit(1)

    # 解析日期参数（如果提供）
    start_date = None
    end_date = None

    if len(sys.argv) >= 4:
        try:
            start_date = datetime.strptime(sys.argv[2], '%m/%d/%Y')
            end_date = datetime.strptime(sys.argv[3], '%m/%d/%Y').replace(
                hour=23, minute=59, second=59)
            print(f"\n使用指定的日期范围: {start_date} 到 {end_date}")
        except ValueError:
            print("警告: 日期格式错误，使用默认范围（格式应为: MM/DD/YYYY）")

    # 显示事件统计
    print(f"\n事件统计:")
    print(f"  总事件数: {len(visualizer.events)}")
    print(f"  最早事件: {min(visualizer.events)}")
    print(f"  最晚事件: {max(visualizer.events)}")

    # 生成可视化
    print("\n正在生成可视化图表...")
    visualizer.visualize(start_date=start_date, end_date=end_date)

    # 保存图表
    output_file = 'motion_events_timeline.png'
    visualizer.save_figure(output_file)

    print(f"\n✓ 图表已保存到: {output_file}")
    print("✓ 正在显示图表窗口...")
    print("\n提示:")
    print("  - 将鼠标悬停在条形图上可以查看详细信息")
    print("  - 关闭窗口以退出程序")

    # 显示图表
    import matplotlib.pyplot as plt
    plt.show()


if __name__ == '__main__':
    main()
