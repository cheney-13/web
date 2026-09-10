# CLAUDE.md — 專案指南(給 Claude Code 續作)

## 這是什麼
Figma 設計稿 vs. 切版成品的自動核對工具(Visual & Spec QC)。透過 MCP 同時取得
Figma 底層 token 與網頁真實 DOM/Computed Style,**逐屬性比對**並自動歸因「設計問題 / 程式問題」,
產出前端 / 設計師逐項明細報告(不含業務摘要)。完整說明見 `README.md`。

## 執行環境
- **純 Python 3.8+,核心無外部依賴**(標準庫)。沒有 Node。
- `fetch_dom.py` 選用 Playwright(`pip install playwright && playwright install chromium`)。
- 產出的 HTML 用 Google Fonts 載入 Zen Kaku Gothic New(需連網;離線退回系統黑體)。

## 怎麼跑 / 怎麼驗
```bash
python3 src/qa.py samples/demo_project.json --fail-under 80      # 批次 CLI(exit≠0 表未達標)
python3 src/auto_qa.py samples/demo_figma_nodes.json samples/demo_dom_facts.json out/r.html
python3 src/run_diff.py samples/demo_figma_nodes.json \
        samples/demo_dom_facts.json samples/demo_dom_facts_v2.json out/diff.html
```
改動後的回歸檢查:**先跑測試套件**(純標準庫,無外部依賴,秒級):
```bash
python3 -m unittest discover -s tests           # 全綠才算沒改壞
```
測試已鎖定關鍵行為(值正規化 / 比對容差 / 責任歸因 / DOM 未擷取防護 /
接受清單靜音 / figma_extract token 判定 / run_diff 分類 / **MX 案例 = 80%**)。
新增比對維度或改容差時,務必同步補測試。上面三條 CLI 也都應正常產出。

## 模組地圖(改動時看這裡)
- `qa_engine.py` — 比對核心。`TOL`=容差、`WEIGHT`=屬性權重、`compare_prop()`=逐屬性比、
  `attribute()`=責任歸因、`AcceptedIndex`=接受清單索引、`run(figma,dom,accepted=None)`=主流程。
  **改比對邏輯只動這支。**
- `figma_extract.py` — 解析 `get_design_context` 的 React+Tailwind。關鍵:`var(--token,值)`=有綁 token、
  原始值=hardcode;`classify()`=Tailwind class→CSS 屬性;`parse()`=把樣式併入最近的具鍵節點。
- `figma_section.py` — 一個 section 放多 RWD 尺寸時,讀 `get_metadata` XML,`parse_section()` 挑出
  名稱含 `@寬度` 的尺寸 frame(略過注記框/popup),`to_config()` 展開成 qa.py 多尺寸批次骨架。
- `auto_qa.py` — 依規範自動對位:`parse_frame_name()` 解析 `/route @width`;以 `data-figma-id` 為 key 配對;
  `coverage()`=配對成功 / 設計獨有(漏做)/ 實作獨有(多餘)。
- `run_section.py` — 多尺寸核對總管:把 section 各尺寸展成 `qa.build_qa_cfg` 的 pairs,
  `--live` 先用 `fetch_dom.py` 逐寬度即時抓 DOM,再呼叫 `qa.run_config_dict` 出逐尺寸報告 + 合併總覽。
- `figma_rest.py` — 後端真實運作用。純標準庫 urllib 打 Figma REST。`node_facts()`=節點→設計事實
  (色/字/間距/圓角,`boundVariables` 有鍵=有綁 token);`section_size_docs()`=section→各尺寸設計事實。
- `server.py` — 後端服務(stdlib http.server)。`/api/run`=真實比對(figma_rest × fetch_dom.capture × auto_qa)。
- `ci_qc.py` — **只靠 GitHub 的真實執行**(`.github/workflows/qc.yml` 呼叫)。讀 `reports.config.json`
  (fileKey/nodeId/siteUrl/selectors,可用 QC_* env 覆寫)→ figma_rest × fetch_dom.capture × auto_qa
  → 寫 `reports/latest.json` + 每尺寸 HTML,CI commit 回 repo;網頁 `loadLatestReport()` 讀 latest.json。
  `assemble()` 為離線可測核心(fixture `samples/figma_rest_section.json`);FIGMA_TOKEN 由 GitHub Secret 提供。
- `fetch_dom.py` — 即時抓 DOM(Playwright)。多寬度 `--widths`;`--selectors` 給 key→CSS 選擇器
  (未標 data-figma-id 的正式站)。與 `extract_dom.js` 屬性集對齊。
- `report_html.py` / `qa.py`(index,`run_config_dict` 可被重用)/ `run_diff.py` — HTML 輸出,共用視覺系統。
- `extract_dom.js` — 注入網頁蒐集 `[data-figma-id]` 的 computed(Browser MCP 或 fetch_dom.py 用)。

