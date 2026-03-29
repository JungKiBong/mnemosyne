"""
Structural Extractor — Phase 1 of 2-Phase Hybrid Extraction.

Extracts deterministic structural skeletons from any data source
WITHOUT calling the LLM. This preserves structure (headings, tables,
metadata, hierarchies) that would be lost if the data were flattened
to plain text before NER.

Inspired by Understand-Anything's file-analyzer Phase 1 script approach,
generalized for universal data sources (PDF, CSV, JSON, HTML, etc.).

Usage:
    extractor = StructuralExtractor()
    skeleton = extractor.extract("/path/to/report.pdf")
    skeleton = extractor.extract_from_text(text, source_type="markdown")
"""

import hashlib
import json
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path

from ..models.knowledge_types import SectionInfo

logger = logging.getLogger("mirofish.structural_extractor")


@dataclass
class StructuralSkeleton:
    """
    Phase 1 output: structural backbone of a data source.

    Contains everything that can be determined WITHOUT an LLM:
    sections, metadata, fingerprint, and pre-split chunks
    that respect structural boundaries.
    """
    source_ref: str                         # Original path/URL
    source_type: str                        # "pdf", "markdown", "csv", "json", ...
    sections: List[SectionInfo] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""                   # SHA-256 of content
    structural_chunks: List[str] = field(default_factory=list)
    structural_relations: List[Dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""                      # Full extracted text (for fallback)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "source_type": self.source_type,
            "sections": [{"name": s.name, "level": s.level,
                          "preview": s.content_preview[:100]}
                         for s in self.sections],
            "metadata": self.metadata,
            "fingerprint": self.fingerprint,
            "chunk_count": len(self.structural_chunks),
            "relation_count": len(self.structural_relations),
            "stats": self.stats,
        }


