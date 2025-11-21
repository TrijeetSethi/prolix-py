"""Tests for structural clarity analysis."""

from __future__ import annotations

import pytest

from clarity_score.structure import (
    analyze_structure,
    StructureReport,
    _count_headings,
    _count_list_items,
    _count_code_blocks,
    _estimate_action_ratio,
)


class TestHeadingCounting:
    """Test heading detection and counting."""

    def test_no_headings(self):
        text = "Just some prose without headings."
        assert _count_headings(text) == 0

    def test_single_h1(self):
        text = "# My Title\n\nBody text here."
        assert _count_headings(text) == 1

    def test_multiple_headings(self):
        text = """
# Level 1
## Level 2
### Level 3
Some content
#### Level 4
"""
        assert _count_headings(text) == 4

    def test_headings_in_skilled_doc(self):
        text = """
# Skill Title

## Overview

## How to Use It

### Example Step

## Limitations
"""
        assert _count_headings(text) == 5


class TestListCounting:
    """Test bullet and numbered list detection."""

    def test_no_lists(self):
        text = "No lists here."
        assert _count_list_items(text) == 0

    def test_bullet_points(self):
        text = """
- First item
- Second item
- Third item
"""
        assert _count_list_items(text) == 3

    def test_numbered_list(self):
        text = """
1. First step
2. Second step
3. Third step
"""
        assert _count_list_items(text) == 3

    def test_mixed_lists(self):
        text = """
- Bullet one
1. Numbered one
- Bullet two
2. Numbered two
"""
        assert _count_list_items(text) == 4


class TestCodeBlockCounting:
    """Test fenced code block detection."""

    def test_no_code_blocks(self):
        text = "Just text, no code."
        assert _count_code_blocks(text) == 0

    def test_single_code_block(self):
        text = """
Here is some text.

```python
print("hello")
```

More text after.
"""
        assert _count_code_blocks(text) == 1

    def test_multiple_code_blocks(self):
        text = """
```bash
command1
```

Some prose.

```python
code2
```

And more.

```json
{"key": "val"}
```
"""
        assert _count_code_blocks(text) == 3


class TestActionRatio:
    """Test action verb ratio estimation."""

    def test_purely_descriptive(self):
        text = "This document describes how things work in a general sense. It basically handles various elements of the system." * 3
        ratio = _estimate_action_ratio(text)
        assert ratio < 0.6  # Low action ratio for descriptive prose

    def test_instructional_text(self):
        text = """
Create an event in the calendar. Delete it when done. Update the title field. Run the validation check.
Pass the API key to the configuration file. Set up the OAuth credentials. Ensure all permissions are granted.
"""
        ratio = _estimate_action_ratio(text)
        assert ratio > 0.5  # High action ratio for instructions

    def test_mixed_content(self):
        text = "This is a description of a skill. It creates events when you specify them."
        ratio = _estimate_action_ratio(text)
        # Should be moderate
        assert 0.3 <= ratio <= 0.8


class TestAnalyzeStructure:
    """Test full structural analysis."""

    def test_empty_text(self):
        result = analyze_structure("")
        assert isinstance(result, StructureReport)
        assert result.structural_clarity >= 10  # Minimum floor
        assert result.heading_count == 0
        assert result.list_item_count == 0

    def test_well_structured_skill_doc(self):
        text = """
# My Skill

## Overview
This skill handles calendar management.

## How to Use It
1. Install the API key
2. Run `calendar.create_event()`

```bash
curl -X POST /events \
  -d '{"title": "Meeting"}'
```

## Limitations
Requires OAuth credentials.
"""
        result = analyze_structure(text)
        assert result.heading_count == 4
        # Both numbered lines match the list pattern
        assert result.list_item_count >= 1
        assert result.code_block_count >= 1
        assert result.structural_clarity > 25

    def test_vague_paragraph(self):
        text = """
This is basically a skill that does things. It handles calendar stuff and manages events when you need them to be taken care of in an effective manner by leveraging its appropriate capabilities to enhance your workflow.
"""
        result = analyze_structure(text)
        assert result.heading_count == 0
        assert result.list_item_count == 0
        assert result.code_block_count == 0
        # Should have low structural clarity
        assert result.structural_clarity < 30

    def test_real_anthropic_skill(self):
        """Score a real SKILL.md file to verify integration."""
        from pathlib import Path
        pdf_path = Path("/tmp/anthropic-skills-full/skills/pdf/SKILL.md")
        if not pdf_path.exists():
            pytest.skip("anthropic skills repo not available")

        text = pdf_path.read_text()
        result = analyze_structure(text)
        assert isinstance(result, StructureReport)
        # PDF is a reference doc with many headings and code blocks
        assert result.heading_count > 0
        assert result.structural_clarity >= 20


class TestStructureIntegration:
    """Test structural clarity integrates into the full scoring pipeline."""

    def test_structure_in_analyze_result(self):
        from clarity_score import analyze

        result = analyze(
            "# My Skill\n\n## How to Use It\n1. Install the API.\n2. Run it.",
            include_readability=True,
        )
        assert result.structural_clarity is not None
        assert isinstance(result.structural_clarity, float)
        # Should have some structure (headings + list items)
        assert result.structural_clarity >= 10

    def test_json_includes_structure(self):
        from clarity_score import analyze

        result = analyze("# Title\n\n## Section\n1. Do something.")
        data = result.to_json()
        assert "structural_clarity" in data
        assert isinstance(data["structural_clarity"], float)
