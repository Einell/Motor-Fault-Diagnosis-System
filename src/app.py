"""
流水线二 — 数据服务层（app.py）
===============================
Flask REST API，为可视化大屏提供数据接口。

5 个 API 端点：
  GET /api/latest      → 最新一条预测结果（状态仪表盘）
  GET /api/trend       → 最近 N 条 RMS 趋势（趋势图）
  GET /api/statistics  → 故障占比统计（饼图）
  GET /api/waveform    → 最新窗口波形数据（示波器）
  GET /api/spectrum    → 最新频谱数据（频谱图）

使用方式：
  python src/app.py [--port 5000]
"""

import os
import sys
import json
import sqlite3
import argparse

from flask import Flask, jsonify, request
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import DB_PATH, LABEL_NAMES, CLASS_LABELS

app = Flask(__name__)
CORS(app)  # 允许跨域请求（Streamlit / DataV 需要）


# ============================================================
# 数据库连接
# ============================================================
def get_db():
    """获取只读数据库连接。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 支持列名访问
    return conn


# ============================================================
# API 1: 最新预测结果 → 状态仪表盘
# ============================================================
@app.route("/api/latest", methods=["GET"])
def api_latest():
    """
    返回最新一条预测结果。

    响应:
      {
        "timestamp": 1234567890.123,
        "file_name": "BF_5HZ.txt",
        "true_label": "BF",
        "predicted_label": "BF",
        "confidence": 0.98,
        "speed": 5,
        "correct": true,
        "label_name": "Bearing Fault"
      }
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM realtime_predictions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": "暂无数据"}), 404

    pred_label = row["predicted_label"]
    return jsonify({
        "timestamp": row["timestamp"],
        "file_name": row["file_name"],
        "true_label": row["true_label"],
        "predicted_label": pred_label,
        "confidence": row["confidence"],
        "speed": row["speed"],
        "correct": row["true_label"] == pred_label,
        "label_name": LABEL_NAMES.get(pred_label, pred_label),
    })


# ============================================================
# API 2: RMS 趋势 → 趋势图
# ============================================================
@app.route("/api/trend", methods=["GET"])
def api_trend():
    """
    返回最近 N 条记录的 RMS 趋势数据。

    参数: ?n=100  (默认 100)

    响应:
      {
        "timestamps": [...],
        "x_rms": [...],
        "y_rms": [...],
        "z_rms": [...],
        "sound_rms": [...],
        "labels": [...],
        "correct": [...]
      }
    """
    n = request.args.get("n", 100, type=int)
    n = min(n, 1000)  # 限制最大返回量

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM realtime_predictions ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()

    rows = list(reversed(rows))  # 时间升序

    return jsonify({
        "timestamps": [r["timestamp"] for r in rows],
        "x_rms": [r["x_rms"] for r in rows],
        "y_rms": [r["y_rms"] for r in rows],
        "z_rms": [r["z_rms"] for r in rows],
        "sound_rms": [r["sound_rms"] for r in rows],
        "labels": [r["predicted_label"] for r in rows],
        "correct": [r["true_label"] == r["predicted_label"] for r in rows],
    })


# ============================================================
# API 3: 故障统计 → 饼图
# ============================================================
@app.route("/api/statistics", methods=["GET"])
def api_statistics():
    """
    返回各类故障的累计占比统计。

    响应:
      {
        "total": 1527,
        "distribution": [
          {"label": "BF", "name": "Bearing Fault", "count": 254, "ratio": 0.166},
          ...
        ],
        "accuracy": 0.9843,
        "confusion_summary": [...]
      }
    """
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM realtime_predictions").fetchone()[0]
    if total == 0:
        conn.close()
        return jsonify({"error": "暂无数据"}), 404

    # 预测标签分布
    pred_rows = conn.execute(
        "SELECT predicted_label, COUNT(*) as cnt "
        "FROM realtime_predictions GROUP BY predicted_label"
    ).fetchall()

    # 准确率
    correct_count = conn.execute(
        "SELECT COUNT(*) FROM realtime_predictions "
        "WHERE true_label = predicted_label"
    ).fetchone()[0]

    conn.close()

    distribution = []
    for row in pred_rows:
        label = row["predicted_label"]
        distribution.append({
            "label": label,
            "name": LABEL_NAMES.get(label, label),
            "count": row["cnt"],
            "ratio": round(row["cnt"] / total, 4),
        })

    # 确保所有类别都在（即使计数为0）
    existing = {d["label"] for d in distribution}
    for cls in CLASS_LABELS:
        if cls not in existing:
            distribution.append({
                "label": cls,
                "name": LABEL_NAMES.get(cls, cls),
                "count": 0,
                "ratio": 0.0,
            })

    return jsonify({
        "total": total,
        "distribution": distribution,
        "accuracy": round(correct_count / total, 4),
    })


