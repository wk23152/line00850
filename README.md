# 00850 五日均線 LINE 推播機器人

每天台灣時間 **晚上 7 點**，透過 GitHub Actions 排程自動：

1. 抓取 FinMind 的 **00850 元大台灣ESG永續ETF** 日收盤資料
2. 計算 **5 日均線（MA5）**
3. 比較「最新交易日收盤價」與「5 日均線」，判斷收盤價在均線之上或之下
4. 用 LINE Messaging API 把結果 **推播到 LINE 群組**

---

## 檔案結構

```
linne報價/
├── main.py                                  # 主程式（抓資料 → 算均線 → 推播）
├── requirements.txt                         # Python 相依套件
├── README.md                                # 本說明
└── .github/
    └── workflows/
        └── daily-00850-ma5.yml              # GitHub Actions 排程（台灣 19:00）
```

---

## 一、部署到 GitHub

1. 在 GitHub 建立一個新 Repository（例如 `linne-00850-notify`）。
2. 把整個資料夾內容上傳（`git push`）到該 Repository。
3. 排程會在台灣時間每天晚上 7 點自動執行；也可以到 **Actions** 頁籤手動 `Run workflow` 測試。

> ⚠️ **私有 Repository 注意**：GitHub 會在私有 repo **連續 60 天沒有 commit 活動**後自動停用排程（scheduled workflows），屆時需要 push 一次或重新啟用。

---

## 二、設定 Secrets（環境變數）

到 GitHub Repository 的 **Settings → Secrets and variables → Actions → New repository secret**，新增以下兩項：

| Secret 名稱 | 必填 | 說明 |
|---|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Messaging API 的 Channel Access Token（長效型） |
| `LINE_GROUP_ID` | ✅ | 要推播的 LINE 群組 ID（例：`C` 開頭的一串英文數字） |
| `FINMIND_TOKEN` | 建議 | FinMind API token（可不填；免費每小時限 300 次，單次推播夠用） |

可在 **Variables**（同頁籤）加選用變數：`STOCK_ID`（預設 `00850`）、`MA_DAYS`（預設 `5`）、`SKIP_NON_TRADING_DAYS`（預設 `1`，非交易日略過推播）。

---

## 三、取得 FinMind Token（建議）

1. 到 [FinMind](https://finmindtrade.com/) 註冊帳號。
2. 登入後到個人頁面（analysis → account）取得 **API token**。
3. 把 token 填入 GitHub 的 `FINMIND_TOKEN` secret。

> 未填 token 也能用，但每小時限 300 次請求；本程式每次只呼叫 1 次，正常不會超限。

---

## 四、取得 LINE 推播所需資訊

> LINE Notify 已於 2025/3/31 終止服務，這裡改用 **LINE Messaging API**。

### 步驟 1：建立 LINE 官方帳號與 Messaging API Channel

1. 到 [LINE Developers Console](https://developers.line.biz/console/) 登入。
2. 建立一個 **Provider**，再於其中建立 **Messaging API** 類型的 Channel。
3. 在 Channel 的 **Messaging API** 頁籤底部「Channel access token」點 **Issue** 產生長效 token，複製起來（這就是 `LINE_CHANNEL_ACCESS_TOKEN`）。

### 步驟 2：把機器人加入 LINE 群組

1. 在 **Messaging API** 頁籤找到「Bot basic ID」（或 QR code），用手機 LINE 加入該機器人為好友。
2. 在 LINE 建立（或使用現有）群組，把該機器人**邀請進群組**。
3. 在 Channel 的 Messaging API 設定裡，把 **「Use webhook」關閉**、**「Auto-reply messages」關閉**（非必要，避免機器人自動回覆干擾）。

### 步驟 3：取得群組 ID

群組 ID 不會直接顯示在介面上，最簡單的取得方式是：

- 在群組裡對機器人**隨便傳一句話**（例如「hi」）。
- 程式收到事件後可讀到 `source.groupId`。可寫一支臨時程式或用 webhook 抓取；若你已開通 webhook，事件 body 中的 `events[0].source.groupId` 即為群組 ID。

更簡單的替代：用 [ngrok](https://ngrok.com/) + 本機 webhook 抓一次事件，或直接用一支小程式訂閱。取得後填進 `LINE_GROUP_ID`。

> 若你手上已有群組 ID（`C...` 開頭），直接填入即可。

---

## 五、判斷邏輯與非交易日處理

- **5 日均線** = 最近 5 個交易日的收盤價平均（含最新交易日）。
- 若 `最新交易日收盤價 > 5 日均線` → 🟢 **站上均線（在均線之上）**
- 若 `最新交易日收盤價 < 5 日均線` → 🔴 **跌破均線（在均線之下）**
- 若相等 → ⚪ 剛好在均線上

### 週六日 / 國定假日

台股週六日與國定假日不交易。程式會判斷「FinMind 最新資料日期」是否等於「今天」：

- 若**不等於**（代表今天沒有新行情）→ 略過推播，不重複發送前一交易日的訊息。
- 若想每天都強制推播，把 Variables 的 `SKIP_NON_TRADING_DAYS` 設為 `0` 即可。

> 小提醒：若某個正常交易日遲遲沒收到訊息，通常是 FinMind 當天資料尚未更新（少見）。可稍後到 Actions 手動 `Run workflow` 補推，或把排程時間往後調。

---

## 六、本地測試（可選）

```bash
pip install -r requirements.txt

# Windows PowerShell
$env:LINE_CHANNEL_ACCESS_TOKEN="你的 token"
$env:LINE_GROUP_ID="你的群組ID"
$env:FINMIND_TOKEN="你的 FinMind token（可省略）"
python main.py
```

---

## 七、常見問題

- **收不到訊息**：確認機器人已加入群組、`LINE_GROUP_ID` 正確、Channel Access Token 有效、Messaging API 方案的免費額度未用完（免費方案每月有 push 訊息上限）。
- **排程沒跑**：GitHub Actions 的 scheduled 執行可能延遲數分鐘到半小時；私有 repo 超過 60 天無 commit 會被停用排程。
- **非交易日（週末/國定假日）**：預設會略過推播（見第五節）；若你改成每天強制推播，則會以「最新交易日」的資料發送。

---

**免責聲明**：本專案僅供資訊參考，不構成任何投資建議。
