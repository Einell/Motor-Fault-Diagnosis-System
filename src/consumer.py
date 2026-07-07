"""
流水线二 — 数据处理层（consumer.py）
======================================
功能：订阅 MQTT 实时数据 → 特征提取 → 模型推理 → 写入数据库

工作流程：
  1. 启动时加载训练好的模型包 motor_model.pkl
  2. 订阅 MQTT Topic: motor/sensor_data
  3. 接收到消息后：
     a. 解析 JSON，提取波形数据 X/Y/Z/Sound
     b. 使用与训练阶段完全相同的特征提取函数
     c. 调用模型推理，得到预测标签 + 置信度
     d. 计算各通道 RMS 值和四通道 FFT 频谱
     e. 写入 SQLite 数据库（含自动清理旧记录）
     f. 输出推理日志到控制台 + 持久化日志文件

使用方式：
  python src/consumer.py
"""

import os
import sys
import json
import time
import sqlite3
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

import numpy as np
import paho.mqtt.client as mqtt
import joblib
from scipy.fft import fft, fftfreq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import (
    MODEL_PATH,
    DB_PATH,
    DB_DIR,
    DB_MAX_RECORDS,
    LOG_DIR,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
    SAMPLING_RATE,
    LABEL_NAMES,
)
from src.feature_utils import (
    extract_features_for_window,
    FEATURE_COLUMNS,
    N_FFT,
)

# ============================================================
# 日志配置（控制台 + 文件双输出）
# ============================================================
LOG_FILENAME = f"consumer_{datetime.now().strftime('%Y%m%d')}.log"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("consumer")
logger.setLevel(logging.INFO)

# 控制台 handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
))
logger.addHandler(console_handler)

# 文件 handler（按日期命名，每 10MB 轮转，保留 30 个历史文件）
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, LOG_FILENAME),
    maxBytes=10 * 1024 * 1024,
    backupCount=30,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(file_handler)

logger.info(f"[Logger] 日志文件: {os.path.join(LOG_DIR, LOG_FILENAME)}")