## 資料契約
- **figma_nodes**:`{baseURL, frames:[{name, url?, nodes:[{key, name, props:{prop:{value, token}}}]}]}`
- **dom_facts**:`{url, nodes:[{key, computed:{prop:value}}]}`(key = data-figma-id 值)
- **accepted(基準線)**:`{accepted:[{key|selector, prop, reason?}]}`;`prop="*"` 豁免整個節點。
  命中的非通過項會被靜音為 `ACCEPTED`(不阻擋分數、仍列出),原判定存於 `orig_responsibility`。
- 比對以 `(frame, [data-figma-id='key'], prop)` 為鍵。`token=None` 代表 hardcode。

## 交付規範(自動對位的前提)
- Frame 命名 `/route @width`;圖層 key ↔ 前端 `data-figma-id`;標準寬度 1440/768/375。
- 規範卡原始碼:`guide.html`。

## 網頁工具 index.html 的畫面結構(P1 重構後)
單頁多 screen(`.screen` + JS `nav(id)` 切換);狀態輕量存 localStorage(`vsqc.v2`)。
- `scr-home` 雙階段選單 → `enterCheck(mode)` → `scr-check`(Step 00 連線檢查,`recheckConn`/`proceedFromCheck`)
- 模式 A `scr-lint`(設計稿規範檢核,`runLint`,目前示範骨架)/ 模式 B `scr-setup`→`scr-running`→`scr-result`(單欄卡片 `col1`)
- **路線圖**:P1 結構/UX(✅)· P2 協作(✅:每張差異點 issue 卡的留言 / 標記特例 / 審核狀態
  🔴待處理→🟢已解決 / 🏷️特例;`renderIssues()` + `ISS`(localStorage `vsqc.issues`),issueId=repId::selector::prop)·
  P3 歷史紀錄 + 新舊回歸對比(✅:`vsqc.history` 存主題/填表人/時間/差異點快照;`openHistory`/`renderHistory`
  /`loadRecord`/`openRegress`+`classify` → 🟢已解決 / 🔴新問題 / 🟡未解決 / 🏷️特例略過,整合 P2 狀態)· 截圖備查(待)。
  真實資料(A 用 Figma MCP 圖層 JSON、B 用設計+DOM)未來由「可連結查資料的網址」接入:
  在 `startRun()` 改呼叫已備妥的 `startRealRun(dataUrl)` 即可切換;協作/歷史的 save/load 換成打該 API 即可跨人共用。

## 視覺系統(極簡日式 · 單一亮色)
所有 HTML 輸出共用同一套 token,改樣式要同步四處(`report_html.py`、`qa.py`、`run_diff.py`、根層 `index.html` / `guide.html`):
```
和紙暖白 --bg:#f4f2ec / #faf9f6   墨色 --ink:#1f1d1a   髮絲線 --line:#e7e3da
傳統色  程式=朱紅#b4453a 設計=藍#3f5b7a 通過=苔綠#5e7d5a 警示=山吹#b98a34 待人工#8f887c
字體    Zen Kaku Gothic New(拉丁/數字) + Noto Sans TC(中文) + IBM Plex Mono(數據)
單一亮色主題(不做暗色);品牌 magenta #c70067 只做極少量點綴
```

## 已知地雷 / 設計決策
- **不可把「DOM 未擷取的屬性」當成不符**。`qa_engine.run()` 有防護:`dom_val is None` → 判「待人工/未量測」,
  不可歸成程式/設計問題(曾出過此 bug)。新增屬性比對時務必維持。
- `qa.py` 報告檔名用 `report_{序號}_{slug}`;slug 對全中文名字會退成 `pair`,靠序號保唯一。
- 顏色比對支援 hex 與 rgb()/rgba();`figma_extract` 的 token 名會把 `\/` 還原成 `/`。
- **唯一整合縫**:URL → context/dom 檔的即時抓取要透過 MCP(代理人)或 `fetch_dom.py`;
  獨立 Python 程序無法直接呼叫 session 的 MCP 工具。

## 路線圖
- ✅ B. 接受清單 / 基準線(靜音可接受差異) — 已完成。`accepted.json` 走 `(key|selector, prop)`,
  `AcceptedIndex` 索引;命中即靜音為 `ACCEPTED`(不阻擋分數、仍列出)。四支 CLI 皆吃 `--accepted`,
  `qa.py` 另支援 config 專案層級 / pair 層級。示範:`samples/demo_accepted.json`。
- ⬜ C. 趨勢紀錄(同頁還原度曲線) — 每輪存快照,畫 62%→…→100%。建議 `history/<pair>.jsonl`
  每行一輪 `{ts, score, CODE, DESIGN, NEEDS_HUMAN, ACCEPTED}`,在 index 畫 sparkline。
- ⬜ 擴充維度(陰影 boxShadow / 狀態 hover·disabled / 多斷點)、設計稿自身一致性檢查。
  新增比對維度時:`qa_engine` 的 `COLOR_PROPS`/`LENGTH_PROPS`/`WEIGHT` + `extract_dom.js` 的 `PROPS`
  + `figma_extract.classify` 的對照表,四處要同步,並補 `tests/`。
