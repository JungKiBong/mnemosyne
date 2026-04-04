"""
DEPRECATED: Use tests.harness.helpers.scenario_helpers instead.
This file remains for backward-compatible dynamic import from workflow JSON files
that reference 'src.app.harness.test_helpers'.
"""

_deep_analysis_counter = 0


def generate_sensor_data(sensor_name: str, value: float) -> float:
    """센서 데이터를 시뮬레이션으로 생성한다."""
    print(f"  [test_helpers] 센서 '{sensor_name}' 값 생성: {value}")
    return value


def analyze_anomaly(reading: float) -> float:
    """이상치 심각도를 0.0~1.0 스케일로 반환한다."""
    try:
        reading_val = float(reading)
    except (TypeError, ValueError):
        reading_val = 50.0
    severity = min(1.0, max(0.0, (reading_val - 80) / 50))
    print(f"  [test_helpers] 이상 분석 완료: reading={reading_val} → severity={severity:.2f}")
    return severity


def deep_analyze(iteration: str = "auto") -> dict:
    """심층 분석을 수행한다 (반복 카운터 포함)."""
    global _deep_analysis_counter
    _deep_analysis_counter += 1
    result = {
        "iteration": _deep_analysis_counter,
        "finding": f"패턴 #{_deep_analysis_counter} 발견: 온도 스파이크 ↔ 촉매 반응 상관관계",
        "confidence": 0.6 + (_deep_analysis_counter * 0.1)
    }
    print(f"  [test_helpers] 심층 분석 #{_deep_analysis_counter}: {result['finding']}")
    return result
