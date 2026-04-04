"""
scenario_helpers.py — 3개 도메인 시나리오 워크플로우 테스트용 헬퍼 함수

마케팅(고객 이탈 예측), 콘텐츠 제작, DevOps CI/CD 시나리오를
외부 의존성 없이 시뮬레이션으로 검증하기 위한 순수 Python 함수 모음.
"""
import random
import logging

logger = logging.getLogger("scenario_helpers")

# ─────────────────────────────────────────────
# 시나리오 1: 마케팅 — 고객 이탈 예측
# ─────────────────────────────────────────────
_crm_data_cache = {}


def collect_crm_data(source: str = "default_crm") -> dict:
    """CRM에서 고객 데이터를 수집한다 (시뮬레이션)."""
    data = {
        "total_customers": 1200,
        "active_last_30d": 850,
        "inactive_30_60d": 230,
        "inactive_60d_plus": 120,
        "avg_purchase_frequency": 2.3,
        "source": source
    }
    _crm_data_cache["latest"] = data
    logger.info(f"[CRM] 수집 완료: 총 {data['total_customers']}명, 비활성 {data['inactive_60d_plus']}명")
    return data


def predict_churn(customer_count: int = 120) -> dict:
    """ML 모델로 이탈 위험 고객을 분류한다 (시뮬레이션)."""
    high_risk = int(customer_count * 0.25)
    medium_risk = int(customer_count * 0.35)
    low_risk = customer_count - high_risk - medium_risk
    
    # 최고 위험 고객의 이탈 확률
    max_churn_prob = round(random.uniform(0.75, 0.95), 2)
    
    result = {
        "high_risk_count": high_risk,
        "medium_risk_count": medium_risk,
        "low_risk_count": low_risk,
        "max_churn_probability": max_churn_prob,
        "model_accuracy": 0.87
    }
    logger.info(f"[ML] 이탈 예측 완료: 고위험 {high_risk}명, 최대 확률 {max_churn_prob}")
    return result


def send_retention_campaign(high_risk_count: int = 30, action_type: str = "auto") -> dict:
    """위험 등급에 따라 리텐션 캠페인을 발송한다."""
    result = {
        "emails_sent": high_risk_count,
        "coupons_issued": int(high_risk_count * 0.6),
        "campaign_id": f"RET-{random.randint(1000,9999)}",
        "action_type": action_type
    }
    logger.info(f"[Campaign] 발송 완료: 이메일 {result['emails_sent']}건, 쿠폰 {result['coupons_issued']}건")
    return result


def connect_vip_consultant(customer_id: str = "VIP-001") -> dict:
    """VIP 전담 상담을 연결한다."""
    result = {"customer_id": customer_id, "consultant": "김매니저", "status": "connected"}
    logger.info(f"[VIP] 전담 상담 연결: {customer_id} → {result['consultant']}")
    return result


def monitor_revisit_rate(campaign_id: str = "RET-0000") -> dict:
    """7일 후 재방문율을 모니터링한다."""
    rate = round(random.uniform(0.15, 0.45), 2)
    result = {"campaign_id": campaign_id, "revisit_rate": rate, "days_elapsed": 7}
    logger.info(f"[Monitor] 재방문율: {rate*100:.0f}% (캠페인: {campaign_id})")
    return result


# ─────────────────────────────────────────────
# 시나리오 2: 콘텐츠 제작
# ─────────────────────────────────────────────
_draft_counter = 0


def collect_trend_keywords(category: str = "tech") -> dict:
    """트렌드 키워드를 수집한다."""
    keywords = {
        "tech": ["AI Agent 오케스트레이션", "MCP 프로토콜", "자율 연구소"],
        "marketing": ["그로스 해킹", "리텐션 전략", "LTV 최적화"],
        "health": ["디지털 치료제", "웨어러블 바이오센서", "AI 진단"]
    }
    selected = keywords.get(category, keywords["tech"])
    logger.info(f"[Trend] 키워드 수집: {selected}")
    return {"keywords": selected, "category": category, "count": len(selected)}


def generate_blog_draft(keywords: list = None, topic: str = "auto") -> dict:
    """Dify LLM으로 블로그 초안을 생성한다 (시뮬레이션)."""
    global _draft_counter
    _draft_counter += 1
    
    quality = 55 + (_draft_counter * 8) + random.randint(-5, 10)
    quality = min(quality, 95)
    
    result = {
        "draft_version": _draft_counter,
        "title": f"AI 오케스트레이션의 미래 (v{_draft_counter})",
        "word_count": random.randint(1200, 2500),
        "quality_score": quality,
        "topic": topic
    }
    logger.info(f"[Draft] v{_draft_counter} 생성: 품질 {quality}점, {result['word_count']}자")
    return result


