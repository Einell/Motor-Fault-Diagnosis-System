"""
流水线一：离线模型训练主程序
=============================
功能：数据加载 → 清洗预处理 → 滑动窗口切分 → 特征提取
      → 数据划分 → 标准化 → 模型训练 → 模型评估 → 保存模型

数据流：
  24个txt文件 → 按文件读取清洗 → 滑动窗口切分(1024/512) → 70维特征提取
  → 分层随机划分 8:2 → StandardScaler标准化 → 随机森林训练
  → 评估(准确率/混淆矩阵/分类报告/特征重要性) → 保存模型

特征设计（v5 无量纲特征版）：
  - 时域特征全部采用无量纲指标（峭度/偏度/波峰因子/波形因子/
    脉冲因子/裕度因子），对振动幅值大小不敏感，反映波形畸变程度
  - 频域特征根据当前转速动态计算转频 fr，提取 1×fr/2×fr/3×fr 幅值
  - 零填充 FFT (n_fft=8192)，频率分辨率 ~3.1 Hz

数据划分策略：
  - 将所有 24 个文件的样本完全混合，按 8:2 分层随机划分
  - 训练集和测试集都包含全部 4 种转速的样本
  - 同时报告留一工况（Leave-One-Speed-Out）泛化指标

输出：
  - models/motor_model.pkl         训练好的模型包
  - outputs/confusion_matrix.png   混淆矩阵
  - outputs/feature_importance.png 特征重要性
  - outputs/classification_report.txt 分类报告
  - outputs/roc_curves.png        ROC曲线
  - outputs/learning_curve.png    学习曲线
"""

import os
import sys
import re
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_curve,
    auc,
    cohen_kappa_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, LabelEncoder, label_binarize
from sklearn.model_selection import (
    learning_curve,
    train_test_split,
    LeaveOneGroupOut,
)
import joblib

# 尝试导入 XGBoost（可选依赖）
try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import (
    DATA_DIR,
    MODEL_DIR,
    MODEL_PATH,
    OUTPUT_DIR,
    SKIPROWS,
    DATA_COLUMNS,
    SIGNAL_COLUMNS,
    WINDOW_SIZE,
    STEP_SIZE,
    SAMPLING_RATE,
    SIGMA_THRESHOLD,
    TRAIN_SPEEDS,
    TEST_SPEEDS,
    LABEL_MAP,
    LABEL_NAMES,
    CLASS_LABELS,
    RF_N_ESTIMATORS,
    RF_MAX_DEPTH,
    RF_MIN_SAMPLES_LEAF,
    RF_RANDOM_STATE,
    RF_N_JOBS,
    XGB_N_ESTIMATORS,
    XGB_MAX_DEPTH,
    XGB_LEARNING_RATE,
    XGB_SUBSAMPLE,
    XGB_REG_LAMBDA,
    XGB_REG_ALPHA,
    MODEL_TYPE,
    SEPARATOR,
    FILE_ENCODING,
)
from src.feature_utils import (
    extract_features_batch,
    FEATURE_COLUMNS,
    ALL_FEATURE_COLUMNS,
)

warnings.filterwarnings("ignore")

# 中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


# ============================================================
# ① 数据加载与标签解析
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
    return {"filename": basename, "raw_label": raw_label, "label": label, "speed": speed}


def get_data_files(data_dir: str) -> list:
    """获取 data/ 目录下所有 .txt 数据文件。"""
    files = sorted(Path(data_dir).glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"在 {data_dir} 中未找到 .txt 数据文件")
    file_info_list = []
    for fp in files:
        info = parse_filename(str(fp))
        info["filepath"] = str(fp)
        file_info_list.append(info)
    print(f"[数据加载] 找到 {len(file_info_list)} 个数据文件:")
    for info in file_info_list:
        print(f"  {info['filename']:20s}  →  标签={info['label']:4s}  转速={info['speed']}Hz")
    return file_info_list


