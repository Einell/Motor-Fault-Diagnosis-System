"""
流水线二 — 数据采集模拟层（producer.py）
==========================================
功能：模拟工业传感器实时采集振动与声学信号，通过 MQTT 协议发布。

工作流程：
  1. 逐个读取 data/ 目录下的 txt 文件
  2. 用滑动窗口（1024采样点，步长512）切分数据
  3. 将每个窗口的 X/Y/Z/Sound 波形数据 + 元数据打包为 JSON
  4. 以 0.04 秒间隔通过 MQTT 发布到 motor/sensor_data topic
  5. 全部文件处理完后循环重放，模拟持续在线监测

使用方式：
  python src/producer.py [--interval 0.04] [--loop]
"""

import os
import sys
import json
import time
import argparse
import re
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import (
    DATA_DIR,
    SKIPROWS,
    DATA_COLUMNS,
    SIGNAL_COLUMNS,
    WINDOW_SIZE,
    STEP_SIZE,
    SAMPLING_RATE,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
    LABEL_MAP,
    FILE_ENCODING,
    SEPARATOR,
)

# ============================================================
# MQTT 客户端
# ============================================================
def create_mqtt_client() -> mqtt.Client:
    """创建并连接 MQTT 客户端。"""
    client = mqtt.Client(client_id="motor_producer")
    client.on_connect = lambda c, u, f, rc: print(
        f"[MQTT] 已连接到 Broker: {MQTT_BROKER}:{MQTT_PORT} (rc={rc})"
    )
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


# ============================================================
# 数据加载
# ============================================================
def parse_filename(filepath: str) -> dict:
    """从文件名解析状态标签和转速。"""
    basename = os.path.basename(filepath)
    stem = os.path.splitext(basename)[0]
    match = re.match(r"([A-Za-z]+)_(\d+)HZ", stem, re.IGNORECASE)
    if not match:
        raise ValueError(f"无法解析文件名: {basename}")
    raw_label = match.group(1).upper()
    speed = int(match.group(2))
    label = LABEL_MAP.get(raw_label, raw_label)
    return {"filename": basename, "label": label, "speed": speed}


def load_file_data(filepath: str) -> np.ndarray:
    """加载单个文件，跳过头部，返回 X/Y/Z/Sound 四列数据。"""
    df = pd.read_csv(
        filepath, skiprows=SKIPROWS, sep=SEPARATOR, header=None,
        names=DATA_COLUMNS, encoding=FILE_ENCODING, engine="python",
    )
    return df[SIGNAL_COLUMNS].values.astype(np.float64)


# ============================================================
# 窗口发送
# ============================================================
def publish_window(
    client: mqtt.Client,
    window_data: np.ndarray,
    meta: dict,
    window_idx: int,
    seq: int,
) -> int:
    """
    将单个窗口数据打包为 JSON 并通过 MQTT 发布。

    参数:
        client:      MQTT 客户端
        window_data: (1024, 4) 数组，列序 [X, Y, Z, Sound]
        meta:        文件元数据 {"filename", "label", "speed"}
        window_idx:  当前窗口在文件中的索引
        seq:         全局消息序号

    返回:
        更新后的 seq
    """
    # JSON 不支持 numpy 数组，转换为 list
    message = {
        "seq": seq,
        "timestamp": time.time(),
        "file_name": meta["filename"],
        "true_label": meta["label"],
        "speed": meta["speed"],
        "window_index": window_idx,
        "x": window_data[:, 0].tolist(),
        "y": window_data[:, 1].tolist(),
        "z": window_data[:, 2].tolist(),
        "sound": window_data[:, 3].tolist(),
    }

    payload = json.dumps(message)
    client.publish(MQTT_TOPIC, payload, qos=0)
    return seq + 1


# ============================================================
# 主循环
# ============================================================
def run_producer(interval: float = 0.04, loop: bool = True):
    """
    主发送循环。

    参数:
        interval: 发送间隔（秒），默认 0.04s（模拟 25.6kHz 采样率下
                  采集 1024 个采样点所需的时间）
        loop:     是否循环重放
    """
    client = create_mqtt_client()
    time.sleep(0.5)  # 等待连接稳定

    data_files = sorted(Path(DATA_DIR).glob("*.txt"))
    print(f"[Producer] 找到 {len(data_files)} 个数据文件")

    global_seq = 0

    try:
        while True:
            for fp in data_files:
                meta = parse_filename(str(fp))
                print(f"\n[Producer] 开始发送: {meta['filename']} "
                      f"(标签={meta['label']}, 转速={meta['speed']}Hz)")

                # 加载数据
                signal_data = load_file_data(str(fp))
                n_samples = signal_data.shape[0]
                n_windows = (n_samples - WINDOW_SIZE) // STEP_SIZE + 1

                # 滑动窗口发送
                send_start = time.time()
                for win_idx in range(n_windows):
                    start = win_idx * STEP_SIZE
                    window_data = signal_data[start:start + WINDOW_SIZE, :]

                    tick = time.time()
                    global_seq = publish_window(
                        client, window_data, meta, win_idx, global_seq,
                    )

                    # 控制发送速率
                    elapsed = time.time() - tick
                    if elapsed < interval:
                        time.sleep(interval - elapsed)

                # 统计
                elapsed_total = time.time() - send_start
                print(f"  发送完成: {n_windows} 窗口, "
                      f"耗时 {elapsed_total:.1f}s, "
                      f"速率 {n_windows/elapsed_total:.1f} 窗口/秒")

            if not loop:
                break
            print("\n[Producer] 循环重放...")

    except KeyboardInterrupt:
        print("\n[Producer] 收到中断信号，停止发送")
    finally:
        client.loop_stop()
        client.disconnect()
        print("[Producer] 已断开 MQTT 连接")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="电机故障诊断 — 数据模拟发送器")
    parser.add_argument("--interval", type=float, default=0.04,
                        help="发送间隔（秒），默认 0.04")
    parser.add_argument("--no-loop", action="store_true",
                        help="不循环，发送完所有文件后退出")
    args = parser.parse_args()

    run_producer(interval=args.interval, loop=not args.no_loop)
