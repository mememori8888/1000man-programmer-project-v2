from __future__ import annotations

from pathlib import Path

import yaml

from elt_v2.bigquery_loader import TRANSFORM_SQL_FILES, render_sql_template


def test_all_registered_sql_files_exist_and_render():
    for filename in TRANSFORM_SQL_FILES:
        path = Path(filename)
        assert path.exists(), filename
        rendered = render_sql_template(
            path.read_text(encoding="utf-8"),
            project_id="project-123",
            dataset="brightdata_raw",
        )
        assert "${PROJECT_ID}" not in rendered
        assert "${DATASET}" not in rendered
        assert "project-123.brightdata_raw" in rendered


def test_bigquery_transform_workflow_exposes_registered_sql_files():
    workflow = yaml.safe_load(Path(".github/workflows/bigquery-transform.yml").read_text(encoding="utf-8"))
    triggers = workflow.get("on") or workflow.get(True)
    options = triggers["workflow_dispatch"]["inputs"]["sql_file"]["options"]

    assert options == TRANSFORM_SQL_FILES
