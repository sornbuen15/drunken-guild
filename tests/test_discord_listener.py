import pytest
from drunken_team.services.discord_listener import extract_clean_response

def test_extract_clean_response():
    raw_log = """
<thinking>
This is an internal thought process.
It should be removed.
</thinking>
I will run a command.
[System] Running task...
[Warning] Something happened.
Executing command: ls
Actual message here.
Another line of the actual message.
"""
    
    cleaned = extract_clean_response(raw_log)
    
    assert "This is an internal thought process." not in cleaned
    assert "I will run a command." not in cleaned
    assert "[System]" not in cleaned
    assert "Actual message here." in cleaned
    assert "Another line of the actual message." in cleaned
