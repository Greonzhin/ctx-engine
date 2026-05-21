from __future__ import annotations

from ctx_engine.pathmap import map_path


def test_pathmap_handles_windows_turkish_apostrophe():
    result = map_path(r"C:\Users\Sanal-Ofis\Drive'ım\Projeler\Klon")
    assert result["wsl"] == "/mnt/c/Users/Sanal-Ofis/Drive'ım/Projeler/Klon"
    assert "unicode-or-apostrophe-safe" in result["notes"]
