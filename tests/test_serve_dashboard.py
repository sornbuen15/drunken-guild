import pytest
from drunken_team.routes.serve_dashboard import AGENTS_METADATA

def test_agents_metadata():
    """Ensure all required agents are correctly defined in metadata."""
    assert "principal-engineer" in AGENTS_METADATA
    assert "devops-engineer" in AGENTS_METADATA
    
    archmage = AGENTS_METADATA["principal-engineer"]
    assert archmage["name"] == "ARCHMAGE"
    assert "Gemini 2.5 Pro" in archmage["model"]
