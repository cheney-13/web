# Visual & Spec QC Agent

**Figma 設計稿 vs. 切版成品的自動核對工具。**

不是比像素,而是透過 MCP 同時取得 Figma 的底層 token/結構與網頁的真實
DOM/Computed Style,**逐屬性語意對位**,並自動判斷每個差異是**設計問題**還是**程式問題**,
輸出給前端工程師與設計師的逐項明細,並自動分派責任。

---

## 為什麼這樣做

傳統「截圖比像素」抗噪差、只知道哪裡不同、不知道差多少與誰的責任。
本工具比對的是「同一元素同一屬性的**設計值 vs 實作值**」:

| 來源 | 取得方式 | 拿到的事實 |
|------|---------|-----------|
| Figma(設計意圖) | `get_design_context` / `get_variable_defs` | token 綁定、色/字/間距/圓角的值 |
| 網頁(實作成品) | 注入 `extract_dom.js` 取 `getComputedStyle` | 真實 DOM 的 computed 值 |

顏色用 **ΔE** 容差抗噪、間距帶容差、每個差異自動歸因並分派人員。

---

## 快速開始

無外部依賴,Python 3.8+ 即可(核心引擎純標準庫)。

```bash
# 1) 批次核對(單一指令跑完 → 每組報告 + 總覽 index + CI 門檻)
python3 src/qa.py samples/demo_project.json --fail-under 80

# 2) 執行差異(修 → 驗 → 修:同一設計、兩輪 DOM,只標「動了什麼」)
python3 src/run_diff.py samples/demo_figma_nodes.json \
        samples/demo_dom_facts.json samples/demo_dom_facts_v2.json out/diff.html

# 3) 單頁核對(手動指定設計事實 + DOM 事實)
python3 src/auto_qa.py samples/demo_figma_nodes.json samples/demo_dom_facts.json out/report.html

# 4) 套用基準線 / 接受清單(把已核准的可接受差異靜音,不阻擋分數)
python3 src/auto_qa.py samples/demo_figma_nodes.json samples/demo_dom_facts.json \
        out/report.html --accepted samples/demo_accepted.json

# 5) 多尺寸核對(一個 section 放多 RWD 尺寸 → 逐尺寸報告 + 合併總覽)
python3 src/run_section.py samples/multisize/section.json --fail-under 80
#   加 --live 會用 fetch_dom.py 對每個尺寸即時抓網站 DOM(需 pip install playwright)

# 6) 回歸測試(純標準庫 unittest,無外部依賴)
python3 -m unittest discover -s tests
```

互動原型與規範卡(可直接用瀏覽器開):
- `index.html` — 切版核對工具(貼連結 → 一鍵批次 → 前端/設計師明細報告;資料夾主入口)
- `guide.html` — Figma 交付規範卡(設計師照著整理檔案)

---

## 資料流

```
① 設計事實   Figma MCP get_design_context ──► figma_extract.py ──► figma_nodes.json
                                              (var(--token,值) 自動判定綁定)
② 實作事實   Browser MCP 注入 extract_dom.js  ──► dom_facts.json
             (或 fetch_dom.py 用 Playwright,無 MCP)
③ 對位比對   auto_qa.py:frame 命名 /route @width → URL+寬度;data-figma-id 自動配對
             qa_engine.py:逐屬性比 + 責任歸因(程式/設計/待人工/通過)
④ 產出       report_html.py(前端/設計師明細) · qa.py(總覽) · run_diff.py(執行差異)
```

**責任歸因規則(核心)**

| 情況 | 判定 | 指派 |
|------|------|------|
| 值相符(容差內) | ✅ 通過 | — |
| 設計端**有綁 token**、實作值不符 | 🔴 程式問題 | 前端 |
| 設計端**沒綁 token**(hardcode)、值不符 | 🔵 設計問題 | 設計師(規格待補) |
| DOM 找不到對應元素 / 屬性未擷取 | ⚪ 待人工 | 對位失敗或漏做 |

容差:顏色 ΔE < 2、間距/圓角 ±1px、字級 ±0.5px、字重需完全一致(見 `qa_engine.py` 頂部 `TOL`)。

**基準線 / 接受清單(靜音可接受差異)**

