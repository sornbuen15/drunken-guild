from scripts.confluence_bridge import strip_frontmatter


def test_strip_frontmatter():
    markdown_with_frontmatter = """---
title: "My Doc"
date: "2024-01-01"
---
# Header
Content goes here.
"""
    markdown_without_frontmatter = """# Header
Content goes here.
"""

    # It should correctly strip the YAML frontmatter
    assert (
        strip_frontmatter(markdown_with_frontmatter).strip()
        == "# Header\nContent goes here."
    )

    # It should leave normal markdown intact
    assert (
        strip_frontmatter(markdown_without_frontmatter).strip()
        == "# Header\nContent goes here."
    )

    # Test edge case with multiple ---
    markdown_with_hr = """---
title: "Doc"
---
# Header
---
Horizontal rule above.
"""
    assert "Horizontal rule above." in strip_frontmatter(markdown_with_hr)
