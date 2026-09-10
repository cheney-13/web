#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ci_qc.py — GitHub Actions 用的「真實比對」批次:只靠 GitHub,不需自架伺服器

流程(全在 CI 內跑):
  ① Figma REST 讀 section 各尺寸設計事實   figma_rest.py(FIGMA_TOKEN 由 GitHub Secret 提供)
  ② Playwright 抓網站各寬度 DOM            fetch_dom.py(CI 內 pip install playwright)
  ③ 逐屬性比對 + 責任歸因                  auto_qa / qa_engine
  ④ 輸出真實報告                          reports/latest.json(給網頁讀)+ 每尺寸 report_<width>.html

用法:
  FIGMA_TOKEN=figd_xxx python3 src/ci_qc.py reports.config.json
  (workflow 也可用環境變數覆寫 config:QC_FILEKEY / QC_NODEID / QC_SITEURL / QC_WIDTHS)

config(reports.config.json)範例見 repo 內同名檔。網頁 index.html 讀 outDir 下的 latest.json 顯示真結果。
"""
import os, re, sys, json
from datetime import datetime

import figma_rest, auto_qa, qa
from report_html import render as render_report

J_LABEL = {"CODE": "code", "DESIGN": "design", "NEEDS_HUMAN": "human", "ACCEPTED": "accepted"}
STATUS_MAP = {"green": "good", "yellow": "warn", "red": "bad"}


def web_rows(report):
    """引擎報告的非通過列 → 網頁明細要的欄位。"""
    out = []
    for f in report["frames"]:
        for r in f["rows"]:
            if r["responsibility"] in ("PASS", "ACCEPTED"):
                continue
            key = re.sub(r"^\[data-figma-id='|'\]$", "", r["selector"] or "")
            out.append({"j": J_LABEL.get(r["responsibility"], "human"),
                        "node": r["node"], "sel": r["selector"], "prop": r["prop"],
                        "tok": r["token"] or "(未綁定)", "spec": r["spec"], "act": r["actual"],
                        "d": r["detail"], "msg": r["resp_msg"], "key": key})
    return out


def assemble(sizes, captured, out_dir=None):
    """(可離線測)各尺寸設計事實 × 已抓的 DOM → 逐尺寸結果 list;有 out_dir 則另寫每尺寸 HTML。"""
    results = []
    for s in sizes:
        dom = captured.get(s["width"]) or {"nodes": []}
        report, cov, plan = auto_qa.run(s["doc"], dom)
        t = report["totals"]
        st = qa.status_of(t["score"], t["CODE"])
        if out_dir:
            slug = re.sub(r"[^0-9A-Za-z]+", "_", str(s["frame"])).strip("_").lower() or "size"
            open(os.path.join(out_dir, f"report_{slug}.html"), "w", encoding="utf-8").write(render_report(report))
        empty = (t["checks"] == 0)          # 沒有任何可比對節點(缺對位)→ 不可當成 100%
        results.append({
            "name": s["frame"], "width": s["width"],
            "score": t["score"], "status": ("info" if empty else STATUS_MAP[st]),
            "checks": t["checks"], "empty": empty,
            "counts": {"code": t["CODE"], "design": t["DESIGN"], "human": t["NEEDS_HUMAN"],
                       "pass": t["pass"], "accepted": t.get("ACCEPTED", 0)},
            "rows": web_rows(report),
            "coverage": cov[0] if cov else {},
        })
    return results


def _cfg_get(cfg, key, env):
    v = os.environ.get(env)
    return v if v else cfg.get(key)


def _write_latest(out_dir, section, site, results):
    latest = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "section": section, "site": site, "results": results}
    open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8").write(
        json.dumps(latest, ensure_ascii=False, indent=2))
    print("=" * 60)
    print(f"真實比對完成 · {section} · {len(results)} 項")
    for r in results:
        tag = " ⚠無可比對(缺對位)" if r.get("empty") else ""
        print(f"  {str(r['name'])[:20]:20} {r['score']:3}%{tag}  程式{r['counts']['code']} 設計{r['counts']['design']} 待人工{r['counts']['human']} 通過{r['counts']['pass']}")
    print("輸出 →", os.path.join(out_dir, "latest.json"))
    return latest


def run_spec(cfg, base_dir):
    """specFile 模式:用既有的『設計規格(帶 CSS 選擇器)』對照即時抓的網站 DOM。
    適合設計稿尚未用 key 命名、但網站有穩定 CSS 選擇器的情況——立即產出有比對的真結果。"""
    import fetch_dom, qa_engine
    site = _cfg_get(cfg, "siteUrl", "QC_SITEURL")
    if not site:
        raise SystemExit("specFile 模式需要 siteUrl")
    width = int(os.environ.get("QC_WIDTHS", "").split(",")[0] or cfg.get("width", 1440))
    out_dir = os.path.join(base_dir, cfg.get("outDir", "reports"))
    os.makedirs(out_dir, exist_ok=True)
    spec = json.load(open(os.path.join(base_dir, cfg["specFile"]), encoding="utf-8"))
    nodes = spec.get("nodes", [])
    selmap = {n["selector"]: n["selector"] for n in nodes if n.get("selector")}
    cap = fetch_dom.capture(site, [width], selmap=selmap)
    dom = cap[0][1]
    report = qa_engine.run(spec, dom)
    t = report["totals"]
    st = qa.status_of(t["score"], t["CODE"])
    name = cfg.get("name") or spec.get("figmaFile") or "設計規格對照"
    slug = re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_").lower() or "spec"
    open(os.path.join(out_dir, f"report_{slug}.html"), "w", encoding="utf-8").write(render_report(report))
    results = [{
        "name": name, "width": width,
        "score": t["score"], "status": ("info" if t["checks"] == 0 else STATUS_MAP[st]),
        "checks": t["checks"], "empty": t["checks"] == 0,
        "counts": {"code": t["CODE"], "design": t["DESIGN"], "human": t["NEEDS_HUMAN"],
                   "pass": t["pass"], "accepted": t.get("ACCEPTED", 0)},
        "rows": web_rows(report), "coverage": {},
    }]
    return _write_latest(out_dir, name, site, results)


def run(cfg, base_dir, token):
    if cfg.get("specFile"):
        return run_spec(cfg, base_dir)
    import fetch_dom
    file_key = _cfg_get(cfg, "fileKey", "QC_FILEKEY")
    node_id  = _cfg_get(cfg, "nodeId",  "QC_NODEID")
    site_url = _cfg_get(cfg, "siteUrl", "QC_SITEURL")
    if not (file_key and node_id and site_url):
        raise SystemExit("config 需要 fileKey、nodeId、siteUrl(或用 QC_FILEKEY/QC_NODEID/QC_SITEURL 覆寫)")
    out_dir = os.path.join(base_dir, cfg.get("outDir", "reports"))
    os.makedirs(out_dir, exist_ok=True)

    selectors = cfg.get("selectors")
    if isinstance(selectors, str):
        selectors = json.load(open(os.path.join(base_dir, selectors), encoding="utf-8"))

    varmap = figma_rest.get_variable_names(file_key, token)
    doc = figma_rest.get_node(file_key, node_id, token)
    if doc.get("type") == "SECTION":
        sizes = figma_rest.section_size_docs(doc, varmap)
        section = doc.get("name")
    else:
        m = figma_rest.SIZE_RE.search(doc.get("name", ""))
        width = int(m.group(1)) if m else 1440
        nodes = figma_rest.walk_keyed(doc, varmap, keys_only=True)
        sizes = [{"frame": doc.get("name"), "width": width, "route": None,
                  "doc": {"baseURL": "", "frames": [{"name": doc.get("name"), "nodes": nodes}]}}]
        section = doc.get("name")
    if not sizes:
        raise SystemExit("此節點下找不到名稱含 @寬度 的尺寸 frame")

    env_widths = os.environ.get("QC_WIDTHS")
    if env_widths:
        ws = [int(w) for w in env_widths.split(",") if w.strip()]
        for s, w in zip(sizes, ws):
            s["width"] = w

    widths = [s["width"] for s in sizes]
    captured = {w: data for (w, data) in fetch_dom.capture(site_url, widths, selmap=selectors)}

    results = assemble(sizes, captured, out_dir)
    return _write_latest(out_dir, section, site_url, results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: FIGMA_TOKEN=xxx python3 src/ci_qc.py <reports.config.json>"); sys.exit(1)
    cfg_path = sys.argv[1]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    base_dir = os.path.dirname(os.path.abspath(cfg_path))
    token = os.environ.get("FIGMA_TOKEN")
    if not cfg.get("specFile") and not token:   # specFile 模式免 Figma token
        print("缺 FIGMA_TOKEN 環境變數(GitHub Actions 由 Secret 提供)"); sys.exit(2)
    run(cfg, base_dir, token)
