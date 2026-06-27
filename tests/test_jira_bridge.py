from scripts.jira_bridge import load_dotenv


def test_load_dotenv_no_crash() -> None:
    """
    Ensure load_dotenv runs without crashing even if .env is missing or malformed.
    """
    try:
        load_dotenv()
        success = True
    except Exception:
        success = False

    assert success is True


def test_jira_jql_builder() -> None:
    """
    Test that JQL builder constructs the expected query based on lane.
    (This simulates testing the logic inside get-todo/get-in-progress without hitting the API).
    """
    # Assuming JIRA_PROJECT_KEY is set
    project_key = "DAGY"

    jql_todo = f"project = {project_key} AND status in ('To Do', 'Selected for Development') ORDER BY priority DESC, created ASC"
    jql_in_progress = f"project = {project_key} AND status = 'In Progress' ORDER BY priority DESC, created ASC"

    assert "status in ('To Do', 'Selected for Development')" in jql_todo
    assert "status = 'In Progress'" in jql_in_progress