# ============================================================
# 频谱计算工具
# ============================================================
def compute_spectrum(signal: np.ndarray, fs: float, n_fft: int = N_FFT) -> dict:
    """计算单通道 FFT 频谱并降采样为 JSON 格式。"""
    spectrum = np.abs(fft(signal, n=n_fft))[:n_fft // 2]
    freqs = fftfreq(n_fft, 1.0 / fs)[:n_fft // 2]
    return {
        "freqs": freqs[::10].tolist(),     # 降采样至 ~410 点
        "amps": spectrum[::10].tolist(),
    }


# ============================================================
# 数据库初始化 + 自动迁移
# ============================================================
def init_database(db_path: str) -> sqlite3.Connection:
    """创建数据库和表结构，自动迁移旧表以兼容新字段。"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-8000")  # 8MB 缓存加速读写

    conn.execute("""
        CREATE TABLE IF NOT EXISTS realtime_predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       REAL    NOT NULL,
            seq             INTEGER,
            file_name       TEXT,
            true_label      TEXT,
            predicted_label TEXT,
            confidence      REAL,
            speed           INTEGER,
            window_index    INTEGER,
            x_rms           REAL,
            y_rms           REAL,
            z_rms           REAL,
            sound_rms       REAL,
            x_waveform      TEXT,
            y_waveform      TEXT,
            z_waveform      TEXT,
            sound_waveform  TEXT,
            spectrum        TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 自动迁移：为旧数据库添加四通道频谱列
    migrations = [
        "ALTER TABLE realtime_predictions ADD COLUMN y_spectrum TEXT",
        "ALTER TABLE realtime_predictions ADD COLUMN z_spectrum TEXT",
        "ALTER TABLE realtime_predictions ADD COLUMN sound_spectrum TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            logger.info(f"[DB] 自动迁移: {sql.split('ADD COLUMN')[1].strip()}")
        except sqlite3.OperationalError:
            pass  # 列已存在，跳过

    # 为高频查询创建索引
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp
        ON realtime_predictions(timestamp DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_predicted_label
        ON realtime_predictions(predicted_label)
    """)

    conn.commit()
    logger.info(f"[DB] 数据库已初始化: {db_path}")
    return conn


# ============================================================
# 数据库自动清理
# ============================================================
def cleanup_old_records(db: sqlite3.Connection, max_records: int, lock: threading.Lock):
    """
    保留最近 max_records 条记录，删除超出部分。
    每 100 条消息调用一次，避免频繁全表扫描。
    """
    with lock:
        count = db.execute("SELECT COUNT(*) FROM realtime_predictions").fetchone()[0]
        if count > max_records:
            excess = count - max_records
            # 删除最旧的记录，保留最近的
            db.execute("""
                DELETE FROM realtime_predictions
                WHERE id <= (
                    SELECT id FROM realtime_predictions
                    ORDER BY id DESC LIMIT 1 OFFSET ?
                )
            """, (max_records,))
            db.execute("PRAGMA optimize")  # 回收空间
            db.commit()
            logger.info(
                f"[DB] 自动清理: 删除 {excess} 条旧记录 "
                f"(当前 {max_records} 条，阈值 {max_records} 条)"
            )


# ============================================================
# 模型加载
# ============================================================
def load_latest_model(models_dir: str) -> dict:
    """
    加载最新的模型文件。

    优先查找 models/ 目录下按时间戳命名的模型文件
    （motor_model_YYYYMMDD_HHMMSS.pkl），找不到则回退到
    默认的 motor_model.pkl。
    """
    # 查找带时间戳的模型文件
    if os.path.isdir(models_dir):
        candidates = sorted(
            [f for f in os.listdir(models_dir)
             if f.startswith("motor_model_") and f.endswith(".pkl")],
            reverse=True,
        )
        if candidates:
            model_path = os.path.join(models_dir, candidates[0])
            logger.info(f"[Model] 发现带版本号的模型: {candidates[0]}")
        else:
            model_path = MODEL_PATH
    else:
        model_path = MODEL_PATH

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"模型文件不存在: {model_path}\n"
            f"请先运行流水线一: python src/train_model.py"
        )

    package = joblib.load(model_path)
    logger.info(f"[Model] 模型已加载: {model_path}")
    logger.info(f"[Model] 特征维度: {len(package.get('feature_columns', []))}")
    return package


# ============================================================
# MQTT 消息处理
# ============================================================
class MotorFaultConsumer:
    """电机故障诊断消费者：接收 MQTT 消息 → 推理 → 存储。"""

    def __init__(self, model_package: dict, db_conn: sqlite3.Connection):
        self.pipeline = model_package["pipeline"]
        self.label_encoder = model_package.get("label_encoder")
        self.feature_columns = model_package.get("feature_columns", FEATURE_COLUMNS)
        self.db = db_conn
        self.lock = threading.Lock()

        # 统计
        self.total_messages = 0
        self.error_count = 0
        self.correct_count = 0
        self.start_time = time.time()
        self._cleanup_interval = 100  # 每 100 条触发一次清理

    def on_message(self, client, userdata, msg):
        """MQTT 消息回调（在 MQTT 网络线程中执行）。"""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            self._process_message(payload)
        except json.JSONDecodeError:
            logger.error("JSON 解析失败")
            self.error_count += 1
        except Exception as e:
            logger.error(f"处理消息异常: {e}")
            self.error_count += 1

    def _process_message(self, msg: dict):
        """处理单条消息：特征提取 → 推理 → 存储。"""
        # ---- 1. 解析波形数据 ----
        x_waveform = np.array(msg["x"], dtype=np.float64)
        y_waveform = np.array(msg["y"], dtype=np.float64)
        z_waveform = np.array(msg["z"], dtype=np.float64)
        s_waveform = np.array(msg["sound"], dtype=np.float64)

        window_data = np.column_stack([x_waveform, y_waveform, z_waveform, s_waveform])

        speed = msg["speed"]
        true_label = msg["true_label"]
        file_name = msg["file_name"]
        seq = msg.get("seq", 0)
        window_index = msg.get("window_index", 0)

        # ---- 2. 特征提取（与训练阶段完全相同）----
        features_dict = extract_features_for_window(
            window_data, speed_hz=speed, fs=SAMPLING_RATE,
        )
        feat_vector = np.array([
            features_dict.get(col, 0.0) for col in FEATURE_COLUMNS
        ]).reshape(1, -1)
        feat_vector = np.column_stack([feat_vector, np.array([[speed]])])

        # ---- 3. 模型推理 ----
        predicted_label = self.pipeline.predict(feat_vector)[0]
        proba = self.pipeline.predict_proba(feat_vector)[0]
        confidence = float(np.max(proba))

        # ---- 4. 计算 RMS（趋势图用）----
        rms_values = {
            "x_rms": float(np.sqrt(np.mean(np.square(x_waveform)))),
            "y_rms": float(np.sqrt(np.mean(np.square(y_waveform)))),
            "z_rms": float(np.sqrt(np.mean(np.square(z_waveform)))),
            "sound_rms": float(np.sqrt(np.mean(np.square(s_waveform)))),
        }

        # ---- 5. 计算四通道 FFT 频谱 ----
        x_spectrum = compute_spectrum(x_waveform, SAMPLING_RATE)
        y_spectrum = compute_spectrum(y_waveform, SAMPLING_RATE)
        z_spectrum = compute_spectrum(z_waveform, SAMPLING_RATE)
        sound_spectrum = compute_spectrum(s_waveform, SAMPLING_RATE)

        # ---- 6. 写入数据库 ----
        is_correct = (true_label == predicted_label)
        with self.lock:
            self.db.execute(
                """
                INSERT INTO realtime_predictions
                    (timestamp, seq, file_name, true_label, predicted_label,
                     confidence, speed, window_index,
                     x_rms, y_rms, z_rms, sound_rms,
                     x_waveform, y_waveform, z_waveform, sound_waveform,
                     spectrum, y_spectrum, z_spectrum, sound_spectrum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg["timestamp"], seq, file_name, true_label,
                    predicted_label, confidence, speed, window_index,
                    rms_values["x_rms"], rms_values["y_rms"],
                    rms_values["z_rms"], rms_values["sound_rms"],
                    json.dumps(x_waveform.tolist()),
                    json.dumps(y_waveform.tolist()),
                    json.dumps(z_waveform.tolist()),
                    json.dumps(s_waveform.tolist()),
                    json.dumps(x_spectrum),
                    json.dumps(y_spectrum),
                    json.dumps(z_spectrum),
                    json.dumps(sound_spectrum),
                ),
            )
            self.db.commit()

        # ---- 7. 日志输出 ----
        self.total_messages += 1
        if is_correct:
            self.correct_count += 1

        true_name = LABEL_NAMES.get(true_label, true_label)
        pred_name = LABEL_NAMES.get(predicted_label, predicted_label)
        status = "✓" if is_correct else "✗"

        logger.info(
            f"[#{self.total_messages:05d}] {status} "
            f"真实={true_name:<18s} 预测={pred_name:<18s} "
            f"置信度={confidence:.3f} | {file_name} win#{window_index}"
        )

        # ---- 8. 定期清理旧记录 ----
        if self.total_messages % self._cleanup_interval == 0:
            cleanup_old_records(self.db, DB_MAX_RECORDS, self.lock)

    def get_stats(self) -> dict:
        """获取运行统计。"""
        elapsed = time.time() - self.start_time
        accuracy = (
            self.correct_count / self.total_messages
            if self.total_messages > 0 else 0.0
        )
        return {
            "total_messages": self.total_messages,
            "correct_count": self.correct_count,
            "error_count": self.error_count,
            "accuracy": accuracy,
            "elapsed_seconds": elapsed,
            "msg_per_second": self.total_messages / elapsed if elapsed > 0 else 0,
        }


# ============================================================
# 主入口
# ============================================================
def main():
    print("=" * 60)
    print("  流水线二 — 在线实时推理消费者")
    print("=" * 60)

    # 1. 加载模型（自动选择最新版本）
    models_dir = os.path.dirname(MODEL_PATH)
    model_package = load_latest_model(models_dir)

    # 2. 初始化数据库
    db_conn = init_database(DB_PATH)

    # 3. 创建消费者
    consumer = MotorFaultConsumer(model_package, db_conn)

    # 4. 连接 MQTT
    mqtt_client = mqtt.Client(client_id="motor_consumer")
    mqtt_client.on_connect = lambda c, u, f, rc: (
        logger.info(f"[MQTT] 已连接 Broker (rc={rc})"),
        c.subscribe(MQTT_TOPIC, qos=0),
        logger.info(f"[MQTT] 已订阅 Topic: {MQTT_TOPIC}"),
    )
    mqtt_client.on_message = consumer.on_message

    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    logger.info(f"[MQTT] 正在连接 {MQTT_BROKER}:{MQTT_PORT}...")

    # 5. 启动 MQTT 循环（阻塞）
    try:
        print("\n  等待接收数据... (按 Ctrl+C 停止)\n")
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        print("\n[Consumer] 收到中断信号")
    finally:
        stats = consumer.get_stats()
        print(f"\n[Consumer] 运行统计:")
        print(f"  总消息数:   {stats['total_messages']}")
        print(f"  正确数:     {stats['correct_count']}")
        print(f"  错误数:     {stats['error_count']}")
        print(f"  在线准确率: {stats['accuracy']:.2%}")
        print(f"  运行时长:   {stats['elapsed_seconds']:.1f}s")
        print(f"  处理速率:   {stats['msg_per_second']:.1f} msg/s")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        db_conn.close()
        print("[Consumer] 已断开所有连接")


if __name__ == "__main__":
    main()