已人工確認、可接受的差異可寫入 `accepted.json`,核對時命中即標記為 **🟢 已接受**,
不再阻擋還原度分數、每輪不再當雜訊,但仍完整列在報告中(附核准理由)。

```jsonc
// accepted.json —— (key, prop) 命中即靜音;prop 用 "*" 豁免整個節點
{ "accepted": [
  { "key": "hero:title", "prop": "color", "reason": "主標色差 ΔE≈3,已與設計確認可接受" },
  { "key": "seo:card",   "prop": "*",     "reason": "此卡片為暫時性 A/B 版,整節點豁免" }
]}
```

用法:各 CLI 加 `--accepted accepted.json`;批次 `qa.py` 可在 `config.json` 設
專案層級 `"accepted": "accepted.json"`,或在單一 `pair` 內覆蓋。

---

## 檔案結構

```
visual-spec-qc/
├── README.md
├── CLAUDE.md              # 給 Claude Code 續作的專案指南
├── LICENSE
├── index.html            # 切版核對工具(團隊入口 · 互動原型)
├── guide.html     # Figma 交付規範卡(設計師照著整理檔案)
├── src/
│   ├── qa.py             # CLI 入口:批次 + 總覽 index + CI 門檻
│   ├── qa_engine.py      # 比對 + 責任歸因 + 分數(純標準庫)
│   ├── report_html.py    # 明細報告(前端 / 設計師;含空間距離)
│   ├── auto_qa.py        # 依交付規範自動對位 + 覆蓋率
│   ├── figma_extract.py  # 從 get_design_context 抽設計事實(含 token 綁定)
│   ├── figma_rest.py     # 用 Figma REST 抽設計事實(後端真實運作用,需 token)
│   ├── figma_section.py  # 一個 section 放多 RWD 尺寸 → 自動列出各尺寸 + 展開批次
│   ├── server.py         # 後端服務:網頁真實比對(Figma REST × 網站 DOM × 引擎)
│   ├── ci_qc.py          # GitHub Actions 真實比對批次 → reports/latest.json(只靠 GitHub)
│   ├── run_section.py    # 多尺寸核對:逐尺寸抓+比對 → 合併總覽(串起整條鏈)
│   ├── run_diff.py       # 執行差異(解決/回歸/未解決)
│   ├── extract_dom.js    # 注入網頁蒐集 [data-figma-id] 的 computed
│   └── fetch_dom.py      # (選用)Playwright 抓 DOM:多寬度 + 選擇器對照,無需 MCP
├── tests/                # 回歸測試(python3 -m unittest discover -s tests)
└── samples/              # 示範資料(含真實 MX 案例、規範示範、基準線示範)
```

---

## 交付規範(讓核對可自動化)

自動對位需要設計檔遵循約定,詳見 `guide.html`:

1. **Frame 命名** `/route @width`(如 `/about @1440`)→ 工具推導測試 URL + 瀏覽器寬度。
2. **單元 key** ↔ 前端 `data-figma-id`(如圖層 `sec:hero` ↔ `data-figma-id="sec:hero"`)。
3. 標準三寬度 `1440 / 768 / 375`;交付與草稿分開;顏色/間距/字級盡量綁 Variable。

---

## 現況與路線圖

**已完成**
- 核心比對引擎 + 責任歸因 + 明細報告(前端 / 設計師)
- 依規範自動對位(零人工選擇器)+ 覆蓋率(漏做 / 多餘)
- 從 `get_design_context` 自動抽設計事實(含 token 綁定)
- 單一 CLI(批次 + 總覽 + CI 門檻)
- 執行差異 A(修→驗→修:解決 / 回歸 / 未解決)
- **B. 接受清單 / 基準線**(把已核准的可接受差異靜音,不阻擋分數、每輪不再當雜訊)
- **多尺寸(一個 section 放多 RWD 尺寸)**:`figma_section.py` 讀 `get_metadata`,挑出名稱含
  `@寬度` 的尺寸 frame(自動略過注記框 / popup);`run_section.py` 逐尺寸抓 + 比對,
  各自對照網站在相同視窗寬度的呈現,產出逐尺寸報告 + 一頁合併總覽 + CI 門檻;
  `fetch_dom.py` 升級為多寬度 + 選擇器對照(未標 data-figma-id 的正式站也能量);
  工具頁斷點新增「多尺寸(全部)」選項。
