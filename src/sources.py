"""어댑터 레지스트리 — 모든 소스를 한 곳에서 조립.

새 소스를 추가하면 여기서만 엮으면 된다(run.py는 변경 불필요).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from src.adapters.anjin import AnjinAdapter
from src.adapters.base import Adapter, FetchResult, safe_fetch
from src.adapters.hanyoung import HanyoungAdapter
from src.adapters.kicpa import build_kicpa_adapters
from src.adapters.samil import SamilAdapter
from src.adapters.samjong import SamjongAdapter


def build_adapters(cfg: dict, state) -> list[Adapter]:
    max_pages = cfg["runtime"]["max_pages"]
    deadline_cache = state.deadlines_by_native_id()

    adapters: list[Adapter] = []
    adapters += build_kicpa_adapters(max_pages, deadline_cache)  # 수습CPA + CPA
    adapters.append(SamjongAdapter())   # 삼정 KPMG
    adapters.append(AnjinAdapter())     # 딜로이트 안진
    adapters.append(HanyoungAdapter())  # EY 한영
    adapters.append(SamilAdapter())     # 삼일 PwC
    return adapters


def fetch_all(adapters: list[Adapter], max_workers: int = 8) -> list[FetchResult]:
    """어댑터들을 도메인 간 병렬로 안전 수집(각 safe_fetch). 한 스레드 실패가 전체를 죽이지 않음.

    서로 다른 도메인이라 동시 호출은 예의 위반이 아니다. 도메인 내 동시성(예: KICPA 상세)은
    각 어댑터 내부에서 제한한다.
    """
    if not adapters:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(adapters))) as ex:
        return list(ex.map(safe_fetch, adapters))
