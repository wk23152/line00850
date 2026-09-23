#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日抓取 FinMind 00850 收盤價，計算 5 日均線，
比較本日(最新交易日)收盤價與均線的相對位置，並推播到 LINE 群組。

透過 GitHub Actions 排程每天執行（台灣時間 19:00 = UTC 11:00）。

需要的環境變數（在 GitHub 的 Settings -> Secrets and variables 設定）：
  - LINE_CHANNEL_ACCESS_TOKEN  必填：LINE Messaging API 的 Channel Access Token
  - LINE_GROUP_ID              必填：要推播的 LINE 群組 ID
  - FINMIND_TOKEN              選填：FinMind API token（沒 token 每小時限 300 次，單次夠用）
  - STOCK_ID                   選填：預設 00850
  - MA_DAYS                    選填：均線天數，預設 5
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

# Windows 本機執行時 console 可能使用 cp950/Big5 而無法輸出 emoji，
# 統一改用 UTF-8 輸出（GitHub Actions 的 Linux 環境已是 UTF-8，此設定無副作用）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ---- 設定（可被環境變數覆寫） ----
STOCK_ID = os.getenv("STOCK_ID") or "00850"
STOCK_NAME = os.getenv("STOCK_NAME") or "元大台灣ESG永續ETF"
MA_DAYS = int(os.getenv("MA_DAYS") or "5")
# 非交易日（週六日、國定假日）是否略過推播，避免重複發送前一交易日的訊息。
# 設為 0 / false 可關閉，每天都強制推播。
SKIP_NON_TRADING_DAYS = (os.getenv("SKIP_NON_TRADING_DAYS") or "1").lower() in ("1", "true", "yes", "on")

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN") or ""
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID") or ""

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 台灣時區 UTC+8（無日光節約）
TW_TZ = timezone(timedelta(hours=8))


def fetch_daily_prices():
    """抓取 FinMind TaiwanStockPrice 的日收盤資料，回傳依日期排序的 row 清單。"""
    end_date = datetime.now(TW_TZ).date()
    # 往前抓 45 天，足夠涵蓋約 30 個交易日（含國定假日）
    start_date = end_date - timedelta(days=45)

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": STOCK_ID,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }
    headers = {"Accept": "application/json"}
    if FINMIND_TOKEN:
        # token 只放 Authorization header，不放 URL query。
        # 否則 FinMind 出錯時，requests 的錯誤訊息會連 URL（含 token）一起印進 log，
        # 公開 repo 的 Actions log 是公開的，等於外洩。
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"

    resp = requests.get(FINMIND_URL, params=params, headers=headers, timeout=30)
    if resp.status_code != 200:
        # 不印 resp.text / URL，避免任何 token 或敏感內容進入 log
        raise RuntimeError(f"FinMind API 回傳 HTTP {resp.status_code}")
    payload = resp.json()

    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind API 回傳錯誤：status={payload.get('status')}, msg={payload.get('msg')}")

    data = payload.get("data") or []
    # 只保留有合法收盤價的列
    rows = [r for r in data if r.get("close") is not None]
    rows.sort(key=lambda r: r["date"])
    return rows


def compute_ma(rows):
    """計算最新交易日收盤價與 MA 均線。"""
    if not rows:
        raise RuntimeError(f"FinMind 沒有回傳 {STOCK_ID} 的價格資料，請檢查代號或日期範圍。")

    closes = [float(r["close"]) for r in rows]
    latest = rows[-1]
    latest_date = latest["date"]
    latest_close = closes[-1]

    # 均線：取最近 MA_DAYS 個交易日的收盤價平均（含最新交易日）
    window = closes[-MA_DAYS:]
    ma = sum(window) / len(window)
    used_days = len(window)

    return latest_date, latest_close, ma, used_days


def build_message(latest_date, close, ma, used_days):
    """組出要推播的 LINE 訊息。"""
    diff = close - ma
    pct = (diff / ma * 100.0) if ma else 0.0

    if diff > 0:
        status = "🟢 站上均線（收盤價在均線之上）"
        arrow = "▲"
    elif diff < 0:
        status = "🔴 跌破均線（收盤價在均線之下）"
        arrow = "▼"
    else:
        status = "⚪ 剛好落在均線上（收盤價 = 均線）"
        arrow = "＝"

    lines = [
        f"📊 {STOCK_ID} {STOCK_NAME}",
        "──────────────",
        f"📅 資料日期：{latest_date}（最新交易日）",
        f"💹 收盤價：{close:.2f}",
        f"📏 {used_days} 日均線：{ma:.2f}",
        "──────────────",
        status,
        f"{arrow} 價差：{diff:+.2f}（{pct:+.2f}%）",
    ]
    return "\n".join(lines)


def send_line(message):
    """透過 LINE Messaging API push 訊息到群組。"""
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "to": LINE_GROUP_ID,
        "messages": [{"type": "text", "text": message}],
    }
    resp = requests.post(LINE_PUSH_URL, headers=headers, json=body, timeout=30)
    if resp.status_code != 200:
        # 只印 status code，不印 header / URL，確保 token 不進入 log
        raise RuntimeError(f"LINE API 回傳 HTTP {resp.status_code}")
    # 成功時回傳 200（body 通常為 {}）
    print(f"LINE 推播成功（HTTP {resp.status_code}）")


def main():
    try:
        rows = fetch_daily_prices()
        latest_date, close, ma, used_days = compute_ma(rows)

        # 週六日或國定假日：FinMind 最新交易日會停留在上一個交易日；
        # 若「最新交易日」與「今天」不同，代表今天沒有新行情，略過推播，避免重複發送。
        today_str = datetime.now(TW_TZ).strftime("%Y-%m-%d")
        if SKIP_NON_TRADING_DAYS and latest_date != today_str:
            print(f"⏭️ 今天（{today_str}）尚無新收盤資料（最新交易日：{latest_date}），略過推播。")
            return

        message = build_message(latest_date, close, ma, used_days)

        print("=" * 40)
        print(message)
        print("=" * 40)

        if LINE_CHANNEL_ACCESS_TOKEN and LINE_GROUP_ID:
            send_line(message)
        else:
            print(
                "⚠️ 未設定 LINE_CHANNEL_ACCESS_TOKEN / LINE_GROUP_ID，跳過推播。",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        # 讓 GitHub Actions 記錄失敗原因，方便 debug
        print(f"❌ 執行失敗：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