class StructuralExtractor:
    """
    Extracts structural skeletons from data sources.

    Strategy pattern: each source type has a dedicated extraction method.
    All methods are deterministic (no LLM calls).
    """

    # Maximum chunk size (chars) — structural boundaries respected
    MAX_CHUNK_SIZE = 600
    MIN_CHUNK_SIZE = 50

    def extract(self, source_ref: str, text: Optional[str] = None) -> StructuralSkeleton:
        """
        Extract structural skeleton from a data source.

        Args:
            source_ref: File path, URL, or source identifier
            text: Pre-extracted text (if already available from adapter)

        Returns:
            StructuralSkeleton with sections, metadata, and chunks
        """
        source_type = self._detect_type(source_ref)

        if text is None:
            text = self._read_source(source_ref)

        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()

        extractor_map = {
            "markdown": self._extract_markdown,
            "pdf": self._extract_pdf,
            "csv": self._extract_csv,
            "json": self._extract_json,
            "yaml": self._extract_yaml,
            "html": self._extract_html,
            "plain": self._extract_plain,
        }

        extractor = extractor_map.get(source_type, self._extract_plain)
        skeleton = extractor(source_ref, text)
        skeleton.fingerprint = fingerprint
        skeleton.source_type = source_type
        skeleton.raw_text = text

        # Generate structural chunks if not already done by the extractor
        if not skeleton.structural_chunks:
            skeleton.structural_chunks = self._chunk_by_sections(
                text, skeleton.sections
            )

        # Compute basic stats
        skeleton.stats = {
            "total_chars": len(text),
            "total_lines": text.count("\n") + 1,
            "section_count": len(skeleton.sections),
            "chunk_count": len(skeleton.structural_chunks),
            "relation_count": len(skeleton.structural_relations),
        }

        logger.info(
            "Structural extraction: %s → %d sections, %d chunks, fingerprint=%s",
            source_ref, len(skeleton.sections),
            len(skeleton.structural_chunks), fingerprint[:12]
        )

        return skeleton

    def extract_from_text(self, text: str, source_type: str = "plain",
                          source_ref: str = "inline") -> StructuralSkeleton:
        """Convenience method for text-only extraction."""
        return self.extract(source_ref=source_ref, text=text)

    # ──────────────────────────────────────────
    # Source Type Detection
    # ──────────────────────────────────────────

    def _detect_type(self, source_ref: str) -> str:
        """Detect source type from path/extension."""
        ref = source_ref.lower()
        ext_map = {
            ".md": "markdown", ".markdown": "markdown",
            ".pdf": "pdf",
            ".csv": "csv", ".tsv": "csv",
            ".json": "json", ".jsonl": "json",
            ".yaml": "yaml", ".yml": "yaml",
            ".html": "html", ".htm": "html",
            ".txt": "plain",
        }
        for ext, stype in ext_map.items():
            if ref.endswith(ext):
                return stype
        if ref.startswith("http"):
            return "html"
        return "plain"

    def _read_source(self, source_ref: str) -> str:
        """Read text content from a source file."""
        from ..utils.file_parser import FileParser
        path = Path(source_ref)
        if path.exists():
            try:
                return FileParser.extract_text(source_ref)
            except Exception:
                return path.read_text(encoding="utf-8", errors="replace")
        return ""

    # ──────────────────────────────────────────
    # Extractors by Source Type
    # ──────────────────────────────────────────

    def _extract_markdown(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Extract structure from Markdown documents."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="markdown")
        lines = text.split("\n")
        sections = []
        current_section_start = 0

        for i, line in enumerate(lines):
            heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
            if heading_match:
                level = len(heading_match.group(1))
                name = heading_match.group(2).strip()
                # Close previous section
                if sections:
                    prev = sections[-1]
                    content = "\n".join(lines[current_section_start:i])
                    prev.content_preview = content[:200]
                sections.append(SectionInfo(
                    name=name, level=level, line_range=(i + 1, i + 1)
                ))
                current_section_start = i

        # Close last section
        if sections:
            content = "\n".join(lines[current_section_start:])
            sections[-1].content_preview = content[:200]
            sections[-1].line_range = (sections[-1].line_range[0], len(lines))

        skeleton.sections = sections

        # Extract metadata from front matter
        if text.startswith("---"):
            fm_end = text.find("---", 3)
            if fm_end > 0:
                fm_text = text[3:fm_end].strip()
                for line in fm_text.split("\n"):
                    if ":" in line:
                        key, _, val = line.partition(":")
                        skeleton.metadata[key.strip()] = val.strip()

        # Build structural relations (section hierarchy)
        for i, sec in enumerate(sections):
            for j in range(i + 1, len(sections)):
                if sections[j].level > sec.level:
                    skeleton.structural_relations.append({
                        "source": f"section:{sec.name}",
                        "target": f"section:{sections[j].name}",
                        "type": "contains",
                        "weight": 1.0,
                    })
                else:
                    break  # Stop at same or higher level

        return skeleton

    def _extract_pdf(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Extract structure from PDF (text already extracted by adapter)."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="pdf")

        # Heuristic: detect headings by capitalization and short lines
        lines = text.split("\n")
        sections = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            # Heuristic: uppercase lines, short lines, or lines with numbering
            is_heading = (
                (stripped.isupper() and 3 < len(stripped) < 80)
                or re.match(r"^\d+\.\s+\S", stripped)
                or re.match(r"^[A-Z][A-Za-z\s]{2,50}$", stripped)
            )
            if is_heading:
                level = 1 if stripped.isupper() else 2
                sections.append(SectionInfo(
                    name=stripped[:60], level=level, line_range=(i + 1, i + 1),
                    content_preview=stripped[:200]
                ))

        skeleton.sections = sections
        return skeleton

    def _extract_csv(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Extract structure from CSV/TSV data."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="csv")

        lines = text.strip().split("\n")
        if not lines:
            return skeleton

        # Header detection
        header = lines[0]
        delimiter = "\t" if "\t" in header else ","
        columns = [c.strip().strip('"') for c in header.split(delimiter)]

        skeleton.metadata = {
            "columns": columns,
            "column_count": len(columns),
            "row_count": len(lines) - 1,
            "delimiter": delimiter,
        }

        # Each column becomes a "section"
        for col in columns:
            skeleton.sections.append(SectionInfo(name=col, level=1))

        # Chunk by rows (groups of N rows)
        chunk_size = 20
        for i in range(1, len(lines), chunk_size):
            batch = lines[i:i + chunk_size]
            chunk_text = header + "\n" + "\n".join(batch)
            skeleton.structural_chunks.append(chunk_text)

        return skeleton

    def _extract_json(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Extract structure from JSON data."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="json")

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return skeleton

        if isinstance(data, dict):
            skeleton.metadata["top_level_keys"] = list(data.keys())[:50]
            skeleton.metadata["key_count"] = len(data)
            for key in list(data.keys())[:30]:
                val = data[key]
                val_type = type(val).__name__
                preview = str(val)[:100] if not isinstance(val, (dict, list)) else f"({val_type})"
                skeleton.sections.append(SectionInfo(
                    name=key, level=1, content_preview=preview
                ))
        elif isinstance(data, list):
            skeleton.metadata["array_length"] = len(data)
            skeleton.metadata["item_type"] = type(data[0]).__name__ if data else "empty"

        return skeleton

    def _extract_yaml(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Extract structure from YAML data."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="yaml")

        # Simple key extraction without importing PyYAML
        top_keys = []
        for line in text.split("\n"):
            if line and not line.startswith(" ") and not line.startswith("#"):
                key = line.split(":")[0].strip()
                if key and not key.startswith("-"):
                    top_keys.append(key)
                    skeleton.sections.append(SectionInfo(name=key, level=1))

        skeleton.metadata["top_level_keys"] = top_keys
        return skeleton

    def _extract_html(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Extract structure from HTML pages."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="html")

        # Extract headings
        for match in re.finditer(r"<h([1-6])[^>]*>(.*?)</h\1>", text, re.IGNORECASE | re.DOTALL):
            level = int(match.group(1))
            heading_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if heading_text:
                skeleton.sections.append(SectionInfo(
                    name=heading_text[:80], level=level,
                    content_preview=heading_text[:200]
                ))

        # Extract title
        title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        if title_match:
            skeleton.metadata["title"] = title_match.group(1).strip()

        # Extract meta tags
        for meta in re.finditer(r'<meta\s+(?:name|property)="([^"]+)"\s+content="([^"]+)"',
                                text, re.IGNORECASE):
            skeleton.metadata[f"meta:{meta.group(1)}"] = meta.group(2)[:200]

        return skeleton

    def _extract_plain(self, source_ref: str, text: str) -> StructuralSkeleton:
        """Fallback: extract structure from plain text."""
        skeleton = StructuralSkeleton(source_ref=source_ref, source_type="plain")

        # Try to detect paragraph blocks as sections
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for i, para in enumerate(paragraphs[:50]):
            first_line = para.split("\n")[0][:60]
            skeleton.sections.append(SectionInfo(
                name=f"Para {i + 1}: {first_line}",
                level=2,
                content_preview=para[:200]
            ))

        return skeleton

    # ──────────────────────────────────────────
    # Structure-Aware Chunking
    # ──────────────────────────────────────────

    def _chunk_by_sections(self, text: str, sections: List[SectionInfo]) -> List[str]:
        """
        Split text into chunks that respect structural boundaries.

        Unlike naive fixed-size chunking, this ensures sections
        are not split mid-sentence and metadata context is preserved.
        """
        if not sections:
            return self._fallback_chunk(text)

        lines = text.split("\n")
        chunks = []

        for i, sec in enumerate(sections):
            start = (sec.line_range[0] - 1) if sec.line_range else 0
            if i + 1 < len(sections) and sections[i + 1].line_range:
                end = sections[i + 1].line_range[0] - 1
            else:
                end = len(lines)

            section_text = "\n".join(lines[start:end]).strip()
            if len(section_text) < self.MIN_CHUNK_SIZE:
                continue

            # If section is too large, sub-chunk by paragraphs
            if len(section_text) > self.MAX_CHUNK_SIZE:
                prefix = f"[Section: {sec.name}]\n"
                sub_chunks = self._fallback_chunk(section_text, prefix=prefix)
                chunks.extend(sub_chunks)
            else:
                chunks.append(f"[Section: {sec.name}]\n{section_text}")

        return chunks if chunks else self._fallback_chunk(text)

    def _fallback_chunk(self, text: str, prefix: str = "") -> List[str]:
        """Paragraph-based fallback chunking."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = prefix

        for para in paragraphs:
            if len(current) + len(para) > self.MAX_CHUNK_SIZE:
                if current.strip():
                    chunks.append(current.strip())
                current = prefix + para
            else:
                current += "\n\n" + para

        if current.strip():
            chunks.append(current.strip())

        return chunks[:200]  # Safety cap
