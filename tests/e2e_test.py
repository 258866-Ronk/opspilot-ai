"""
端到端测试脚本：直接调用运行中的 API，验证完整业务闭环。
运行：python tests/e2e_test.py
"""
import json
import time
import httpx

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"


def wait_server():
    for _ in range(30):
        try:
            r = httpx.get(f"{BASE}/health", timeout=2)
            if r.status_code == 200:
                print("[OK] server healthy")
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError("server not reachable")


def main():
    wait_server()
    c = httpx.Client(timeout=60)

    # 1. 根信息
    print("\n=== 1. 根信息 ===")
    print(json.dumps(c.get(BASE).json(), ensure_ascii=False, indent=2))

    # 2. 登录
    print("\n=== 2. 登录 (operator) ===")
    r = c.post(f"{API}/auth/login", json={"username": "operator", "password": "123456"})
    print("status:", r.status_code)
    token = r.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("login OK, role:", r.json()["data"]["role"])

    # 3. 知识库统计
    print("\n=== 3. 知识库统计 ===")
    print(json.dumps(c.get(f"{API}/knowledge/stats", headers=headers).json(), ensure_ascii=False, indent=2))

    # 4. 知识检索
    print("\n=== 4. 知识检索 ===")
    r = c.post(f"{API}/knowledge/search?query=数据库连接池耗尽&top_k=2", headers=headers)
    d = r.json()["data"]
    print("results:", len(d["results"]))
    if d["results"]:
        print("top score:", d["results"][0]["score"])

    # 5. Agent 任务（核心闭环）
    print("\n=== 5. Agent 故障诊断 ===")
    question = "今天下午订单服务出现大量 HTTP 500 错误，帮我分析原因并给出处理建议"
    r = c.post(f"{API}/agent/tasks", json={"question": question, "service_name": "order-service"}, headers=headers)
    print("create status:", r.status_code)
    d = r.json()["data"]
    task_no = d["task_no"]
    print("task:", task_no, "status:", d["status"])

    # 6. 报告
    print("\n=== 6. 完整报告 ===")
    report = c.get(f"{API}/agent/tasks/{task_no}", headers=headers).json()["data"]
    print("status:", report["status"])
    print("root_cause:", report["root_cause"])
    print("suggestions:", report["suggestions"])
    print("steps:", [(s["node_name"], s["status"]) for s in report["steps"]])
    print("tool_calls:", [(t["tool_name"], t["status"]) for t in report["tool_calls"]])
    print("\n--- final_report ---\n", report["final_report"])

    # 7. 任务列表
    print("\n=== 7. 任务列表 ===")
    print("count:", len(c.get(f"{API}/agent/tasks", headers=headers).json()["data"]))

    # 8. 监控数据
    print("\n=== 8. 监控概览 ===")
    print(json.dumps(c.get(f"{API}/incidents/metrics/overview", headers=headers).json(), ensure_ascii=False)[:300])

    print("\nALL E2E TESTS PASSED")


if __name__ == "__main__":
    main()
