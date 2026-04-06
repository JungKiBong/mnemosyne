# conftest.py — SDK 테스트 루트 마커
# mories_sdk/tests/ 를 프로젝트 루트의 tests/ 와 분리하기 위한 설정
import sys
import os

# mories_sdk 패키지가 import 가능하도록 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
