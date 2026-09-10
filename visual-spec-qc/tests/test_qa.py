#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visual & Spec QC — 回歸測試(純標準庫 unittest,無外部依賴)

跑法:
  python3 -m unittest discover -s tests            # 從專案根目錄
  python3 tests/test_qa.py                          # 直接跑

覆蓋:值正規化 / 逐屬性比對 / 責任歸因 / 主流程 / 覆蓋率 /
      figma_extract 的 token 綁定判定 / run_diff 分類 / 接受清單(基準線)/
      MX 真實案例還原度鎖定在 80%。
"""
import os
import sys
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
SAMPLES = os.path.join(ROOT, "samples")
sys.path.insert(0, SRC)

import qa_engine as qe          # noqa: E402
import auto_qa                  # noqa: E402
import figma_extract as fx      # noqa: E402
import figma_section as fs      # noqa: E402
import run_diff                 # noqa: E402
import run_section              # noqa: E402
import report_html              # noqa: E402
import figma_rest as frest      # noqa: E402
import server                   # noqa: E402
import ci_qc                    # noqa: E402


def load(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ #
class TestNormalize(unittest.TestCase):
    def test_parse_color_forms(self):
        self.assertEqual(qe.parse_color("#fff"), (255, 255, 255))
        self.assertEqual(qe.parse_color("#000000"), (0, 0, 0))
        self.assertEqual(qe.parse_color("rgb(33, 37, 41)"), (33, 37, 41))
        self.assertEqual(qe.parse_color("rgba(66,133,244,0.5)"), (66, 133, 244))
        self.assertIsNone(qe.parse_color("not-a-color"))
        self.assertIsNone(qe.parse_color(None))

    def test_delta_e_identical_is_zero(self):
        self.assertAlmostEqual(qe.delta_e((10, 20, 30), (10, 20, 30)), 0.0, places=6)

    def test_delta_e_symmetric(self):
        a, b = (10, 20, 30), (40, 50, 60)
        self.assertAlmostEqual(qe.delta_e(a, b), qe.delta_e(b, a), places=6)

    def test_parse_len(self):
        self.assertEqual(qe.parse_len("16px"), 16.0)
        self.assertEqual(qe.parse_len("16"), 16.0)
        self.assertEqual(qe.parse_len(16), 16.0)
        self.assertIsNone(qe.parse_len("auto"))
        self.assertIsNone(qe.parse_len(None))

    def test_norm_family(self):
        self.assertEqual(qe.norm_family('"Noto Sans TC", sans-serif'), "noto sans tc")
        self.assertEqual(qe.norm_family("Arial"), "arial")


# ------------------------------------------------------------------ #
class TestCompareProp(unittest.TestCase):
    def test_color_within_tolerance_matches(self):
        match, *_ = qe.compare_prop("color", "#212529", "rgb(33, 37, 41)")
        self.assertTrue(match)

    def test_color_out_of_tolerance_fails(self):
        match, *_ = qe.compare_prop("color", "#212529", "rgb(200, 0, 0)")
        self.assertFalse(match)

    def test_length_tolerance(self):
        self.assertTrue(qe.compare_prop("gap", "16px", "16.4px")[0])   # 差 0.4 < 1
        self.assertFalse(qe.compare_prop("gap", "16px", "20px")[0])

    def test_font_size_stricter_tolerance(self):
        self.assertTrue(qe.compare_prop("fontSize", "48px", "48.3px")[0])   # < 0.5
        self.assertFalse(qe.compare_prop("fontSize", "48px", "49px")[0])    # > 0.5

    def test_font_weight_exact(self):
        self.assertTrue(qe.compare_prop("fontWeight", 700, "700")[0])
        self.assertFalse(qe.compare_prop("fontWeight", 700, "400")[0])

    def test_unparseable_returns_none(self):
        match, *_ = qe.compare_prop("color", "#212529", "not-a-color")
        self.assertIsNone(match)


# ------------------------------------------------------------------ #
class TestAttribution(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(qe.attribute(True, {"token": "x"}, True)[0], "PASS")

    def test_token_bound_mismatch_is_code(self):
        self.assertEqual(qe.attribute(False, {"token": "color/brand"}, True)[0], "CODE")

    def test_hardcode_mismatch_is_design(self):
        self.assertEqual(qe.attribute(False, {"token": None}, True)[0], "DESIGN")

    def test_missing_dom_needs_human(self):
        self.assertEqual(qe.attribute(None, {"token": "x"}, False)[0], "NEEDS_HUMAN")


# ------------------------------------------------------------------ #
class TestRunGuardrails(unittest.TestCase):
    def test_uncaptured_prop_not_counted_as_mismatch(self):
        """核心防護:DOM 未擷取的屬性不可判成程式/設計問題(必為 NEEDS_HUMAN)。"""
        figma = {"nodes": [{
            "frame": "F", "name": "n", "selector": "[data-figma-id='k']",
            "props": {"color": {"value": "#212529", "token": "color/ink"}},
        }]}
        dom = {"nodes": [{"selector": "[data-figma-id='k']", "computed": {}}]}
        rep = qe.run(figma, dom)
        row = rep["frames"][0]["rows"][0]
        self.assertEqual(row["responsibility"], "NEEDS_HUMAN")

    def test_missing_element_needs_human(self):
        figma = {"nodes": [{
            "frame": "F", "name": "n", "selector": "[data-figma-id='k']",
            "props": {"color": {"value": "#212529", "token": "color/ink"}},
        }]}
        dom = {"nodes": []}
        rep = qe.run(figma, dom)
        self.assertEqual(rep["frames"][0]["rows"][0]["responsibility"], "NEEDS_HUMAN")

    def test_score_all_pass_is_100(self):
        figma = {"nodes": [{
            "frame": "F", "name": "n", "selector": "[data-figma-id='k']",
            "props": {"color": {"value": "#212529", "token": "t"}},
        }]}
        dom = {"nodes": [{"selector": "[data-figma-id='k']",
                          "computed": {"color": "rgb(33,37,41)"}}]}
        rep = qe.run(figma, dom)
        self.assertEqual(rep["totals"]["score"], 100)


# ------------------------------------------------------------------ #
class TestAcceptedBaseline(unittest.TestCase):
    """Roadmap B:接受清單把可接受差異靜音,不阻擋分數但仍列出。"""

    def _spec_dom(self):
        figma = {"nodes": [{
            "frame": "F", "name": "主標", "selector": "[data-figma-id='hero:title']",
            "props": {"color": {"value": "#c70067", "token": "color/brand"}},
        }]}
        dom = {"nodes": [{"selector": "[data-figma-id='hero:title']",
                          "computed": {"color": "rgb(33, 37, 41)"}}]}  # 明顯不符 → CODE
        return figma, dom

    def test_without_baseline_is_code_and_low_score(self):
        figma, dom = self._spec_dom()
        rep = qe.run(figma, dom)
        self.assertEqual(rep["totals"]["CODE"], 1)
        self.assertEqual(rep["totals"]["score"], 0)

    def test_baseline_mutes_to_accepted(self):
        figma, dom = self._spec_dom()
        accepted = {"accepted": [{"key": "hero:title", "prop": "color",
                                  "reason": "已確認可接受"}]}
        rep = qe.run(figma, dom, accepted)
        t = rep["totals"]
        self.assertEqual(t["CODE"], 0)
        self.assertEqual(t["ACCEPTED"], 1)
        self.assertEqual(t["score"], 100)   # 已接受不阻擋分數
        row = rep["frames"][0]["rows"][0]
        self.assertEqual(row["responsibility"], "ACCEPTED")
        self.assertEqual(row["orig_responsibility"], "CODE")
        self.assertIn("已確認可接受", row["resp_msg"])

    def test_wildcard_prop_mutes_whole_node(self):
        figma, dom = self._spec_dom()
        accepted = {"accepted": [{"key": "hero:title", "prop": "*"}]}
        rep = qe.run(figma, dom, accepted)
        self.assertEqual(rep["totals"]["ACCEPTED"], 1)

    def test_selector_form_also_matches(self):
        figma, dom = self._spec_dom()
        accepted = [{"selector": "[data-figma-id='hero:title']", "prop": "color"}]
        rep = qe.run(figma, dom, accepted)
        self.assertEqual(rep["totals"]["ACCEPTED"], 1)

    def test_non_matching_entry_leaves_code(self):
        figma, dom = self._spec_dom()
        accepted = {"accepted": [{"key": "other", "prop": "color"}]}
        rep = qe.run(figma, dom, accepted)
        self.assertEqual(rep["totals"]["CODE"], 1)
        self.assertEqual(rep["totals"]["ACCEPTED"], 0)

    def test_pass_row_is_never_muted(self):
        figma = {"nodes": [{
            "frame": "F", "name": "n", "selector": "[data-figma-id='k']",
            "props": {"color": {"value": "#212529", "token": "t"}},
        }]}
        dom = {"nodes": [{"selector": "[data-figma-id='k']",
                          "computed": {"color": "rgb(33,37,41)"}}]}
        rep = qe.run(figma, dom, {"accepted": [{"key": "k", "prop": "*"}]})
        self.assertEqual(rep["frames"][0]["rows"][0]["responsibility"], "PASS")
        self.assertEqual(rep["totals"]["ACCEPTED"], 0)


# ------------------------------------------------------------------ #
class TestSpacing(unittest.TestCase):
    """空間距離:間距 gap、內距 padding、外距 margin、寬高皆納入比對。"""

    def test_spacing_props_in_length_set(self):
        for p in ("gap", "paddingTop", "paddingLeft",
                  "marginTop", "marginRight", "marginBottom", "marginLeft",
                  "width", "height"):
            self.assertIn(p, qe.LENGTH_PROPS)
            self.assertIn(p, qe.WEIGHT)

    def test_margin_compared_with_tolerance(self):
        self.assertTrue(qe.compare_prop("marginBottom", "24px", "24.4px")[0])   # 差 0.4 < 1
        self.assertFalse(qe.compare_prop("marginBottom", "24px", "32px")[0])    # 差 8 → 不符

    def test_margin_mismatch_with_token_is_code(self):
        figma = {"nodes": [{
            "frame": "F", "name": "區塊", "selector": "[data-figma-id='sec']",
            "props": {"marginBottom": {"value": 40, "token": "space/lg"}},
        }]}
        dom = {"nodes": [{"selector": "[data-figma-id='sec']",
                          "computed": {"marginBottom": "24px"}}]}
        rep = qe.run(figma, dom)
        self.assertEqual(rep["frames"][0]["rows"][0]["responsibility"], "CODE")

    def test_figma_extract_tailwind_margin(self):
        code = '<div data-name="sec:x" className="mt-[var(--space\\/lg,40px)] mb-[24px]"></div>'
        nodes = fx.parse(code, keys_only=True)
        props = nodes[0]["props"]
        self.assertEqual(props["marginTop"]["value"], 40)
        self.assertEqual(props["marginTop"]["token"], "space/lg")
        self.assertEqual(props["marginBottom"]["value"], 24)
        self.assertIsNone(props["marginBottom"]["token"])


# ------------------------------------------------------------------ #
class TestReportView(unittest.TestCase):
    """報告只給前端 / 設計師看:不再有業務摘要分頁。"""

    def _report(self):
        figma = {"nodes": [{
            "frame": "F", "name": "n", "selector": "[data-figma-id='k']",
            "props": {"color": {"value": "#c70067", "token": "color/brand"}},
        }]}
        dom = {"nodes": [{"selector": "[data-figma-id='k']",
                          "computed": {"color": "rgb(33,37,41)"}}]}
        return report_html.render(qe.run(figma, dom))

    def test_no_business_summary_tab(self):
        html_out = self._report()
        self.assertNotIn("業務摘要", html_out)
        self.assertNotIn("onclick=\"sw(", html_out)

    def test_has_dev_audience_and_spacing_note(self):
        html_out = self._report()
        self.assertIn("前端", html_out)
        self.assertIn("設計師", html_out)
        self.assertIn("空間距離", html_out)   # 報告說明有列出間距/margin 等維度


# ------------------------------------------------------------------ #
class TestFrameNameAndCoverage(unittest.TestCase):
    def test_parse_frame_name(self):
        self.assertEqual(auto_qa.parse_frame_name("/about @1440"), ("/about", 1440))
        self.assertEqual(auto_qa.parse_frame_name("/pricing @375"), ("/pricing", 375))
        route, width = auto_qa.parse_frame_name("/no-width")
        self.assertEqual(route, "/no-width")
        self.assertIsNone(width)

    def test_coverage_matched_and_only(self):
        plan = [{"frame": "F", "url": "u", "width": 1440,
                 "keys": ["a", "b", "c"]}]
        cov = auto_qa.coverage(plan, {"b", "c", "d"})
        row = cov[0]
        self.assertEqual(row["matched"], ["b", "c"])
        self.assertEqual(row["design_only"], ["a"])   # 設計有、實作漏做
        self.assertEqual(row["dom_only"], ["d"])       # 實作有、設計未定義


# ------------------------------------------------------------------ #
class TestFigmaExtract(unittest.TestCase):
    def test_var_binding_detected_as_token(self):
        val, token = fx.unwrap("var(--color\\/brand,#c70067)")
        self.assertEqual(val, "#c70067")
        self.assertEqual(token, "color/brand")

    def test_hardcode_has_no_token(self):
        val, token = fx.unwrap("#c70067")
        self.assertEqual(val, "#c70067")
        self.assertIsNone(token)

    def test_parse_extracts_keyed_node_with_token(self):
        code = '''
        <div data-name="hero:title" className="text-[var(--fs\\/h1,48px)] font-bold">Hi</div>
        '''
        nodes = fx.parse(code, keys_only=True)
        self.assertEqual(len(nodes), 1)
        n = nodes[0]
        self.assertEqual(n["key"], "hero:title")
        self.assertEqual(n["props"]["fontSize"]["value"], 48)
        self.assertEqual(n["props"]["fontSize"]["token"], "fs/h1")
        self.assertEqual(n["props"]["fontWeight"]["value"], 700)


# ------------------------------------------------------------------ #
class TestFigmaSection(unittest.TestCase):
    """一個 section 放多個 RWD 尺寸 → 自動列出各尺寸(略過注記/popup)。"""

    def _load(self):
        with open(os.path.join(SAMPLES, "demo_section_metadata.xml"), encoding="utf-8") as f:
            return f.read()

    def test_route_width(self):
        self.assertEqual(fs.route_width("about @1440"), ("about", 1440))
        self.assertEqual(fs.route_width("about @576"), ("about", 576))
        self.assertEqual(fs.route_width("popup"), ("popup", None))

    def test_section_picks_only_sized_frames(self):
        sec = fs.parse_section(self._load())
        self.assertEqual(sec["section"], "about")
        self.assertEqual(sec["page"], "about")
        widths = [s["width"] for s in sec["sizes"]]
        self.assertEqual(widths, [1440, 576, 375])            # 由大到小,且只有 3 個
        frames = [s["frame"] for s in sec["sizes"]]
        self.assertNotIn("popup", frames)                     # popup 略過
        self.assertTrue(all("@" in f for f in frames))        # 注記框(1440以上/992~576)略過

    def test_to_config_one_pair_per_size(self):
        sec = fs.parse_section(self._load())
        cfg = fs.to_config(sec, base_url="https://site/#/about")
        self.assertEqual(len(cfg["pairs"]), 3)
        self.assertTrue(all(p["url"] == "https://site/#/about" for p in cfg["pairs"]))
        self.assertEqual(cfg["pairs"][0]["frame"], "about @1440")   # 桌機在前

    def test_frames_map_to_engine_widths(self):
        """每個尺寸 frame 名稱能被 auto_qa 的 parse_frame_name 正確解析寬度。"""
        sec = fs.parse_section(self._load())
        for s in sec["sizes"]:
            route, width = auto_qa.parse_frame_name(s["frame"])
            self.assertEqual(width, s["width"])


# ------------------------------------------------------------------ #
class TestRunDiff(unittest.TestCase):
    def test_resolved_and_regressed_detected(self):
        figma = load("demo_figma_nodes.json")
        prev = load("demo_dom_facts.json")
        curr = load("demo_dom_facts_v2.json")
        _, _, cats = run_diff.run(figma, prev, curr)
        resolved = {k[1] for (k, _, _) in cats["RESOLVED"]}
        regressed = {k[1] for (k, _, _) in cats["REGRESSED"]}
        self.assertIn("[data-figma-id='hero:title']", resolved)
        self.assertIn("[data-figma-id='seo:card']", regressed)


# ------------------------------------------------------------------ #
class TestRunSection(unittest.TestCase):
    """多尺寸核對:一個 section 兩尺寸 → 逐尺寸報告 + 合併總覽(離線,不需 Playwright)。"""

    def test_multisize_chain_offline(self):
        import tempfile, shutil
        src_dir = os.path.join(SAMPLES, "multisize")
        cfg = json.load(open(os.path.join(src_dir, "section.json"), encoding="utf-8"))
        tmp = tempfile.mkdtemp()
        try:
            for fn in os.listdir(src_dir):
                sp = os.path.join(src_dir, fn)
                if os.path.isfile(sp):
                    shutil.copy(sp, tmp)
            cfg["outDir"] = "out"
            code = run_section.run(cfg, tmp, live=False, fail_under=80)
            out = os.path.join(tmp, "out")
            self.assertTrue(os.path.isfile(os.path.join(out, "index.html")))
            reports = [f for f in os.listdir(out) if f.startswith("report_")]
            self.assertEqual(len(reports), 2)          # 兩個尺寸各一份
            self.assertEqual(code, 1)                   # 手機 70% < 80 → CI 未達標
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_build_qa_cfg_maps_sizes_to_pairs(self):
        cfg = json.load(open(os.path.join(SAMPLES, "multisize", "section.json"), encoding="utf-8"))
        qa_cfg = run_section.build_qa_cfg(cfg)
        self.assertEqual(len(qa_cfg["pairs"]), 2)
        self.assertEqual(qa_cfg["pairs"][0]["frame"], "about @1440")
        self.assertTrue(all(p["url"] == cfg["baseURL"] for p in qa_cfg["pairs"]))


# ------------------------------------------------------------------ #
class TestFigmaRest(unittest.TestCase):
    """後端真實運作:Figma REST 節點 JSON → 設計事實(用 fixture 測,不需 token)。"""

    def _doc(self):
        return load("figma_rest_section.json")

    def test_color_from_figma_float_rgb(self):
        self.assertEqual(frest._hex({"r": 0.78, "g": 0, "b": 0.404}), "#C70067")

    def test_section_sizes_skip_annotation(self):
        varmap = {"VariableID:1:10": "color/brand", "VariableID:1:20": "fs/h1"}
        sizes = frest.section_size_docs(self._doc(), varmap)
        self.assertEqual([s["width"] for s in sizes], [1440, 375])   # 只有兩個尺寸,注記框略過

    def test_extract_props_and_token_binding(self):
        varmap = {"VariableID:1:10": "color/brand", "VariableID:1:20": "fs/h1"}
        sizes = frest.section_size_docs(self._doc(), varmap)
        big = sizes[0]["doc"]["frames"][0]["nodes"]
        title = next(n for n in big if n["key"] == "hero:title")["props"]
        self.assertEqual(title["color"]["value"], "#C70067")
        self.assertEqual(title["color"]["token"], "color/brand")     # 有綁 token → 之後判程式問題
        self.assertEqual(title["fontSize"]["token"], "fs/h1")
        self.assertIsNone(title["fontWeight"]["token"])              # 未綁 → hardcode
        cta = next(n for n in big if n["key"] == "sec:cta")["props"]
        self.assertEqual(cta["gap"]["value"], 12)                    # 空間距離:gap
        self.assertEqual(cta["paddingLeft"]["value"], 24)           # 空間距離:padding
        self.assertEqual(cta["borderRadius"]["value"], 8)

    def test_rest_facts_feed_engine(self):
        """REST 抽出的設計事實可直接餵引擎,對不上就標非通過。"""
        sizes = frest.section_size_docs(self._doc(), {"VariableID:1:10": "color/brand"})
        doc = sizes[0]["doc"]
        dom = {"nodes": [{"selector": "[data-figma-id='hero:title']",
                          "computed": {"color": "rgb(0,0,0)"}}]}   # 明顯不符
        report, cov, plan = auto_qa.run(doc, dom)
        self.assertEqual(report["totals"]["CODE"], 1)               # 綁 token 不符 → 程式問題


# ------------------------------------------------------------------ #
class TestCIAssemble(unittest.TestCase):
    """GitHub Actions 真實比對:設計事實(REST)× 已抓 DOM → 逐尺寸結果(離線測 assemble)。"""

    def _sizes(self):
        doc = load("figma_rest_section.json")
        return frest.section_size_docs(doc, {"VariableID:1:10": "color/brand", "VariableID:1:20": "fs/h1"})

    def test_assemble_builds_per_size_results(self):
        sizes = self._sizes()          # about @1440 / @375
        captured = {
            1440: {"nodes": [
                {"key": "hero:title", "computed": {"color": "rgb(0,0,0)", "fontSize": "48px",
                                                   "fontWeight": "700", "fontFamily": "Noto Sans TC"}},  # 顏色不符 → CODE
                {"key": "sec:cta", "computed": {"backgroundColor": "rgb(199,0,103)", "borderRadius": "8px",
                                                "gap": "12px", "paddingLeft": "24px", "paddingRight": "24px",
                                                "paddingTop": "16px", "paddingBottom": "16px"}}]},
            375: {"nodes": [
                {"key": "hero:title", "computed": {"color": "rgb(199,0,103)", "fontSize": "32px",
                                                   "fontWeight": "700", "fontFamily": "Noto Sans TC"}}]},  # 全符
        }
        results = ci_qc.assemble(sizes, captured)
        self.assertEqual([r["width"] for r in results], [1440, 375])
        big = next(r for r in results if r["width"] == 1440)
        self.assertGreaterEqual(big["counts"]["code"], 1)          # 桌機主標色不符 → 程式問題
        self.assertIn(big["status"], ("good", "warn", "bad"))
        self.assertTrue(all("j" in row and "prop" in row for row in big["rows"]))
        sml = next(r for r in results if r["width"] == 375)
        self.assertEqual(sml["score"], 100)                        # 手機全符 → 100%

    def test_assemble_missing_dom_marks_human(self):
        sizes = self._sizes()
        results = ci_qc.assemble(sizes, {1440: {"nodes": []}, 375: {"nodes": []}})
        # DOM 抓不到元素 → 標「待人工/無法比對」,不會誤判成程式/設計
        self.assertTrue(all(r["counts"]["code"] == 0 and r["counts"]["design"] == 0 for r in results))


# ------------------------------------------------------------------ #
class TestServer(unittest.TestCase):
    def test_web_rows_maps_and_drops_pass(self):
        figma = {"nodes": [
            {"frame": "F", "name": "主標", "selector": "[data-figma-id='a']",
             "props": {"color": {"value": "#c70067", "token": "t"}}},   # 不符 → CODE
            {"frame": "F", "name": "副標", "selector": "[data-figma-id='b']",
             "props": {"color": {"value": "#c70067", "token": "t"}}},   # 符 → PASS(應被丟掉)
        ]}
        dom = {"nodes": [
            {"selector": "[data-figma-id='a']", "computed": {"color": "rgb(0,0,0)"}},
            {"selector": "[data-figma-id='b']", "computed": {"color": "rgb(199,0,103)"}},
        ]}
        rep = qe.run(figma, dom)
        rows = server._web_rows(rep)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["j"], "code")
        self.assertEqual(rows[0]["key"], "a")

    def test_run_real_requires_token(self):
        old = os.environ.pop("FIGMA_TOKEN", None)
        try:
            payload, code = server.run_real({"fileKey": "x", "nodeId": "1-2", "siteUrl": "http://a"})
            self.assertEqual(code, 400)
            self.assertIn("FIGMA_TOKEN", payload["error"])
        finally:
            if old is not None:
                os.environ["FIGMA_TOKEN"] = old


# ------------------------------------------------------------------ #
class TestIntegrationSamples(unittest.TestCase):
    def test_demo_auto_qa_runs(self):
        figma = load("demo_figma_nodes.json")
        dom = load("demo_dom_facts.json")
        rep, cov, plan = auto_qa.run(figma, dom)
        self.assertIn("score", rep["totals"])
        self.assertIn("iso:quote", cov[0]["design_only"])
        self.assertIn("promo:banner", cov[0]["dom_only"])

    def test_demo_accepted_file_mutes_hero_title(self):
        figma = load("demo_figma_nodes.json")
        dom = load("demo_dom_facts.json")
        accepted = load("demo_accepted.json")
        base, _, _ = auto_qa.run(figma, dom)
        acc, _, _ = auto_qa.run(figma, dom, accepted)
        self.assertGreaterEqual(acc["totals"]["ACCEPTED"], 1)
        self.assertLessEqual(acc["totals"]["CODE"], base["totals"]["CODE"] - 1)
        self.assertGreaterEqual(acc["totals"]["score"], base["totals"]["score"])

    def test_mx_real_case_locked_at_80(self):
        """CLAUDE.md 規定:MX 真實案例應穩定得到 80%。"""
        figma = load("mx_figma_spec.json")
        dom = load("mx_dom_facts.json")
        rep = qe.run(figma, dom)
        self.assertEqual(rep["totals"]["score"], 80)


if __name__ == "__main__":
    unittest.main(verbosity=2)
