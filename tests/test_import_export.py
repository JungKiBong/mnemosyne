#!/usr/bin/env python3
"""
End-to-End Test — Memory Import/Export Round-Trip

Tests the full lifecycle:
  1. Export Memory Manifest (create_manifest)
  2. Export RAG Corpus (export_rag_corpus)
  3. Import Manifest back (import_manifest, both merge & create strategies)
  4. Import RAG Corpus (import_rag_corpus)
  5. Verify imported data is queryable
  6. List imports history

Uses live Neo4j connection (same as the rest of the test suite).
"""

import json
import sys
import os
import uuid

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# Load .env if exists
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.app.storage.data_product import MemoryDataProduct
from src.app.config import Config
from neo4j import GraphDatabase


class ImportExportTester:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )
        self.dp = MemoryDataProduct(driver=self.driver)
        self.test_prefix = f"import_test_{uuid.uuid4().hex[:8]}"
        self.results = []

    def run_all(self):
        print("=" * 60)
        print("🧪 Memory Import/Export Round-Trip Test")
        print("=" * 60)

        try:
            self.test_0_seed_data()
            self.test_1_export_manifest()
            self.test_2_export_rag_corpus()
            self.test_3_import_manifest_merge()
            self.test_4_import_manifest_create()
            self.test_5_import_rag_corpus()
            self.test_6_import_malformed_rag()
            self.test_7_list_imports()
            self.test_8_verify_imported_data()
        finally:
            self.cleanup()
            self.print_summary()

    # ──────────────────────────────────────────
    # Test 0: Seed test data
    # ──────────────────────────────────────────

    def test_0_seed_data(self):
        """Create test nodes and edges for export/import testing."""
        test_name = "Seed Test Data"
        try:
            with self.driver.session() as session:
                # Create 3 test entities
                for i in range(3):
                    session.run("""
                        CREATE (e:Entity:Memory {
                            uuid: $uuid,
                            graph_id: $graph_id,
                            name: $name,
                            name_lower: $name_lower,
                            summary: $summary,
                            salience: $salience,
                            scope: $scope,
                            source_type: 'test',
                            access_count: $i,
                            created_at: datetime().epochMillis
                        })
                    """,
                        uuid=f"{self.test_prefix}-node-{i}",
                        graph_id=self.test_prefix,
                        name=f"TestEntity_{self.test_prefix}_{i}",
                        name_lower=f"testentity_{self.test_prefix}_{i}",
                        summary=f"Test entity {i} for import/export testing",
                        salience=0.5 + i * 0.2,
                        scope=["personal", "tribal", "global"][i],
                        i=i,
                    )

                # Create 2 edges
                session.run("""
                    MATCH (s:Entity {uuid: $s_uuid})
                    MATCH (t:Entity {uuid: $t_uuid})
                    CREATE (s)-[:RELATES_TO {
                        name: 'test_relation',
                        weight: 0.8,
                        fact: 'Test edge for import testing'
                    }]->(t)
                """,
                    s_uuid=f"{self.test_prefix}-node-0",
                    t_uuid=f"{self.test_prefix}-node-1",
                )
                session.run("""
                    MATCH (s:Entity {uuid: $s_uuid})
                    MATCH (t:Entity {uuid: $t_uuid})
                    CREATE (s)-[:RELATES_TO {
                        name: 'depends_on',
                        weight: 0.6,
                        fact: 'Dependency relationship'
                    }]->(t)
                """,
                    s_uuid=f"{self.test_prefix}-node-1",
                    t_uuid=f"{self.test_prefix}-node-2",
                )

                # Create a test agent
                session.run("""
                    MERGE (a:Agent {agent_id: $agent_id})
                    SET a.name = $name, a.role = 'analyst',
                        a.subscribed_scopes = ['personal', 'tribal'],
                        a.registered_at = datetime().epochMillis
                """,
                    agent_id=f"agent-{self.test_prefix}",
                    name=f"TestAgent_{self.test_prefix}",
                )

            self._pass(test_name, "3 nodes, 2 edges, 1 agent created")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 1: Export Manifest
    # ──────────────────────────────────────────

    def test_1_export_manifest(self):
        test_name = "Export Manifest"
        try:
            manifest = self.dp.create_manifest(
                name=f"Test Manifest {self.test_prefix}",
                description="Automated test export",
            )

            assert manifest.get("manifest_id"), "Missing manifest_id"
            assert manifest.get("entities") is not None, "Missing entities"
            assert manifest.get("relations") is not None, "Missing relations"
            assert manifest.get("schema"), "Missing schema"
            assert manifest.get("lineage"), "Missing lineage"

            node_count = manifest["stats"]["node_count"]
            edge_count = manifest["stats"]["edge_count"]

            # Store for later import tests
            self._manifest = manifest
            self._manifest_json = json.dumps(manifest, ensure_ascii=False, default=str)

            self._pass(test_name,
                f"manifest_id={manifest['manifest_id'][:8]}, "
                f"{node_count} nodes, {edge_count} edges, "
                f"JSON size={len(self._manifest_json)} bytes")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 2: Export RAG Corpus
    # ──────────────────────────────────────────

    def test_2_export_rag_corpus(self):
        test_name = "Export RAG Corpus"
        try:
            result = self.dp.export_rag_corpus(
                scope=None,
                min_salience=0.3,
                include_relations=True,
                format="jsonl",
            )

            assert result.get("content"), "Empty RAG corpus content"
            assert result.get("document_count", 0) > 0, "No documents in RAG corpus"

            # Verify JSONL format
            lines = result["content"].strip().split("\n")
            first_doc = json.loads(lines[0])
            assert "id" in first_doc, "Missing 'id' in RAG document"
            assert "text" in first_doc, "Missing 'text' in RAG document"
            assert "metadata" in first_doc, "Missing 'metadata' in RAG document"

            # Store for later import
            self._rag_content = result["content"]

            self._pass(test_name,
                f"{result['document_count']} documents, "
                f"{len(lines)} JSONL lines, "
                f"content size={len(result['content'])} bytes")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 3: Import Manifest (merge strategy)
    # ──────────────────────────────────────────

    def test_3_import_manifest_merge(self):
        test_name = "Import Manifest (merge)"
        try:
            result = self.dp.import_manifest(
                manifest=self._manifest,
                target_graph_id="import-test-merge",
                merge_strategy="merge",
                imported_by="test_runner",
            )

            assert result["status"] == "imported", f"Expected 'imported', got {result['status']}"
            assert result.get("import_id"), "Missing import_id"

            stats = result["stats"]
            assert stats["nodes_imported"] >= 0, "Negative nodes_imported"
            assert len(stats["errors"]) == 0, f"Import errors: {stats['errors']}"

            self._pass(test_name,
                f"import_id={result['import_id'][:8]}, "
                f"nodes={stats['nodes_imported']}, "
                f"edges={stats['edges_imported']}, "
                f"agents={stats['agents_imported']}")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 4: Import Manifest (create strategy)
    # ──────────────────────────────────────────

    def test_4_import_manifest_create(self):
        test_name = "Import Manifest (create)"
        try:
            # Use small subset for create strategy
            small_manifest = {
                "manifest_id": "test-create-manifest",
                "name": "Create Strategy Test",
                "entities": [
                    {
                        "id": f"create-test-{uuid.uuid4().hex[:8]}",
                        "label": f"CreateTest_{self.test_prefix}",
                        "salience": 0.7,
                        "scope": "tribal",
                        "summary": "Node created via create strategy import",
                    }
                ],
                "relations": [],
                "agents": [],
            }

            result = self.dp.import_manifest(
                manifest=small_manifest,
                target_graph_id="import-test-create",
                merge_strategy="create",
                imported_by="test_runner",
            )

            assert result["status"] == "imported"
            stats = result["stats"]
            assert stats["nodes_imported"] == 1, f"Expected 1 node, got {stats['nodes_imported']}"

            self._pass(test_name,
                f"Created 1 new node with new UUID, "
                f"strategy=create, graph_id=import-test-create")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 5: Import RAG Corpus
    # ──────────────────────────────────────────

    def test_5_import_rag_corpus(self):
        test_name = "Import RAG Corpus (JSONL)"
        try:
            # Build a custom JSONL corpus
            docs = [
                {"id": f"rag-import-{self.test_prefix}-0",
                 "text": "TurboQuant enables FP4/FP6 quantization on GPU at runtime",
                 "metadata": {"name": "TurboQuant", "salience": 0.9, "scope": "tribal"}},
                {"id": f"rag-import-{self.test_prefix}-1",
                 "text": "Ebbinghaus forgetting curve models memory decay over time",
                 "metadata": {"name": "Ebbinghaus Curve", "salience": 0.85, "scope": "global"}},
                {"id": f"rag-import-{self.test_prefix}-2",
                 "text": "Synaptic Bridge enables inter-agent memory sharing",
                 "metadata": {"name": "Synaptic Bridge", "salience": 0.8, "scope": "social"}},
            ]
            jsonl = "\n".join(json.dumps(d, ensure_ascii=False) for d in docs)

            result = self.dp.import_rag_corpus(
                content=jsonl,
                target_graph_id="rag-import-test",
                default_scope="personal",
                imported_by="test_runner",
            )

            assert result["status"] == "imported"
            stats = result["stats"]
            assert stats["imported"] == 3, f"Expected 3, got {stats['imported']}"
            assert stats["skipped"] == 0, f"Unexpected skips: {stats['skipped']}"

            self._pass(test_name,
                f"Imported {stats['imported']}/{stats['total_lines']} docs, "
                f"graph_id=rag-import-test")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 6: Import malformed RAG (error handling)
    # ──────────────────────────────────────────

    def test_6_import_malformed_rag(self):
        test_name = "Import Malformed RAG (error handling)"
        try:
            malformed_jsonl = (
                '{"id":"ok-1","text":"Valid document","metadata":{"name":"OK"}}\n'
                'this is not valid json\n'
                '{"id":"ok-2","text":"Second valid","metadata":{"name":"OK2"}}\n'
                '{"id":"empty","text":"","metadata":{}}\n'  # empty text → skip
            )

            result = self.dp.import_rag_corpus(
                content=malformed_jsonl,
                target_graph_id="rag-malformed-test",
                imported_by="test_runner",
            )

            stats = result["stats"]
            assert stats["imported"] == 2, f"Expected 2 valid imports, got {stats['imported']}"
            assert stats["skipped"] == 2, f"Expected 2 skips, got {stats['skipped']}"
            assert len(stats["errors"]) >= 1, "Expected at least 1 error recorded"

            self._pass(test_name,
                f"Imported={stats['imported']}, Skipped={stats['skipped']}, "
                f"Errors={len(stats['errors'])} (graceful handling confirmed)")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 7: List Imports
    # ──────────────────────────────────────────

    def test_7_list_imports(self):
        test_name = "List Import History"
        try:
            imports = self.dp.list_imports()

            assert isinstance(imports, list), "Expected list"
            assert len(imports) >= 2, f"Expected ≥2 imports, got {len(imports)}"

            # Verify structure
            first = imports[0]
            assert "import_id" in first, "Missing import_id"
            assert "source_name" in first, "Missing source_name"
            assert "nodes_imported" in first, "Missing nodes_imported"

            self._pass(test_name,
                f"{len(imports)} import records found, "
                f"latest: {first.get('source_name', 'N/A')}")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Test 8: Verify imported data is queryable
    # ──────────────────────────────────────────

    def test_8_verify_imported_data(self):
        test_name = "Verify Imported Data Queryable"
        try:
            with self.driver.session() as session:
                # Check RAG-imported entities
                result = session.run("""
                    MATCH (e:Entity)
                    WHERE e.uuid STARTS WITH $prefix AND e.imported = true
                    RETURN count(e) AS cnt
                """, prefix=f"rag-import-{self.test_prefix}").single()
                rag_count = result["cnt"]

                # Check imported flag is set
                imported_nodes = session.run("""
                    MATCH (e:Entity {imported: true})
                    RETURN count(e) AS cnt
                """).single()
                total_imported = imported_nodes["cnt"]

                # Check MemoryImport records
                import_records = session.run("""
                    MATCH (m:MemoryImport)
                    RETURN count(m) AS cnt
                """).single()

            assert rag_count >= 3, f"Expected ≥3 RAG nodes, got {rag_count}"
            assert total_imported > 0, "No imported nodes found"

            self._pass(test_name,
                f"RAG nodes={rag_count}, total imported={total_imported}, "
                f"import records={import_records['cnt']}")
        except Exception as e:
            self._fail(test_name, str(e))

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def cleanup(self):
        """Remove test data."""
        try:
            with self.driver.session() as session:
                # Clean test entities
                session.run("""
                    MATCH (e:Entity)
                    WHERE e.graph_id STARTS WITH $prefix
                       OR e.graph_id IN ['import-test-merge','import-test-create',
                                         'rag-import-test','rag-malformed-test']
                       OR e.uuid STARTS WITH $prefix
                       OR e.uuid STARTS WITH 'rag-import-'
                       OR e.uuid IN ['ok-1','ok-2']
                    DETACH DELETE e
                """, prefix=self.test_prefix)

                # Clean test agents
                session.run("""
                    MATCH (a:Agent)
                    WHERE a.agent_id STARTS WITH 'agent-' + $prefix
                       OR a.imported = true
                    DETACH DELETE a
                """, prefix=self.test_prefix)

                # Clean import records
                session.run("MATCH (m:MemoryImport) DETACH DELETE m")

                # Clean test manifests
                session.run("""
                    MATCH (m:MemoryManifest)
                    WHERE m.name STARTS WITH 'Test Manifest'
                    DETACH DELETE m
                """)

            print("\n🧹 Cleanup: test data removed")
        except Exception as e:
            print(f"\n⚠️  Cleanup warning: {e}")
        finally:
            self.dp.close()

    def _pass(self, name, detail=""):
        self.results.append(("PASS", name, detail))
        print(f"  ✅ {name}: {detail}")

    def _fail(self, name, detail=""):
        self.results.append(("FAIL", name, detail))
        print(f"  ❌ {name}: {detail}")

    def print_summary(self):
        print("\n" + "=" * 60)
        passed = sum(1 for r in self.results if r[0] == "PASS")
        failed = sum(1 for r in self.results if r[0] == "FAIL")
        total = len(self.results)
        print(f"📊 Results: {passed}/{total} passed, {failed} failed")

        if failed > 0:
            print("\n❌ Failed tests:")
            for status, name, detail in self.results:
                if status == "FAIL":
                    print(f"   - {name}: {detail}")
        else:
            print("🎉 All tests passed!")
        print("=" * 60)


if __name__ == "__main__":
    tester = ImportExportTester()
    tester.run_all()