def evaluate_quality(quality_score: float = 0) -> dict:
    """품질 점수를 평가한다."""
    try:
        score = float(quality_score)
    except (TypeError, ValueError):
        score = 50.0
    passed = score >= 70
    result = {"score": score, "passed": passed, "threshold": 70}
    logger.info(f"[QA] 품질 평가: {score}점 → {'통과 ✅' if passed else '미달 ❌'}")
    return result


def apply_seo_optimization(title: str = "Untitled") -> dict:
    """SEO 최적화를 적용한다."""
    result = {
        "original_title": title,
        "seo_title": f"{title} | 2026 최신 가이드",
        "meta_description": f"{title}에 대한 완벽 분석. 실무 적용 사례와 미래 전망까지.",
        "slug": title.lower().replace(" ", "-")[:50]
    }
    logger.info(f"[SEO] 최적화 적용: {result['seo_title']}")
    return result


def publish_to_cms(seo_title: str = "Untitled") -> dict:
    """CMS에 자동 발행한다."""
    post_id = f"POST-{random.randint(10000,99999)}"
    result = {"post_id": post_id, "status": "published", "url": f"/blog/{post_id}"}
    logger.info(f"[CMS] 발행 완료: {post_id} — {seo_title}")
    return result


# ─────────────────────────────────────────────
# 시나리오 3: DevOps CI/CD
# ─────────────────────────────────────────────
_build_attempt = 0


def receive_pr_event(repo: str = "mirofish/supermemory") -> dict:
    """GitHub PR merge 이벤트를 수신한다."""
    result = {
        "repo": repo,
        "pr_number": random.randint(100, 999),
        "branch": "main",
        "author": "dev-agent",
        "commit_sha": f"abc{random.randint(1000,9999)}"
    }
    logger.info(f"[GitHub] PR #{result['pr_number']} merge 이벤트 수신 ({repo})")
    return result


def run_build(commit_sha: str = "unknown") -> dict:
    """빌드를 실행한다."""
    global _build_attempt
    _build_attempt += 1
    
    # 첫 시도는 50% 확률로 실패, 이후 시도는 성공
    success = _build_attempt > 1 or random.random() > 0.5
    
    result = {
        "attempt": _build_attempt,
        "success": success,
        "commit_sha": commit_sha,
        "duration_seconds": random.randint(30, 120),
        "error_log": None if success else "TypeError: Cannot read properties of undefined (reading 'map')"
    }
    status = "성공 ✅" if success else "실패 ❌"
    logger.info(f"[Build] 시도 #{_build_attempt}: {status} ({result['duration_seconds']}s)")
    return result


def run_tests(build_success: bool = True) -> dict:
    """테스트를 실행한다."""
    if not build_success:
        return {"passed": 0, "failed": 0, "skipped": 0, "success": False, "reason": "빌드 실패로 테스트 스킵"}
    
    passed = random.randint(80, 120)
    failed = random.randint(0, 3)
    success = failed == 0
    
    result = {
        "passed": passed,
        "failed": failed,
        "skipped": 2,
        "success": success,
        "coverage": round(random.uniform(78, 95), 1)
    }
    logger.info(f"[Test] 통과 {passed}, 실패 {failed}, 커버리지 {result['coverage']}%")
    return result


def analyze_error_with_llm(error_log: str = "unknown error") -> dict:
    """Dify LLM으로 에러를 분석한다 (시뮬레이션)."""
    result = {
        "root_cause": "null-safety 미처리로 인한 TypeError",
        "suggested_fix": "optional chaining(?.) 적용 필요",
        "confidence": 0.85,
        "patch_generated": True
    }
    logger.info(f"[LLM] 에러 분석: {result['root_cause']} → {result['suggested_fix']}")
    return result


def deploy_to_staging(commit_sha: str = "unknown") -> dict:
    """스테이징 환경에 배포한다."""
    result = {"environment": "staging", "commit_sha": commit_sha, "status": "deployed", "url": "https://staging.example.com"}
    logger.info(f"[Deploy] 스테이징 배포 완료: {commit_sha}")
    return result


def send_slack_alert(message: str = "알림", channel: str = "#devops") -> dict:
    """슬랙 알림을 발송한다."""
    result = {"channel": channel, "message": message, "sent": True}
    logger.info(f"[Slack] 알림 발송: {channel} — {message[:60]}")
    return result
