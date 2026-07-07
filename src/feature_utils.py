"""
特征提取工具函数 (v5 - 无量纲特征版)
供流水线一（train_model.py）和流水线二（consumer.py）共用

设计原则：
  - 时域特征全部采用无量纲指标，对振动幅值的绝对大小不敏感，
    更能体现波形本身的畸变程度，对转速变化具有天然鲁棒性。
  - 频域特征根据当前转速动态计算转频 fr，提取 1×fr / 2×fr / 3×fr
    处的归一化幅值，确保不同转速下提取的都是对应的谐波分量。
  - 采用零填充 FFT (n_fft=8192)，频率分辨率 ~3.1 Hz，可分辨 5-30 Hz 转频。

特征总计（70 维）：
  【时域无量纲】每通道  6 项 × 4 通道 = 24 维
     峭度、偏度、波峰因子、波形因子、脉冲因子、裕度因子
  【频谱统计】  每通道  6 项 × 4 通道 = 24 维
     质心、散布、偏度、峭度、平坦度、滚降点
  【谐波特征】  每通道  3 项 × 4 通道 = 12 维
     1×fr / 2×fr / 3×fr 归一化幅值
  【跨通道比值】                    =  9 维
  【转速】                          =  1 维
"""

import numpy as np
from scipy import stats
from scipy.fft import fft, fftfreq


# ============================================================
# 特征列名定义
# ============================================================
# 无量纲时域特征（对振幅绝对值不敏感，反映波形畸变程度）
TIME_DIMENSIONLESS = [
    "kurtosis",         # 峭度 — 反映冲击成分，轴承故障敏感
    "skewness",         # 偏度 — 反映信号不对称性
    "crest_factor",     # 波峰因子 = peak / rms
    "shape_factor",     # 波形因子 = rms / mean_abs
    "impulse_factor",   # 脉冲因子 = peak / mean_abs
    "clearance_factor", # 裕度因子 = peak / (mean(sqrt(|x|)))^2
]

# 频谱统计特征（反映频谱形状，对转速敏感度低于固定频率幅值）
SPECTRAL_STATS = [
    "spec_centroid",    # 频谱质心
    "spec_spread",      # 频谱散布（带宽）
    "spec_skewness",    # 频谱偏度
    "spec_kurtosis",    # 频谱峭度
    "spec_flatness",    # 频谱平坦度
    "spec_rolloff",     # 频谱滚降点（85%能量）
]

# 谐波特征 — 动态计算：根据转速 fr 提取 1×fr / 2×fr / 3×fr 归一化幅值
HARMONIC_FEATURES = [
    "harm_norm_1x",     # 转频幅值 / 总能量
    "harm_norm_2x",     # 2倍频幅值 / 总能量
    "harm_norm_3x",     # 3倍频幅值 / 总能量
]

# 跨通道比值 — 振动能量在各传感器间的分布模式
CROSS_CHANNEL_RATIOS = [
    "cross_rms_XY", "cross_rms_XZ", "cross_rms_XS",
    "cross_rms_YZ", "cross_rms_YS", "cross_rms_ZS",
    "cross_peak_XY", "cross_peak_XZ", "cross_peak_YZ",
]

ALL_CHANNELS = ["X", "Y", "Z", "Sound"]

# ---- 生成完整特征列名列表 ----
FEATURE_COLUMNS = []
# 时域无量纲：6 × 4 = 24
for ch in ALL_CHANNELS:
    for feat in TIME_DIMENSIONLESS:
        FEATURE_COLUMNS.append(f"{ch}_{feat}")
# 频谱统计：6 × 4 = 24
for ch in ALL_CHANNELS:
    for feat in SPECTRAL_STATS:
        FEATURE_COLUMNS.append(f"{ch}_{feat}")
# 谐波特征：3 × 4 = 12
for ch in ALL_CHANNELS:
    for feat in HARMONIC_FEATURES:
        FEATURE_COLUMNS.append(f"{ch}_{feat}")
# 跨通道比值：9
for feat in CROSS_CHANNEL_RATIOS:
    FEATURE_COLUMNS.append(feat)

