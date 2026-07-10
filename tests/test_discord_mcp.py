from unittest.mock import mock_open, patch

import pytest

from discord_mcp.server import request_boss_approval


@pytest.mark.asyncio
async def test_request_boss_approval_success() -> None:
    action = "Delete file"
    reason = "File is useless"
    
    mock_file_data = "{}"
    
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=mock_file_data)) as m:
            with patch("os.makedirs"):
                res = await request_boss_approval(action, reason)
                
                # Check that it wrote something
                m.assert_called()
                
                # Verify that it returns the expected wait string
                assert "Successfully sent request req_" in res
                assert "CRITICAL NEXT STEP: You MUST use the `schedule` tool" in res
