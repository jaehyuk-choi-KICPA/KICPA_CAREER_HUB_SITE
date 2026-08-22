"""아카이브 병합 — 멱등성·월 버킷·하한·보강 규칙.

아카이브는 매 수집(30분)마다 호출되므로 **멱등**이 사양이다. 같은 입력을 다시 넣어도
샤드가 커지거나 파일이 다시 쓰이면 안 된다(git 리포가 부푼다).
"""
from __future__ import annotations

import json

import pytest

from src import archive


@pytest.fixture(autouse=True)
def tmp_archive(tmp_path, monkeypatch):
    """샤드 경로를 임시 디렉터리로 돌려 실제 docs/data/archive를 건드리지 않는다."""
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path / "archive")
    return tmp_path / "archive"


def item(url, title="제목", published="2026-06-15", **kw):
    base = {"url": url, "title": title, "published": published,
            "published_at": published + "T09:00:00", "source_label": "연합뉴스",
            "category": "감사", "summary": "", "source": "gnews_감사"}
    base.update(kw)
    return base


class TestNormUrl:
    def test_strips_google_news_query(self):
        assert archive.norm_url("https://news.google.com/rss/articles/ABC?oc=5") == \
            "https://news.google.com/rss/articles/ABC"

    def test_keeps_other_host_query(self):
        u = "https://example.com/a?id=3"
        assert archive.norm_url(u) == u


class TestMonthKey:
    def test_prefers_published(self):
        assert archive.month_key({"published": "2026-06-15"}, "2026-08-22") == "2026-06"

    def test_falls_back_to_first_archived(self):
        # 인사이트는 published가 전부 빈 문자열이라 이 폴백이 유일한 근거다
        got = archive.month_key({"published": "", "first_archived": "2026-07-02"}, "2026-08-22")
        assert got == "2026-07"

    def test_falls_back_to_today(self):
        assert archive.month_key({}, "2026-08-22") == "2026-08"


class TestMergeItems:
    def test_creates_shard_and_counts(self, tmp_archive):
        added = archive.merge_items("news", [item("u1"), item("u2")], today="2026-08-22")
        assert added == {"2026-06": 2}
        assert (tmp_archive / "news" / "2026-06.json").exists()

    def test_is_idempotent(self, tmp_archive):
        items = [item("u1"), item("u2")]
        archive.merge_items("news", items, today="2026-08-22")
        path = tmp_archive / "news" / "2026-06.json"
        before = path.read_text(encoding="utf-8")
        added = archive.merge_items("news", items, today="2026-08-22")
        assert added == {"2026-06": 0}
        assert path.read_text(encoding="utf-8") == before   # 재기록조차 하지 않는다

    def test_google_url_variants_are_one_record(self, tmp_archive):
        u = "https://news.google.com/rss/articles/ABC"
        archive.merge_items("news", [item(u + "?oc=5")], today="2026-08-22")
        archive.merge_items("news", [item(u)], today="2026-08-22")
        items = json.loads((tmp_archive / "news" / "2026-06.json").read_text(encoding="utf-8"))["items"]
        assert len(items) == 1

    def test_splits_by_month(self, tmp_archive):
        added = archive.merge_items(
            "news", [item("u1", published="2026-05-02"), item("u2", published="2026-07-30")],
            today="2026-08-22")
        assert added == {"2026-05": 1, "2026-07": 1}

    def test_since_floor_drops_older(self, tmp_archive):
        added = archive.merge_items(
            "news", [item("old", published="2026-04-10"), item("new", published="2026-05-10")],
            since="2026-05-01", today="2026-08-22")
        assert added == {"2026-05": 1}
        assert not (tmp_archive / "news" / "2026-04.json").exists()

    def test_first_values_are_sticky(self, tmp_archive):
        archive.merge_items("news", [item("u1", title="원래 제목", category="감사")],
                            today="2026-08-22")
        archive.merge_items("news", [item("u1", title="바뀐 제목", category="세무")],
                            today="2026-08-23")
        rec = json.loads((tmp_archive / "news" / "2026-06.json").read_text(encoding="utf-8"))["items"][0]
        assert rec["title"] == "원래 제목"      # 그때 화면에 떴던 모습 보존
        assert rec["category"] == "감사"
        assert rec["first_archived"] == "2026-08-22"

    def test_dupes_are_flattened_into_records(self, tmp_archive):
        """군집은 아카이브에 중첩 저장하지 않고 개별 레코드로 편다.

        중첩하면 대표의 dupes 배열이 스냅샷마다 합쳐지며 무한 누적된다(실측 11MB → 평면화 후 3MB).
        """
        archive.merge_items("news", [item("u1", dupes=[{"url": "d1", "title": "다른 매체"},
                                                       {"url": "d2", "title": "또 다른 매체"}])],
                            today="2026-08-22")
        items = json.loads((tmp_archive / "news" / "2026-06.json").read_text(encoding="utf-8"))["items"]
        assert {i["url"] for i in items} == {"u1", "d1", "d2"}
        assert all("dupes" not in i for i in items)
        # 멤버는 category·published를 대표에게서 상속받는다
        member = next(i for i in items if i["url"] == "d1")
        assert member["category"] == "감사" and member["published"] == "2026-06-15"

    def test_drops_noise_fields(self, tmp_archive):
        archive.merge_items("news", [item("u1")], today="2026-08-22")
        rec = json.loads((tmp_archive / "news" / "2026-06.json").read_text(encoding="utf-8"))["items"][0]
        assert "summary" not in rec and "source" not in rec

    def test_one_item_per_line(self, tmp_archive):
        """git 델타 최소화 규약 — 아이템 1건이 1줄이어야 append가 순수 추가가 된다."""
        archive.merge_items("news", [item("u1"), item("u2"), item("u3")], today="2026-08-22")
        text = (tmp_archive / "news" / "2026-06.json").read_text(encoding="utf-8")
        assert len(text.splitlines()) == 3 + 2      # 헤더 1 + 아이템 3 + 닫는 줄 1


class TestRebuildIndex:
    def test_indexes_all_streams(self, tmp_archive):
        archive.merge_items("news", [item("u1", published="2026-06-01")], today="2026-08-22")
        archive.merge_items("industry", [item("i1", published="2026-07-01")], today="2026-08-22")
        idx = archive.rebuild_index(since="2026-05-01")
        assert idx["since"] == "2026-05-01"
        assert idx["streams"]["news"]["total"] == 1
        assert idx["streams"]["industry"]["months"][0]["m"] == "2026-07"
        assert (tmp_archive / "index.json").exists()

    def test_empty_streams_are_omitted(self, tmp_archive):
        archive.merge_items("news", [item("u1")], today="2026-08-22")
        idx = archive.rebuild_index()
        assert "insights" not in idx["streams"]