# speed 在 train_model.build_dataset() 中拼接到末尾
ALL_FEATURE_COLUMNS = FEATURE_COLUMNS + ["speed"]

# FFT 参数
N_FFT = 8192  # 零填充至 8192 点 → 频率分辨率 = 25600/8192 ≈ 3.125 Hz


# ============================================================
# 时域特征提取（仅无量纲指标）
# ============================================================
def extract_time_domain_features(signal: np.ndarray) -> dict:
    """
    提取 6 项无量纲时域特征。

    这些特征通过比值运算消除了振动幅值量级的影响，对转速变化具有
    天然鲁棒性，能更纯粹地反映故障引起的波形畸变。
    """
    rms_val = float(np.sqrt(np.mean(np.square(signal))))
    peak_val = float(np.max(np.abs(signal)))
    mean_abs = float(np.mean(np.abs(signal)))
    sqrt_abs_mean = float(np.mean(np.sqrt(np.abs(signal))))

    kurtosis_val = float(stats.kurtosis(signal))
    skewness_val = float(stats.skew(signal))

    # 无量纲指标 — 通过比值消除幅值量级
    crest_factor = peak_val / rms_val if rms_val > 1e-12 else 0.0
    shape_factor = rms_val / mean_abs if mean_abs > 1e-12 else 0.0
    impulse_factor = peak_val / mean_abs if mean_abs > 1e-12 else 0.0
    clearance_factor = peak_val / (sqrt_abs_mean ** 2) if sqrt_abs_mean > 1e-12 else 0.0

    return {
        "kurtosis":         kurtosis_val,
        "skewness":         skewness_val,
        "crest_factor":     crest_factor,
        "shape_factor":     shape_factor,
        "impulse_factor":   impulse_factor,
        "clearance_factor": clearance_factor,
    }


