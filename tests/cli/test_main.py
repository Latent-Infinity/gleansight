from __future__ import annotations

import papers.cli.__main__ as main_module


def test_main_invokes_app(monkeypatch) -> None:
    called = {"ok": False}

    def fake_app() -> None:
        called["ok"] = True

    monkeypatch.setattr(main_module, "app", fake_app)

    main_module.main()

    assert called["ok"] is True
