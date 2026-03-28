"""Unit tests for CsvAdapter and JsonAdapter."""
import os
import json
import tempfile
import pytest

from app.adapters.structured_adapters import CsvAdapter, JsonAdapter, YamlAdapter
from app.adapters.base import SourceType


class TestCsvAdapter:
    def setup_method(self):
        self.adapter = CsvAdapter()

    def test_can_handle(self):
        assert self.adapter.can_handle("/data/test.csv") is True
        assert self.adapter.can_handle("/data/test.CSV") is True
        assert self.adapter.can_handle("/data/test.json") is False

    def test_ingest_basic(self):
        # Create a temp CSV
        content = "name,age,city\nAlice,30,Seoul\nBob,25,Tokyo\nCharlie,35,Berlin\n"
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w') as f:
            f.write(content)
            path = f.name

        try:
            result = self.adapter.ingest(path)
            assert result.source_type == SourceType.STRUCTURED
            assert result.metadata["format"] == "csv"
            assert result.metadata["row_count"] == 3
            assert "name" in result.metadata["columns"]
            assert "Alice" in result.text
            assert "age is 30" in result.text or "name is Alice" in result.text
            assert len(result.raw_records) == 3
        finally:
            os.unlink(path)

    def test_ingest_with_row_limit(self):
        rows = "id,value\n" + "\n".join(f"{i},{i*10}" for i in range(100))
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w') as f:
            f.write(rows)
            path = f.name

        try:
            result = self.adapter.ingest(path, row_limit=10)
            assert len(result.raw_records) == 10
            assert result.metadata["row_count"] == 100
        finally:
            os.unlink(path)

    def test_numeric_summary(self):
        content = "product,price\nA,100\nB,200\nC,300\n"
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w') as f:
            f.write(content)
            path = f.name

        try:
            result = self.adapter.ingest(path)
            assert "min=" in result.text
            assert "max=" in result.text
            assert "mean=" in result.text
        finally:
            os.unlink(path)


class TestJsonAdapter:
    def setup_method(self):
        self.adapter = JsonAdapter()

    def test_can_handle(self):
        assert self.adapter.can_handle("/data/test.json") is True
        assert self.adapter.can_handle("/data/test.jsonl") is True
        assert self.adapter.can_handle("/data/test.csv") is False

    def test_ingest_array(self):
        data = [
            {"name": "Alice", "role": "engineer"},
            {"name": "Bob", "role": "designer"},
        ]
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            json.dump(data, f)
            path = f.name

        try:
            result = self.adapter.ingest(path)
            assert result.source_type == SourceType.STRUCTURED
            assert result.metadata["record_count"] == 2
            assert "name is Alice" in result.text
            assert "role is engineer" in result.text
        finally:
            os.unlink(path)

    def test_ingest_nested(self):
        data = {"user": {"name": "Alice", "address": {"city": "Seoul"}}}
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            json.dump(data, f)
            path = f.name

        try:
            result = self.adapter.ingest(path)
            assert "user.name is Alice" in result.text
            assert "user.address.city is Seoul" in result.text
        finally:
            os.unlink(path)

    def test_ingest_jsonl(self):
        lines = '{"a": 1}\n{"a": 2}\n{"a": 3}\n'
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False, mode='w') as f:
            f.write(lines)
            path = f.name

        try:
            result = self.adapter.ingest(path)
            assert result.metadata["record_count"] == 3
        finally:
            os.unlink(path)

    def test_record_to_text_with_list(self):
        record = {"tags": ["alpha", "beta", "gamma"]}
        text = self.adapter._record_to_text(record)
        assert "tags includes alpha, beta, gamma" in text


class TestYamlAdapter:
    def setup_method(self):
        self.adapter = YamlAdapter()

    def test_can_handle(self):
        assert self.adapter.can_handle("/data/config.yaml") is True
        assert self.adapter.can_handle("/data/config.yml") is True
        assert self.adapter.can_handle("/data/config.json") is False

    def test_ingest_dict(self):
        content = "name: TestProject\nversion: 1.0\nfeatures:\n  - auth\n  - api\n"
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
            f.write(content)
            path = f.name

        try:
            result = self.adapter.ingest(path)
            assert "name is TestProject" in result.text
        finally:
            os.unlink(path)
