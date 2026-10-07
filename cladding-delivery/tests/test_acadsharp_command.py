import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cladding_delivery.cad.acadsharp import ACadSharpUnavailable, command_path, inspect_dwg


def test_json_command_preserves_windows_unicode_and_space_paths(monkeypatch, tmp_path):
    argv = [r"C:\Program Files\dotnet\dotnet.exe", r"C:\模型工具\ACadSharpDump.dll"]
    monkeypatch.setenv("CADFAB_ACADSHARP_DUMP_ARGV", json.dumps(argv))
    source = tmp_path / "雨棚.dwg"
    source.write_bytes(b"fixture bytes")
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"layers":["铝板"]}', stderr="")
    monkeypatch.setattr("cladding_delivery.cad.acadsharp.subprocess.run", run)
    result = inspect_dwg(source)
    assert calls[0][0] == argv + ["inspect", str(source.resolve())]
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "strict"
    assert result["layers"] == ["铝板"]


@pytest.mark.parametrize("value", ['{}', '[]', '["dotnet", null]', 'bad json', '[""]'])
def test_invalid_command_fails_closed(monkeypatch, value):
    monkeypatch.setenv("CADFAB_ACADSHARP_DUMP_ARGV", value)
    with pytest.raises(ACadSharpUnavailable):
        command_path()