- **回歸測試套件**(`tests/`,純標準庫 unittest,鎖定 MX 案例 80% 等關鍵行為)
- 視覺:極簡日式亮色主題

**待做**
- C. 趨勢紀錄(同一頁還原度曲線)
- 擴充比對維度(陰影、狀態 hover/disabled)
- 設計稿自身一致性檢查(同 token 跨節點值不一致)

**即時抓取(整合縫)現況**
把 URL 變成 context / dom 檔的兩側:
- **DOM 側 ✅ 已串接**:`run_section.py --live` 會呼叫 `fetch_dom.py`(Playwright)對每個尺寸的
  網站在該 `@寬度` 即時抓 DOM(支援 data-figma-id 或 CSS 選擇器對照)。本專案雲端環境已預裝
  Chromium,本機只需 `pip install playwright`。
- **Figma 側(剩餘邊界)**:各尺寸 frame 的設計事實目前由 `get_design_context`(session 內 Figma MCP,
  由代理人取)或預抽好的 `figmaNodes` 提供;獨立程序要全自動需 Figma REST API + token。
  `figma_section.py` 已能從 `get_metadata` 自動列出各尺寸並產出批次骨架,填入各尺寸來源即可跑。

---

## 真實運作 A:只靠 GitHub(GitHub Actions,免自架伺服器 · 推薦)

沒有後端主機、沒有線上空間,只有 GitHub 也能真跑——用 **GitHub Actions** 當執行環境:
CI 內打 Figma REST + Playwright 抓站 + 跑引擎 → 把真實報告 commit 回 repo,GitHub Pages 提供,
網頁讀 `reports/latest.json` 顯示真結果。

**啟用(一次性):**
1. Figma → Settings → Security → Personal access tokens → 建唯讀 token。
2. GitHub repo → Settings → Secrets and variables → Actions → 新增 secret **`FIGMA_TOKEN`**(貼上 token)。
3. 編輯 `visual-spec-qc/reports.config.json`(Figma fileKey/nodeId、測試站 URL;未標 `data-figma-id`
   的站再給 `selectors` 對照)。

**執行:** GitHub → Actions →「Visual Spec QC」→ Run workflow(或設排程)。約 1–3 分鐘後,
`visual-spec-qc/reports/latest.json` 更新;打開工具頁按「📥 載入最新真實報告」即顯示真結果。

- CI 腳本:`src/ci_qc.py`(figma_rest × fetch_dom × 引擎)· workflow:`.github/workflows/qc.yml`
- token 只存在 GitHub Secret,**不進前端、不進 commit**。測試站需公開可連。

## 真實運作 B:本機 / 私有後端(`server.py`)

若有主機,`server.py`(純標準庫)可即時服務:網頁 fetch 它的 `/api/run` 拿即時結果。

```bash
export FIGMA_TOKEN=figd_xxx      # Figma personal access token(唯讀即可)
pip install playwright           # 抓網站各寬度 DOM(雲端環境已預裝 Chromium)
python3 src/server.py            # → http://127.0.0.1:8787(工具頁與 API 同源)
```

後端做的三件事:

```
① 設計  figma_rest.py  Figma REST 讀 section 各尺寸 frame → 設計事實(色/字/間距/圓角 + token 綁定)
② 實作  fetch_dom.py   Playwright 把網站在各 @寬度 載入 → getComputedStyle
③ 比對  auto_qa/引擎    逐屬性比 + 責任歸因 → 逐尺寸真實報告(對不到元素標「待人工/無法比對」)
```

> **網頁工具目前為示範模式**(結果為固定示範資料,結果頁會明確標示)。
> 未來將以「**可連結查資料的網址**」接上真實比對:屆時 `index.html` 的 `startRun()` 改呼叫
> 已備妥的 `startRealRun(dataUrl)` 即可切換。後端 API 網址欄已先移除,避免誤解。
>
> 現在要跑真實結果,直接用 CLI:
> `python3 src/run_section.py <section.json>`,或
> `python3 src/figma_rest.py <fileKey> <nodeId> <token> --out nodes.json`。

---

## 授權

見 `LICENSE`(預設 MIT,可依團隊需要調整)。