# ============================================================
# API 4: 波形数据 → 示波器
# ============================================================
@app.route("/api/waveform", methods=["GET"])
def api_waveform():
    """
    返回最新一条记录的波形数据（4通道 X/Y/Z/Sound）。

    响应:
      {
        "timestamp": ...,
        "file_name": "...",
        "speed": 5,
        "x": [...], "y": [...], "z": [...], "sound": [...]
      }
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM realtime_predictions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": "暂无数据"}), 404

    return jsonify({
        "timestamp": row["timestamp"],
        "file_name": row["file_name"],
        "speed": row["speed"],
        "x": json.loads(row["x_waveform"]),
        "y": json.loads(row["y_waveform"]),
        "z": json.loads(row["z_waveform"]),
        "sound": json.loads(row["sound_waveform"]),
    })


# ============================================================
# API 5: 频谱数据 → 频谱图
# ============================================================
@app.route("/api/spectrum", methods=["GET"])
def api_spectrum():
    """
    返回最新一条记录的四通道频谱数据。

    查询参数: ?channel=x|y|z|sound  (默认返回全部四通道)

    响应:
      {
        "timestamp": ...,
        "file_name": "...",
        "speed": 5,
        "x":  {"freqs": [...], "amps": [...]},
        "y":  {"freqs": [...], "amps": [...]},
        "z":  {"freqs": [...], "amps": [...]},
        "sound": {"freqs": [...], "amps": [...]}
      }
    """
    channel = request.args.get("channel", "all", type=str)

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM realtime_predictions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": "暂无数据"}), 404

    # 兼容旧数据库（可能缺少新频谱列）
    def _safe_load_spectrum(row_dict, col_name):
        try:
            val = row_dict[col_name]
            return json.loads(val) if val else {"freqs": [], "amps": []}
        except (KeyError, IndexError):
            return {"freqs": [], "amps": []}

    row_dict = dict(row)
    result = {
        "timestamp": row["timestamp"],
        "file_name": row["file_name"],
        "speed": row["speed"],
        "x": _safe_load_spectrum(row_dict, "spectrum"),       # X 在 spectrum 列
        "y": _safe_load_spectrum(row_dict, "y_spectrum"),
        "z": _safe_load_spectrum(row_dict, "z_spectrum"),
        "sound": _safe_load_spectrum(row_dict, "sound_spectrum"),
    }

    if channel in result:
        return jsonify({channel: result[channel], **{k: v for k, v in result.items() if k == "timestamp" or k == "file_name" or k == "speed"}})

    return jsonify(result)


# ============================================================
# API 6: 历史记录查询 → 回放功能
# ============================================================
@app.route("/api/history/<int:record_id>", methods=["GET"])
def api_history_detail(record_id):
    """
    返回指定 ID 的完整记录（含波形和频谱）。

    响应: 与 /api/latest 结构一致，但包含完整波形和频谱数据
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM realtime_predictions WHERE id = ?", (record_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": f"记录 #{record_id} 不存在"}), 404

    pred_label = row["predicted_label"]
    spectrum = json.loads(row["spectrum"]) if row["spectrum"] else {}

    return jsonify({
        "id": row["id"],
        "timestamp": row["timestamp"],
        "file_name": row["file_name"],
        "true_label": row["true_label"],
        "predicted_label": pred_label,
        "confidence": row["confidence"],
        "speed": row["speed"],
        "correct": row["true_label"] == pred_label,
        "label_name": LABEL_NAMES.get(pred_label, pred_label),
        "x_rms": row["x_rms"],
        "y_rms": row["y_rms"],
        "z_rms": row["z_rms"],
        "sound_rms": row["sound_rms"],
        "x": json.loads(row["x_waveform"]) if row["x_waveform"] else [],
        "y": json.loads(row["y_waveform"]) if row["y_waveform"] else [],
        "z": json.loads(row["z_waveform"]) if row["z_waveform"] else [],
        "sound": json.loads(row["sound_waveform"]) if row["sound_waveform"] else [],
        "freqs": spectrum.get("freqs", []),
        "amps": spectrum.get("amps", []),
    })


