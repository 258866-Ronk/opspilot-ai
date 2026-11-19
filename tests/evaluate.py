"""
Agent 评测脚本
==============
对 test_cases.json 里的每个故障案例调用 Agent，统计：
  - 工具选择准确率（实际调用工具 vs 期望工具的重合度）
  - 结论关键词命中率（根因/建议是否覆盖预期关键词）
  - 平均响应时间

运行：先启动后端，然后 python tests/evaluate.py
输出：tests/eval_report.json
"""
import json, time, sys, os
import httpx

BASE = "http://127.0.0.1:8000/api/v1"
HERE = os.path.dirname(__file__)


def login():
    r = httpx.post(f"{BASE}/auth/login", json={"username": "operator", "password": "123456"}, timeout=30)
    return r.json()["data"]["access_token"]


def main():
    token = login()
    h = {"Authorization": f"Bearer {token}"}
    cases = json.load(open(os.path.join(HERE, "test_cases.json"), encoding="utf-8"))

    tool_hits, keyword_hits, total = 0, 0, 0
    durations = []
    details = []
    c = httpx.Client(timeout=60)

    for case in cases:
        try:
            t0 = time.time()
            r = c.post(f"{BASE}/agent/tasks", headers=h,
                       json={"question": case["question"], "service_name": case.get("service")})
            d = r.json()["data"]
            task_no = d["task_no"]
            report = c.get(f"{BASE}/agent/tasks/{task_no}", headers=h).json()["data"]
            dur = int((time.time() - t0) * 1000)
            durations.append(dur)

            actual_tools = set(t["tool_name"] for t in report["tool_calls"])
            expected = set(case["expected_tools"])
            tools_ok = len(actual_tools & expected) / max(len(expected), 1)
            tool_hits += tools_ok

            text = (report.get("root_cause") or "") + " " + " ".join(report.get("suggestions") or [])
            kw_ok = sum(1 for k in case["expected_keywords"] if k in text) / max(len(case["expected_keywords"]), 1)
            keyword_hits += kw_ok

            details.append({
                "id": case["id"], "status": report["status"],
                "tools_ok": round(tools_ok, 2), "kw_ok": round(kw_ok, 2),
                "actual_tools": list(actual_tools), "duration_ms": dur,
            })
            total += 1
            print(f"[{case['id']}] tools={tools_ok:.0%} kw={kw_ok:.0%} {dur}ms")
        except Exception as e:
            print(f"[{case['id']}] ERROR {e}")

    report = {
        "total_cases": total,
        "tool_selection_accuracy": round(tool_hits / max(total, 1), 3),
        "keyword_hit_rate": round(keyword_hits / max(total, 1), 3),
        "avg_duration_ms": int(sum(durations) / max(len(durations), 1)),
        "details": details,
    }
    out = os.path.join(HERE, "eval_report.json")
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n=== 评测结果 ===")
    print(f"工具选择准确率: {report['tool_selection_accuracy']:.1%}")
    print(f"结论关键词命中率: {report['keyword_hit_rate']:.1%}")
    print(f"平均响应时间: {report['avg_duration_ms']}ms")
    print(f"报告已保存: {out}")


if __name__ == "__main__":
    main()