# ============================================================
# ② 数据清洗
# ============================================================
def load_and_clean_single_file(filepath: str) -> np.ndarray:
    """加载单个文件，跳过头部，3σ 异常值替换为中位数。"""
    df = pd.read_csv(
        filepath, skiprows=SKIPROWS, sep=SEPARATOR, header=None,
        names=DATA_COLUMNS, encoding=FILE_ENCODING, engine="python",
    )
    signal_data = df[SIGNAL_COLUMNS].values.astype(np.float64)

    for col_idx in range(signal_data.shape[1]):
        col = signal_data[:, col_idx]
        mean_val, std_val, median_val = np.mean(col), np.std(col), np.median(col)
        lower, upper = mean_val - SIGMA_THRESHOLD * std_val, mean_val + SIGMA_THRESHOLD * std_val
        outliers = (col < lower) | (col > upper)
        if np.sum(outliers) > 0:
            signal_data[outliers, col_idx] = median_val

    return signal_data


# ============================================================
# ③ 滑动窗口切分
# ============================================================
def sliding_window_split(
    signal_data: np.ndarray,
    window_size: int = WINDOW_SIZE,
    step_size: int = STEP_SIZE,
) -> np.ndarray:
    """滑动窗口切分，返回 (n_windows, window_size, 4) 数组。"""
    n_samples = signal_data.shape[0]
    n_windows = (n_samples - window_size) // step_size + 1
    windows = np.zeros((n_windows, window_size, signal_data.shape[1]), dtype=np.float64)
    for i in range(n_windows):
        start = i * step_size
        windows[i] = signal_data[start:start + window_size, :]
    return windows


# ============================================================
# ④ 数据处理流水线：加载 → 清洗 → 切分 → 特征提取
# ============================================================
def build_dataset(file_info_list: list, verbose: bool = True) -> tuple:
    """完整数据处理流水线，返回 (X, y, speeds)。"""
    X_list, y_list, speed_list = [], [], []
    total_files = len(file_info_list)

    print(f"\n[数据处理] 开始处理 {total_files} 个文件...")
    start_time = time.time()

    for idx, info in enumerate(file_info_list):
        signal_data = load_and_clean_single_file(info["filepath"])
        windows = sliding_window_split(signal_data, WINDOW_SIZE, STEP_SIZE)
        features = extract_features_batch(windows, speed_hz=info["speed"], fs=SAMPLING_RATE)

        X_list.append(features)
        y_list.extend([info["label"]] * windows.shape[0])
        speed_list.extend([info["speed"]] * windows.shape[0])

        if verbose:
            elapsed = time.time() - start_time
            print(f"  [{idx+1:2d}/{total_files}] {info['filename']:20s} "
                  f"→ {windows.shape[0]:4d} 窗口 | 耗时 {elapsed:5.1f}s")

    X = np.vstack(X_list)
    y = np.array(y_list)
    speeds = np.array(speed_list)

    # 转速作为附加特征，帮助模型感知工况
    X = np.column_stack([X, speeds])

    total_elapsed = time.time() - start_time
    print(f"\n  总计: {X.shape[0]} 个样本, {X.shape[1]} 维特征 (含转速) "
          f"| 总耗时 {total_elapsed:.1f}s")

    return X, y, speeds


