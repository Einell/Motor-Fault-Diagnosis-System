"""
配置文件：路径、参数、常量定义
供流水线一（train_model.py）和流水线二（consumer.py）共用
"""

import os

# ============================================================
# 项目路径
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
DB_DIR = os.path.join(BASE_DIR, "database")

MODEL_PATH = os.path.join(MODEL_DIR, "motor_model.pkl")
DB_PATH = os.path.join(DB_DIR, "motor_data.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ============================================================
# 数据库自动清理
# ============================================================
DB_MAX_RECORDS = 20000       # SQLite 保留最大记录数，超出自动删除旧记录

# ============================================================
# 数据解析参数
# ============================================================
# 文件头部行数（跳过到 "Time (seconds) and Data Channels" 之后）
SKIPROWS = 19
# 数据列名（对应 X, Y, Z, Sound, 不包含 Time）
DATA_COLUMNS = ["Time", "X", "Y", "Z", "Sound"]
SIGNAL_COLUMNS = ["X", "Y", "Z", "Sound"]  # 四个信号通道
# 文件编码
FILE_ENCODING = "utf-8"
# 列分隔符
SEPARATOR = "\t"

# ============================================================
# 滑动窗口参数
# ============================================================
WINDOW_SIZE = 1024       # 每个窗口的采样点数
STEP_SIZE = 512          # 窗口滑动步长（50% 重叠）
SAMPLING_RATE = 25600    # 采样频率 (Hz)

# ============================================================
# 异常值检测参数
# ============================================================
SIGMA_THRESHOLD = 3.0    # 3σ 原则

# ============================================================
# 频域特征参数
# ============================================================
# 转频的基频取决于转速（Hz），在运行时按文件转速动态计算
# 用于提取：转频幅值、2倍频幅值、3倍频幅值
HARMONICS = [1, 2, 3]    # 谐波倍数

# ============================================================
# 标签映射
# ============================================================
# 文件名中的状态编码 → 标准标签
LABEL_MAP = {
    "H":      "H",
    "BF":     "BF",
    "BOW":    "BOW",
    "BROKEN": "BR",
    "MISAL":  "MIS",
    "UNBAL":  "UV",
}

# 标签的完整名称（用于图表显示）
LABEL_NAMES = {
    "H":   "Healthy",
    "BF":  "Bearing Fault",
    "BOW": "Bowed Rotor",
    "BR":  "Broken Rotor Bars",
    "MIS": "Misalignment",
    "UV":  "Voltage Unbalance",
}

# 类别标签列表（按字母序固定顺序）
CLASS_LABELS = ["BF", "BOW", "BR", "H", "MIS", "UV"]

# ============================================================
# 随机森林模型参数
# ============================================================
RF_N_ESTIMATORS = 200        # 决策树数量
RF_MAX_DEPTH = 12            # 限制深度防止过拟合（跨工况泛化）
RF_MIN_SAMPLES_LEAF = 5      # 叶节点最小样本数（正则化）
RF_RANDOM_STATE = 42         # 随机种子（保证可复现）
RF_N_JOBS = -1               # 并行训练，使用全部CPU核心

# XGBoost 参数（作为替代方案）
XGB_N_ESTIMATORS = 200
XGB_MAX_DEPTH = 6
XGB_LEARNING_RATE = 0.05
XGB_SUBSAMPLE = 0.8
XGB_REG_LAMBDA = 1.0         # L2 正则化
XGB_REG_ALPHA = 0.5          # L1 正则化

# 模型选择: "rf" (随机森林) 或 "xgb" (XGBoost)
MODEL_TYPE = "rf"

# ============================================================
# MQTT 配置（流水线二使用）
# ============================================================
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "motor/sensor_data"