@app.route("/api/records", methods=["GET"])
def api_records():
    """
    分页查询历史记录摘要列表（不含波形数据，仅元信息）。

    参数: ?page=1&limit=50&label=BF

    响应:
      {
        "total": 7632,
        "page": 1,
        "limit": 50,
        "records": [
          {"id": 7632, "timestamp": ..., "true_label": "BF",
           "predicted_label": "BF", "confidence": 0.98, "correct": true, ...},
          ...
        ]
      }
    """
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 50, type=int)
    label_filter = request.args.get("label", None, type=str)

    limit = min(limit, 200)
    offset = (page - 1) * limit

    conn = get_db()

    if label_filter:
        total = conn.execute(
            "SELECT COUNT(*) FROM realtime_predictions WHERE predicted_label = ?",
            (label_filter,),
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT id, timestamp, seq, file_name, true_label, predicted_label,
                      confidence, speed, window_index, x_rms, y_rms, z_rms, sound_rms
               FROM realtime_predictions WHERE predicted_label = ?
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (label_filter, limit, offset),
        ).fetchall()
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM realtime_predictions"
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT id, timestamp, seq, file_name, true_label, predicted_label,
                      confidence, speed, window_index, x_rms, y_rms, z_rms, sound_rms
               FROM realtime_predictions
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()

    conn.close()

    records = []
    for r in rows:
        records.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "seq": r["seq"],
            "file_name": r["file_name"],
            "true_label": r["true_label"],
            "predicted_label": r["predicted_label"],
            "confidence": r["confidence"],
            "speed": r["speed"],
            "window_index": r["window_index"],
            "correct": r["true_label"] == r["predicted_label"],
            "label_name": LABEL_NAMES.get(r["predicted_label"], r["predicted_label"]),
            "x_rms": r["x_rms"],
            "y_rms": r["y_rms"],
            "z_rms": r["z_rms"],
            "sound_rms": r["sound_rms"],
        })

    return jsonify({
        "total": total,
        "page": page,
        "limit": limit,
        "records": records,
    })


# ============================================================
# 健康检查
# ============================================================
@app.route("/api/health", methods=["GET"])
def api_health():
    """健康检查 + 数据概览。"""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM realtime_predictions").fetchone()[0]
    conn.close()
    return jsonify({
        "status": "ok",
        "total_records": total,
        "database": DB_PATH,
    })


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="电机故障诊断 — Flask API 服务")
    parser.add_argument("--port", type=int, default=5000, help="监听端口，默认 5000")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    print("=" * 60)
    print("  流水线二 — Flask API 服务")
    print(f"  地址: http://{args.host}:{args.port}")
    print("=" * 60)
    print(f"\n  端点列表:")
    print(f"    GET /api/latest          — 最新预测结果")
    print(f"    GET /api/trend?n=100     — RMS 趋势数据")
    print(f"    GET /api/statistics      — 故障占比统计")
    print(f"    GET /api/waveform        — 最新波形数据")
    print(f"    GET /api/spectrum        — 四通道频谱数据")
    print(f"    GET /api/history/<id>    — 历史记录详情（含波形）")
    print(f"    GET /api/records?page=1  — 历史记录分页列表")
    print(f"    GET /api/health          — 健康检查")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)
