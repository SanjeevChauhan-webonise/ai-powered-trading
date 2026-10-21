import io
import json

from fastapi.testclient import TestClient

from app.data.synthetic import SyntheticConfig, generate

CFG = SyntheticConfig(trading_days=2, n_strikes=2)


def test_synthetic_endpoint_and_get(client: TestClient) -> None:
    r = client.post("/datasets/synthetic", json={"trading_days": 2, "n_strikes": 2})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["underlying_rows"] == 750
    assert d["options_rows"] > 0
    assert d["timeframe_minutes"] == 1
    assert d["lot_size"] == 75
    assert len(d["expiries"]) >= 3
    assert d["quality"]["underlying"]["missing_candles"] == 0
    assert client.get(f"/datasets/{d['id']}").json()["id"] == d["id"]
    assert [x["id"] for x in client.get("/datasets").json()] == [d["id"]]


def test_upload_with_mapping_and_attach(client: TestClient) -> None:
    under, opts = generate(CFG)
    src = under.rename(columns={"timestamp": "Time", "close": "Close"})
    r = client.post(
        "/datasets/upload",
        files={"file": ("u.csv", src.to_csv(index=False), "text/csv")},
        data={
            "mapping": json.dumps({"timestamp": "Time", "open": "open", "high": "high", "low": "low", "close": "Close", "volume": "volume"}),
            "kind": "underlying", "underlying": "NIFTY", "lot_size": "75", "resample_to": "5",
        },
    )  # fmt: skip
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["timeframe_minutes"] == 5 and d["underlying_rows"] == 150
    buf = io.BytesIO()
    opts.to_parquet(buf, index=False)
    r2 = client.post(
        "/datasets/upload",
        files={"file": ("o.parquet", buf.getvalue())},
        data={
            "mapping": client_std_options(),
            "kind": "options",
            "underlying": "NIFTY",
            "dataset_id": d["id"],
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["options_rows"] == len(opts)
    assert r2.json()["underlying_rows"] == 150


def client_std_options() -> str:
    from app.schemas.data import ColumnMapping

    return ColumnMapping.standard("options").model_dump_json()


def test_upload_errors(client: TestClient) -> None:
    csv = "a,b\n1,2\n"
    bad_map = client.post(
        "/datasets/upload", files={"file": ("x.csv", csv)},
        data={"mapping": "{not json", "kind": "underlying", "underlying": "X"},
    )  # fmt: skip
    assert bad_map.status_code == 422
    missing_col = client.post(
        "/datasets/upload", files={"file": ("x.csv", csv)},
        data={"mapping": json.dumps({"timestamp": "a", "open": "b", "high": "b", "low": "b", "close": "zzz"}), "kind": "underlying", "underlying": "X"},
    )  # fmt: skip
    assert missing_col.status_code == 400
    assert "zzz" in missing_col.json()["detail"]
    bad_ext = client.post(
        "/datasets/upload", files={"file": ("x.txt", csv)},
        data={"mapping": json.dumps({"timestamp": "a", "open": "b", "high": "b", "low": "b", "close": "b"}), "kind": "underlying", "underlying": "X"},
    )  # fmt: skip
    assert bad_ext.status_code == 400


def test_get_unknown_dataset(client: TestClient) -> None:
    assert client.get("/datasets/nope").status_code == 404
