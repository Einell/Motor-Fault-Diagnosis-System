# 电机智能故障诊断系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Vue-3.4-green.svg" alt="Vue">
  <img src="https://img.shields.io/badge/Scikit--learn-1.9-orange.svg" alt="Scikit-learn">
  <img src="https://img.shields.io/badge/EMQX-5.3.2-brightgreen.svg" alt="EMQX">
  <img src="https://img.shields.io/badge/Accuracy-98.43%25-success.svg" alt="Accuracy">
</p>

基于多模态信号（振动 + 声学）与机器学习的电机智能故障诊断系统。利用 HUSTmotor 公开数据集，构建完整覆盖"数据采集 → 数据传输 → 数据处理 → 数据应用"全链路的工业互联网原型系统。

## 项目概述

- **数据集**：HUSTmotor 多模态电机故障数据集，24 个文件，163,840 采样点/文件
- **传感器**：三轴振动加速度计（X/Y/Z）+ 麦克风（Sound），采样率 25.6 kHz
- **故障类型**：6 类 — 健康(H)、轴承故障(BF)、弯曲转子(BOW)、转子断条(BR)、不对中(MIS)、电压不平衡(UV)
- **转速工况**：4 种 — 5 Hz、10 Hz、20 Hz、30 Hz
- **核心算法**：Random Forest（200 棵树，max_depth=12），70 维无量纲特征 + 动态谐波提取
- **最终准确率**：测试集 98.43%，Kappa 0.9811

## 系统架构

```
┌──────────────────┐     MQTT      ┌──────────────────┐    SQLite    ┌──────────────────┐     HTTP      ┌──────────────────┐
│   producer.py    │ ────────────→ │   consumer.py    │ ──────────→ │     app.py       │ ────────────→ │    Dashboard     │
│   数据采集模拟层   │ motor/sensor  │   数据处理推理层   │             │   Flask REST API  │              │   Vue 3 + ECharts │
│                  │    _data      │                  │             │                  │              │   可视化大屏       │
└──────────────────┘              ┌──────────────────┐             └──────────────────┘              └──────────────────┘
                                  │  motor_model.pkl │
                                  │  (离线训练产出)    │
                                  └──────────────────┘
```

**两条流水线**：

| 流水线 | 名称 | 执行频率 | 说明 |
|--------|------|---------|------|
| 流水线一 | 离线模型训练 | 一次性 | 数据加载 → 清洗 → 滑动窗口 → 70 维特征提取 → RF 训练 → 评估 → 保存模型 |
| 流水线二 | 在线实时推理 | 持续运行 | MQTT 订阅 → 特征提取 → 模型推理 → SQLite 存储 → Flask API → 大屏展示 |

## 项目结构

```
motor_health_project/
├── data/                          # 原始数据集 (24 个 txt 文件)
├── src/
│   ├── config.py                  # 全局配置参数
│   ├── feature_utils.py           # 特征提取函数 (70 维，流水线共用)
│   ├── train_model.py             # 流水线一：离线模型训练
│   ├── producer.py                # 流水线二：MQTT 数据模拟发送
│   ├── consumer.py                # 流水线二：MQTT 接收 + 推理 + 存储
│   └── app.py                     # 流水线二：Flask REST API (8 个端点)
├── dashboard/                     # 可视化大屏 (Vue 3 + Vite + ECharts 5)
│   └── src/
│       ├── App.vue                # 主布局 + 故障告警
│       ├── api/index.js           # API 调用封装
│       └── components/
│           ├── StatusGauge.vue    # 健康状态仪表盘
│           ├── WaveformChart.vue  # 实时波形图
│           ├── SpectrumChart.vue  # 四通道频谱 + 谐波标注
│           ├── RmsTrend.vue       # RMS 振动趋势
│           ├── FaultPie.vue       # 故障统计饼图
│           └── HistoryPlayback.vue # 历史回放
├── notebooks/                     # Jupyter Notebook 实验记录
├── models/                        # 训练好的模型文件
├── database/                      # SQLite 数据库 (运行时生成)
├── logs/                          # Consumer 运行日志 (运行时生成)
├── outputs/                       # 模型评估图表
├── requirements.txt               # Python 依赖
├── run_all.bat                    # Windows 一键启动脚本
├── 快速开始.md                     # 详细操作指南
├── 项目框架.md                     # 技术设计文档
└── 数据集说明.txt                  # 数据集说明
```

## 快速开始

### 环境要求

- Python 3.8+ | Node.js 18+ | EMQX 5.3+

### 1. 安装依赖

```bash
# Python
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 前端
cd dashboard && npm install && cd ..
```

### 2. 流水线一：训练模型

```bash
python src/train_model.py
```

产出 `models/motor_model.pkl` 和 `outputs/` 下的评估图表。

### 3. 流水线二：启动在线推理

需要 4 个终端（详见 [快速开始.md](快速开始.md)）：

| 终端 | 命令 | 说明 |
|------|------|------|
| 0 | `emqx.cmd console` | EMQX Broker |
| 1 | `python src/app.py` | Flask API |
| 2 | `python src/consumer.py` | 推理 + 存储 |
| 3 | `python src/producer.py --no-loop` | 数据发送 |
| 4 | `cd dashboard && npm run dev` | 可视化大屏 |

浏览器打开 `http://localhost:3000` 查看大屏。

或者直接双击运行 `run_all.bat` 一键启动所有服务。

## 特征工程

| 特征类别 | 维度 | 说明 |
|---------|------|------|
| 无量纲时域 | 24 | 峭度、偏度、波峰因子、波形因子、脉冲因子、裕度因子 × 4 通道 |
| 频谱统计 | 24 | 质心、散布、偏度、峭度、平坦度、滚降点 × 4 通道 |
| 动态谐波 | 12 | 1×fr / 2×fr / 3×fr 归一化幅值 × 4 通道 |
| 跨通道比值 | 9 | RMS 比值 + Peak 比值（捕获振动能量分布） |
| 转速 | 1 | 电机转速频率 |
| **合计** | **70** | 全部为无量纲或归一化特征，对转速变化鲁棒 |

## 大屏功能

- 🔍 **状态仪表盘**：交通灯 + 置信度进度条 + 故障告警
- 📊 **实时波形**：四通道 1024 点振动波形
- 📈 **频谱分析**：四通道切换 + 转频谐波标注线
- 📉 **RMS 趋势**：最近 100 条振动能量趋势 + dataZoom
- 🥧 **故障统计**：环形饼图 + 累计准确率
- ⏮️ **历史回放**：分页查询 + 选中波形预览 + 自动播放

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/latest` | GET | 最新预测结果 |
| `/api/trend?n=100` | GET | RMS 趋势数据 |
| `/api/statistics` | GET | 故障分布统计 |
| `/api/waveform` | GET | 最新波形数据 |
| `/api/spectrum?channel=x` | GET | 四通道频谱 |
| `/api/history/<id>` | GET | 历史记录详情 |
| `/api/records?page=1&limit=50` | GET | 分页查询记录列表 |
| `/api/health` | GET | 健康检查 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 数据处理 | Python, NumPy, Pandas, SciPy |
| 机器学习 | Scikit-learn (Random Forest) |
| 消息中间件 | EMQX (MQTT Broker), paho-mqtt |
| 后端 API | Flask + flask-cors |
| 数据库 | SQLite (WAL mode) |
| 前端框架 | Vue 3, Vite, ECharts 5 |
| 图表输出 | Matplotlib, Seaborn |

## License

本项目仅用于学术研究与教学演示。
