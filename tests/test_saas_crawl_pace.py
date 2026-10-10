"""onlinejobs.ph's robots.txt asks for ``Crawl-delay: 5``. The worker keeps it on every request."""

from __future__ import annotations

from applyfirst.saas import db, worker
from test_saas_worker import _Board, _engine_factory, _seed


class _Stopwatch:
    """Fake time. Sleeping moves it forward, so a round costs no real seconds."""

    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds


class _TimedBoard(_Board):
    """Notes the fake time of every request, search page and job page alike."""

    def __init__(self, pages, watch):
        super().__init__(pages)
        self.watch = watch
        self.hits: list[float] = []

    def search_latest(self, keyword):
        self.hits.append(self.watch.now)
        return super().search_latest(keyword)

    def fetch_detail(self, job):
        self.hits.append(self.watch.now)
        return super().fetch_detail(job)


def _round(conn, saas_cfg, master_key, monkeypatch, pages):
    watch = _Stopwatch()
    monkeypatch.setattr(worker.time, "sleep", watch.sleep)
    board = _TimedBoard(pages, watch)
    worker.run_once(conn, board, saas_cfg, master_key, engine_factory=_engine_factory,
                    sender=lambda *a, **k: "m")
    return [b - a for a, b in zip(board.hits, board.hits[1:])]


def test_every_request_waits_five_seconds_after_the_last(saas_cfg, master_key, monkeypatch):
    conn = db.init_db(saas_cfg.db_path)
    user = _seed(conn, master_key, keyword="shopify")
    db.add_keyword(conn, user.id, "virtual assistant")

    gaps = _round(conn, saas_cfg, master_key, monkeypatch,
                  {"shopify": ["1", "2"], "virtual assistant": ["3", "4"]})

    assert len(gaps) == 5, gaps   # 2 searches and 4 new job pages make 6 requests
    assert min(gaps) >= 5.0, gaps
    conn.close()


def test_the_site_check_after_an_empty_round_waits_too(saas_cfg, master_key, monkeypatch):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key, keyword="shopify")

    gaps = _round(conn, saas_cfg, master_key, monkeypatch, {})

    assert len(gaps) == 1, gaps   # the empty search, then the canary search
    assert min(gaps) >= 5.0, gaps
    conn.close()
