"""3개 도메인 시나리오 통합 실행 스크립트"""
import sys
import json
import logging

sys.path.insert(0, "src/app/harness")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

from harness_runtime import run_workflow_from_file

scenarios = [
    ("🛒 마케팅: 고객 이탈 예측", "src/app/harness/workflows/marketing_churn.json"),
    ("📝 콘텐츠: AI 블로그 제작", "src/app/harness/workflows/content_creation.json"),
    ("🔧 DevOps: CI/CD 자동 복구", "src/app/harness/workflows/cicd_auto_recovery.json"),
]

results = []
for name, path in scenarios:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  {name}")
    print(f"{sep}")
    r = run_workflow_from_file(path)
    results.append({
        "scenario": name,
        "success": r["success"],
        "steps": r["steps_executed"],
        "elapsed_ms": r["elapsed_ms"],
        "error": r.get("error")
    })

sep = "=" * 60
print(f"\n{sep}")
print("  📊 전체 결과 요약")
print(f"{sep}")
for r in results:
    icon = "✅" if r["success"] else "❌"
    print(f"  {icon} {r['scenario']}: {r['steps']}스텝, {r['elapsed_ms']}ms")
    if r["error"]:
        print(f"     에러: {r['error'][:80]}")
print()