# ============================================================
# 频域特征提取（动态转频 + 零填充 FFT）
# ============================================================
def extract_freq_domain_features(
    signal: np.ndarray,
    fs: float,
    base_freq: float,
    n_fft: int = N_FFT,
    rolloff_fraction: float = 0.85,
) -> dict:
    """
    提取频谱统计特征 + 动态谐波幅值特征。

    关键设计：
      - base_freq = 当前文件的转速频率 fr（Hz），由文件名解析得到
      - 谐波提取动态计算目标频率：1×fr、2×fr、3×fr
      - 无论转速如何变化，提取的始终是对应工况下的谐波分量
      - 零填充 FFT 保证低频（5 Hz）也能被准确分辨
      - 幅值除以总能量做归一化，消除不同工况间绝对能量差异
    """
    # 零填充 FFT
    spectrum = np.abs(fft(signal, n=n_fft))[: n_fft // 2]
    freqs = fftfreq(n_fft, 1.0 / fs)[: n_fft // 2]

    total_energy = float(np.sum(spectrum))
    if total_energy < 1e-12:
        total_energy = 1.0

    # ---- 频谱统计特征 ----
    spec_centroid = float(np.sum(freqs * spectrum) / total_energy)

    spec_spread = float(
        np.sqrt(np.sum(((freqs - spec_centroid) ** 2) * spectrum) / total_energy)
    )

    spec_skewness = float(
        np.sum(((freqs - spec_centroid) ** 3) * spectrum)
        / (total_energy * (spec_spread ** 3 + 1e-12))
    )

    spec_kurtosis = float(
        np.sum(((freqs - spec_centroid) ** 4) * spectrum)
        / (total_energy * (spec_spread ** 4 + 1e-12))
    )

    log_spectrum = np.log(spectrum + 1e-12)
    spec_flatness = float(
        np.exp(np.mean(log_spectrum)) / (np.mean(spectrum) + 1e-12)
    )

    cumsum_energy = np.cumsum(spectrum)
    rolloff_idx = np.argmax(cumsum_energy >= rolloff_fraction * total_energy)
    spec_rolloff = float(freqs[rolloff_idx]) if rolloff_idx > 0 else 0.0

    # ---- 动态谐波幅值（根据当前转速 fr 计算目标频率） ----
    harmonics = {}
    search_half_width = 3.5  # ±3.5 Hz 搜索窗口（略大于频率分辨率 ~3.1 Hz）
    for h in [1, 2, 3]:
        target = base_freq * h           # 动态计算：h × fr
        mask = (freqs >= target - search_half_width) & (freqs <= target + search_half_width)
        if np.any(mask):
            amp = float(np.max(spectrum[mask]))
        else:
            idx = np.argmin(np.abs(freqs - target))
            amp = float(spectrum[idx])
        harmonics[f"harm_norm_{h}x"] = amp / total_energy

    return {
        "spec_centroid":  spec_centroid,
        "spec_spread":    spec_spread,
        "spec_skewness":  spec_skewness,
        "spec_kurtosis":  spec_kurtosis,
        "spec_flatness":  spec_flatness,
        "spec_rolloff":   spec_rolloff,
        **harmonics,
    }


# ============================================================
# 综合特征提取（70 维）
# ============================================================
def extract_features_for_window(
    window_data: np.ndarray,
    speed_hz: float,
    fs: float = 25600.0,
) -> dict:
    """
    对单个滑动窗口提取完整特征向量。

    参数:
        window_data: 2D numpy 数组，形状 (window_size, 4)，列序 [X, Y, Z, Sound]
        speed_hz:    电机转速频率 fr (Hz)，用作频域分析的基频
        fs:          采样频率 (Hz)
    """
    features = {}
    base_freq = speed_hz

    # 各通道独立特征
    for i, ch_name in enumerate(ALL_CHANNELS):
        signal = window_data[:, i]
        # 时域无量纲特征
        td = extract_time_domain_features(signal)
        for feat_name, feat_val in td.items():
            features[f"{ch_name}_{feat_name}"] = feat_val
        # 频域特征（频谱统计 + 动态谐波）
        fd = extract_freq_domain_features(signal, fs=fs, base_freq=base_freq)
        for feat_name, feat_val in fd.items():
            features[f"{ch_name}_{feat_name}"] = feat_val

    # ---- 跨通道比值 ----
    rms_vals, peak_vals = {}, {}
    for i, ch_name in enumerate(ALL_CHANNELS):
        signal = window_data[:, i]
        rms_vals[ch_name] = float(np.sqrt(np.mean(np.square(signal))))
        peak_vals[ch_name] = float(np.max(np.abs(signal)))

    _safe_ratio(features, "cross_rms_XY", rms_vals["X"], rms_vals["Y"])
    _safe_ratio(features, "cross_rms_XZ", rms_vals["X"], rms_vals["Z"])
    _safe_ratio(features, "cross_rms_XS", rms_vals["X"], rms_vals["Sound"])
    _safe_ratio(features, "cross_rms_YZ", rms_vals["Y"], rms_vals["Z"])
    _safe_ratio(features, "cross_rms_YS", rms_vals["Y"], rms_vals["Sound"])
    _safe_ratio(features, "cross_rms_ZS", rms_vals["Z"], rms_vals["Sound"])
    _safe_ratio(features, "cross_peak_XY", peak_vals["X"], peak_vals["Y"])
    _safe_ratio(features, "cross_peak_XZ", peak_vals["X"], peak_vals["Z"])
    _safe_ratio(features, "cross_peak_YZ", peak_vals["Y"], peak_vals["Z"])

    return features


def _safe_ratio(features: dict, name: str, num: float, den: float):
    """安全计算比值，避免除零。"""
    features[name] = num / den if abs(den) > 1e-12 else 0.0


# ============================================================
# 批量特征提取
# ============================================================
def extract_features_batch(
    windows: np.ndarray,
    speed_hz: float,
    fs: float = 25600.0,
) -> np.ndarray:
    """
    批量提取特征。

    参数:
        windows:  3D 数组，形状 (n_windows, window_size, 4)
        speed_hz: 转速频率 (Hz)
        fs:       采样频率 (Hz)

    返回:
        2D 数组，形状 (n_windows, n_features)
    """
    all_features = []
    for i in range(windows.shape[0]):
        feats = extract_features_for_window(windows[i], speed_hz=speed_hz, fs=fs)
        feat_vector = [feats[col] for col in FEATURE_COLUMNS]
        all_features.append(feat_vector)
    return np.array(all_features)