# ============================================================
# ⑤ 数据划分
# ============================================================
def split_stratified(X: np.ndarray, y: np.ndarray,
                     test_size: float = 0.2) -> tuple:
    """
    分层随机划分（推荐方案）：
    将所有 24 个文件的样本完全混合，按类别比例分层抽样 8:2。
    训练集和测试集都包含全部 4 种转速的样本。
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=RF_RANDOM_STATE,
    )

    print(f"\n[数据划分-分层随机] 训练集: {X_train.shape[0]} 样本 "
          f"({(1-test_size):.0%})")
    print(f"                   测试集: {X_test.shape[0]} 样本 "
          f"({test_size:.0%})")

    for name, y_set in [("训练集", y_train), ("测试集", y_test)]:
        unique, counts = np.unique(y_set, return_counts=True)
        dist = " | ".join([f"{u}: {c}" for u, c in zip(unique, counts)])
        print(f"  {name}分布: {dist}")

    print(f"  训练集和测试集均覆盖全部 4 种转速 (5/10/20/30 Hz)")
    return X_train, X_test, y_train, y_test


# ============================================================
# ⑥ 模型训练
# ============================================================
def train_model(X_train: np.ndarray, y_train: np.ndarray) -> tuple:
    """
    构建并训练模型 Pipeline：StandardScaler + 分类器。
    返回 (pipeline, label_encoder)。
    """
    le = LabelEncoder()

    if MODEL_TYPE == "xgb" and HAS_XGBOOST:
        y_encoded = le.fit_transform(y_train)
        print(f"\n[模型训练] XGBoost (n_estimators={XGB_N_ESTIMATORS}, "
              f"max_depth={XGB_MAX_DEPTH}, lr={XGB_LEARNING_RATE}, "
              f"subsample={XGB_SUBSAMPLE})")
        print(f"  标签编码: {dict(zip(le.classes_, range(len(le.classes_))))}")
        print(f"  L2={XGB_REG_LAMBDA}, L1={XGB_REG_ALPHA}")

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", XGBClassifier(
                n_estimators=XGB_N_ESTIMATORS, max_depth=XGB_MAX_DEPTH,
                learning_rate=XGB_LEARNING_RATE, subsample=XGB_SUBSAMPLE,
                reg_lambda=XGB_REG_LAMBDA, reg_alpha=XGB_REG_ALPHA,
                random_state=RF_RANDOM_STATE, n_jobs=RF_N_JOBS,
                eval_metric="mlogloss", verbosity=0,
            )),
        ])
    else:
        if MODEL_TYPE == "xgb" and not HAS_XGBOOST:
            print("  [警告] XGBoost 未安装，使用 Random Forest")
        y_encoded = y_train
        print(f"\n[模型训练] Random Forest (n_estimators={RF_N_ESTIMATORS}, "
              f"max_depth={RF_MAX_DEPTH}, min_samples_leaf={RF_MIN_SAMPLES_LEAF})")

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", RandomForestClassifier(
                n_estimators=RF_N_ESTIMATORS, max_depth=RF_MAX_DEPTH,
                min_samples_leaf=RF_MIN_SAMPLES_LEAF,
                random_state=RF_RANDOM_STATE, n_jobs=RF_N_JOBS,
                class_weight="balanced", oob_score=True,
            )),
        ])

    start_time = time.time()
    pipeline.fit(X_train, y_encoded)
    elapsed = time.time() - start_time

    clf = pipeline.named_steps["classifier"]
    if hasattr(clf, "oob_score_"):
        print(f"  训练完成，耗时 {elapsed:.1f}s | OOB Score: {clf.oob_score_:.4f}")
    else:
        print(f"  训练完成，耗时 {elapsed:.1f}s")

    return pipeline, le


# ============================================================
# ⑦ 模型评估
# ============================================================
def evaluate_model(
    pipeline: Pipeline,
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    label_encoder: LabelEncoder = None,
) -> dict:
    """全面评估模型，生成所有可视化图表。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    clf = pipeline.named_steps["classifier"]

    # 预测
    if label_encoder is not None and MODEL_TYPE == "xgb":
        y_train_pred = label_encoder.inverse_transform(pipeline.predict(X_train))
        y_test_pred = label_encoder.inverse_transform(pipeline.predict(X_test))
    else:
        y_train_pred = pipeline.predict(X_train)
        y_test_pred = pipeline.predict(X_test)
    y_test_proba = pipeline.predict_proba(X_test)

    train_acc = accuracy_score(y_train, y_train_pred)
    test_acc = accuracy_score(y_test, y_test_pred)
    kappa = cohen_kappa_score(y_test, y_test_pred)

    print(f"\n{'='*60}")
    print(f"  训练集准确率: {train_acc:.4f}")
    print(f"  测试集准确率: {test_acc:.4f}")
    print(f"  Kappa 系数:   {kappa:.4f}")
    print(f"{'='*60}")

    # 混淆矩阵
    cm = confusion_matrix(y_test, y_test_pred, labels=CLASS_LABELS)
    plot_confusion_matrix(cm, CLASS_LABELS)
    plot_confusion_matrix(cm, CLASS_LABELS, normalize=True)

    # 分类报告
    report = classification_report(
        y_test, y_test_pred, labels=CLASS_LABELS,
        target_names=[LABEL_NAMES[l] for l in CLASS_LABELS], digits=4,
    )
    print(f"\n[分类报告]\n{report}")

    report_path = os.path.join(OUTPUT_DIR, "classification_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"训练集准确率: {train_acc:.4f}\n")
        f.write(f"测试集准确率: {test_acc:.4f}\n")
        f.write(f"Kappa 系数:   {kappa:.4f}\n\n{report}")
    print(f"  分类报告已保存至: {report_path}")

    # 各类别指标
    precision = precision_score(y_test, y_test_pred, labels=CLASS_LABELS, average=None)
    recall = recall_score(y_test, y_test_pred, labels=CLASS_LABELS, average=None)
    f1 = f1_score(y_test, y_test_pred, labels=CLASS_LABELS, average=None)

    print(f"\n[各类别指标]")
    print(f"  {'类别':<20s} {'精确率':>8s} {'召回率':>8s} {'F1-score':>8s}")
    for i, cls in enumerate(CLASS_LABELS):
        print(f"  {LABEL_NAMES[cls]:<20s} {precision[i]:>8.4f} "
              f"{recall[i]:>8.4f} {f1[i]:>8.4f}")

    # 可视化
    plot_feature_importance(clf, ALL_FEATURE_COLUMNS)
    plot_roc_curves(y_test, CLASS_LABELS, y_test_proba)
    plot_learning_curve(clf, X_train, y_train)
    plot_classification_report_heatmap(precision, recall, f1)

    return {
        "train_acc": train_acc, "test_acc": test_acc,
        "kappa": kappa, "precision": precision,
        "recall": recall, "f1": f1,
    }


# ============================================================
# 可视化辅助函数
# ============================================================
def plot_confusion_matrix(cm: np.ndarray, class_labels: list, normalize: bool = False):
    """绘制混淆矩阵热力图。"""
    if normalize:
        cm_plot = cm.astype("float") / cm.sum(axis=1, keepdims=True)
        cm_plot = np.nan_to_num(cm_plot, 0)
        title, fname, fmt = "Normalized Confusion Matrix", "confusion_matrix_normalized.png", ".2f"
    else:
        cm_plot, title, fname, fmt = cm, "Confusion Matrix", "confusion_matrix.png", "d"

    display_labels = [LABEL_NAMES[l] for l in class_labels]
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(cm_plot, annot=True, fmt=fmt, cmap="Blues",
                xticklabels=display_labels, yticklabels=display_labels, ax=ax)
    ax.set_xlabel("Predicted Label"); ax.set_ylabel("True Label"); ax.set_title(title)
    fig.savefig(os.path.join(OUTPUT_DIR, fname), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: {fname}")


def plot_feature_importance(model, feature_names: list):
    """绘制特征重要性柱状图 (Top 20)。"""
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]
    top_n = min(20, len(feature_names))
    top_indices = indices[:top_n]

    fig, ax = plt.subplots(figsize=(12, 8))
    colors = plt.cm.viridis(np.linspace(0, 1, top_n))
    ax.barh(range(top_n), importances[top_indices], color=colors[::-1],
            edgecolor="gray", linewidth=0.5)
    ax.set_yticks(range(top_n))
    ax.set_yticklabels([feature_names[i] for i in top_indices])
    ax.invert_yaxis()
    ax.set_xlabel("Importance")
    ax.set_title(f"Feature Importance (Top {top_n})")
    for i, v in enumerate(importances[top_indices]):
        ax.text(v + 0.001, i, f"{v:.3f}", va="center", fontsize=8)
    fig.savefig(os.path.join(OUTPUT_DIR, "feature_importance.png"),
                dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: feature_importance.png")


def plot_roc_curves(y_test: np.ndarray, class_labels: list, y_proba: np.ndarray):
    """绘制多分类 ROC 曲线 (One-vs-Rest)。"""
    y_test_bin = label_binarize(y_test, classes=class_labels)
    n_classes = len(class_labels)
    if n_classes <= 1:
        return

    fig, ax = plt.subplots(figsize=(10, 8))
    for i, cls in enumerate(class_labels):
        fpr, tpr, _ = roc_curve(y_test_bin[:, i], y_proba[:, i])
        roc_auc = auc(fpr, tpr)
        ax.plot(fpr, tpr, linewidth=2,
                label=f"{LABEL_NAMES[cls]} (AUC={roc_auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5)
    ax.set_xlim([0.0, 1.0]); ax.set_ylim([0.0, 1.05])
    ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curves (One-vs-Rest)")
    ax.legend(loc="lower right", fontsize=8); ax.grid(alpha=0.3)
    fig.savefig(os.path.join(OUTPUT_DIR, "roc_curves.png"),
                dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: roc_curves.png")


def plot_learning_curve(model, X_train: np.ndarray, y_train: np.ndarray):
    """绘制学习曲线（兼容 RF 和 XGBoost）。"""
    # 确保标签为数值型（XGBoost 需要）
    if not np.issubdtype(np.asarray(y_train).dtype, np.number):
        le_curve = LabelEncoder()
        y_for_curve = le_curve.fit_transform(y_train)
    else:
        y_for_curve = y_train

    train_sizes = np.linspace(0.1, 1.0, 10)
    train_sizes_abs, train_scores, test_scores = learning_curve(
        model, X_train, y_for_curve, train_sizes=train_sizes,
        cv=3, scoring="accuracy", n_jobs=RF_N_JOBS, shuffle=True,
        random_state=RF_RANDOM_STATE,
    )

    train_mean = np.mean(train_scores, axis=1)
    train_std = np.std(train_scores, axis=1)
    test_mean = np.mean(test_scores, axis=1)
    test_std = np.std(test_scores, axis=1)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(train_sizes_abs, train_mean - train_std, train_mean + train_std,
                    alpha=0.2, color="blue")
    ax.fill_between(train_sizes_abs, test_mean - test_std, test_mean + test_std,
                    alpha=0.2, color="orange")
    ax.plot(train_sizes_abs, train_mean, "o-", color="blue", label="Training Score")
    ax.plot(train_sizes_abs, test_mean, "o-", color="orange", label="Cross-Validation Score")
    ax.set_xlabel("Training Samples"); ax.set_ylabel("Accuracy")
    ax.set_title("Learning Curve"); ax.legend(loc="best"); ax.grid(alpha=0.3)
    fig.savefig(os.path.join(OUTPUT_DIR, "learning_curve.png"),
                dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: learning_curve.png")


def plot_classification_report_heatmap(
    precision: np.ndarray, recall: np.ndarray, f1: np.ndarray,
):
    """绘制分类报告热力图。"""
    metrics = np.column_stack([precision, recall, f1])
    display_labels = [LABEL_NAMES[l] for l in CLASS_LABELS]

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(metrics, annot=True, fmt=".4f", cmap="YlOrRd",
                xticklabels=["Precision", "Recall", "F1-score"],
                yticklabels=display_labels, ax=ax, vmin=0, vmax=1)
    ax.set_title("Classification Report Heatmap")
    fig.savefig(os.path.join(OUTPUT_DIR, "classification_report_heatmap.png"),
                dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图表已保存: classification_report_heatmap.png")


# ============================================================
# ⑧ 保存模型
# ============================================================
def save_model(package: dict, path: str):
    """使用 joblib 保存模型包。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(package, path)
    print(f"\n[模型保存] 模型包已保存至: {path}")


# ============================================================
# 留一工况泛化诊断
# ============================================================
def cross_speed_diagnostic(X: np.ndarray, y: np.ndarray, speeds: np.ndarray):
    """
    留一工况（Leave-One-Speed-Out）交叉验证：
    每次留出一种转速作为测试集，其余 3 种转速训练，评估跨工况泛化能力。
    """
    print(f"\n[跨工况泛化诊断] 留一工况交叉验证")
    logo = LeaveOneGroupOut()
    accs = []

    for train_idx, test_idx in logo.split(X, y, groups=speeds):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]
        test_spd = np.unique(speeds[test_idx])[0]

        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=RF_N_ESTIMATORS, max_depth=RF_MAX_DEPTH,
                min_samples_leaf=RF_MIN_SAMPLES_LEAF,
                random_state=RF_RANDOM_STATE, n_jobs=RF_N_JOBS,
                class_weight="balanced",
            )),
        ])
        pipe.fit(X_tr, y_tr)
        acc = accuracy_score(y_te, pipe.predict(X_te))
        accs.append(acc)
        print(f"  留出转速={test_spd}Hz → 泛化准确率={acc:.4f}")

    print(f"  留一工况平均泛化准确率: {np.mean(accs):.4f}")
    return np.mean(accs)


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  流水线一：离线模型训练")
    print("  电机智能故障诊断系统")
    print("=" * 60)

    # ---- ① 数据加载 ----
    file_info_list = get_data_files(DATA_DIR)

    # ---- ②③④ 数据处理 + 特征提取 ----
    X, y, speeds = build_dataset(file_info_list, verbose=True)

    # ---- ⑤ 数据划分（分层随机 8:2）----
    X_train, X_test, y_train, y_test = split_stratified(
        X, y, test_size=0.2,
    )

    # ---- ⑥ 模型训练 ----
    pipeline, label_encoder = train_model(X_train, y_train)

    # ---- ⑦ 模型评估 ----
    results = evaluate_model(
        pipeline, X_train, X_test, y_train, y_test, label_encoder,
    )

    # ---- 留一工况泛化诊断 ----
    mean_cross = cross_speed_diagnostic(X, y, speeds)

    # ---- ⑧ 保存模型（默认路径 + 带时间戳的版本副本）----
    save_package = {
        "pipeline": pipeline,
        "label_encoder": label_encoder,
        "feature_columns": ALL_FEATURE_COLUMNS,
        "train_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "test_accuracy": results["test_acc"],
        "model_type": MODEL_TYPE,
    }

    # 默认路径（供流水线二加载）
    save_model(save_package, MODEL_PATH)

    # 带时间戳的版本副本（不会被覆盖，用于版本回溯）
    version_name = f"motor_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
    version_path = os.path.join(MODEL_DIR, version_name)
    save_model(save_package, version_path)

    # ---- 最终总结 ----
    print(f"\n{'='*60}")
    print(f"  流水线一完成!")
    print(f"  测试集准确率（8:2 分层随机）: {results['test_acc']:.4f}")
    print(f"  Kappa 系数:                   {results['kappa']:.4f}")
    print(f"  留一工况平均泛化准确率:        {mean_cross:.4f}")
    print(f"  模型已保存至: {MODEL_PATH}")
    print(f"  版本副本:     {version_path}")
    print(f"  评估图表已保存至: {OUTPUT_DIR}")
    print(f"{'='*60}")

    return save_package, results


if __name__ == "__main__":
    main()
