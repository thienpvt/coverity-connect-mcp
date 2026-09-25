import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from coverity_mcp_server import main, main_production
from coverity_mcp_server import coverity_client, coverity_client_production


CLIENTS = (coverity_client.CoverityClient, coverity_client_production.CoverityClient)
SERVERS = (main, main_production)


@pytest.mark.parametrize("client_type", CLIENTS)
def test_search_posts_filters_and_decodes_rows(client_type):
    client = client_type("localhost", username="user", password="key")
    client._make_request = AsyncMock(return_value={
        "rows": [[{"key": "cid", "value": "42"}, {"key": "displayImpact", "value": "High"}]],
        "totalRows": 1,
    })
    result = asyncio.run(client.get_defects(
        stream_id="main", query="null", filters={"checker": "NULL_RETURNS", "severity": "High", "status": "New"}, limit=7
    ))
    assert result == [{"cid": "42", "displayImpact": "High"}]
    args, kwargs = client._make_request.call_args
    assert args == ("POST", "/api/v2/issues/search")
    assert kwargs["data"]["rowCount"] == 7
    assert kwargs["data"]["offset"] == 0
    assert kwargs["data"]["query"] == "null"
    assert kwargs["data"]["filters"] == [
        {"columnKey": key, "matchMode": "oneOrMoreMatch", "matchers": [matcher]}
        for key, matcher in (
            ("stream", {"class": "Stream", "name": "main", "type": "nameMatcher"}),
            ("checker", {"key": "NULL_RETURNS", "type": "keyMatcher"}),
            ("displayImpact", {"key": "High", "type": "keyMatcher"}),
            ("displayStatus", {"key": "New", "type": "keyMatcher"}),
        )
    ]


@pytest.mark.parametrize("client_type", CLIENTS)
def test_view_contents_preserves_paging_metadata(client_type):
    client = client_type("localhost", username="user", password="key")
    page = {"offset": 100, "totalRows": 205, "rows": [[{"key": "cid", "value": "42"}]]}
    client._make_request = AsyncMock(return_value=page)
    assert asyncio.run(client.get_view_contents("77", "10380", row_count=100, offset=100)) == page
    client._make_request.assert_awaited_once_with("GET", "/api/v2/views/viewContents/77", params={
        "projectId": "10380", "rowCount": 100, "offset": 100,
    })
    for count, offset in ((0, 0), (1001, 0), (100, -1)):
        with pytest.raises(ValueError):
            asyncio.run(client.get_view_contents("77", "10380", row_count=count, offset=offset))


@pytest.mark.parametrize("client_type", CLIENTS)
def test_occurrences_and_generic_get(client_type):
    client = client_type("localhost", username="user", password="key")
    client._make_request = AsyncMock(return_value={"rows": [{"event": "trace"}]})
    assert asyncio.run(client.get_defect_occurrences("42")) == {"rows": [{"event": "trace"}]}
    client._make_request.assert_awaited_with("GET", "/api/v2/issues/42/occurrences")
    assert asyncio.run(client.coverity_api_get("/api/v2/projects", {"rowCount": 2})) == {"rows": [{"event": "trace"}]}
    client._make_request.assert_awaited_with("GET", "/api/v2/projects", params={"rowCount": 2})
    for path in ("https://other.test/api/v2/projects", "/api/../admin", "/api//other", "/api/%2e%2e/admin", "/api/v2/projects?x=1", "/api/v2/projects#fragment", "/api/v2/projects?", "/api/v2/projects#", "/api/\\evil"):
        with pytest.raises(ValueError):
            asyncio.run(client.coverity_api_get(path))


def test_production_server_starts_without_proxy(monkeypatch):
    monkeypatch.setenv("COVERITY_HOST", "https://localhost:8443")
    monkeypatch.setenv("COVAUTHUSER", "user")
    monkeypatch.setenv("COVAUTHKEY", "key")
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "PROXY_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(main_production, "coverity_client", None)
    server = main_production.create_server()
    assert {"get_view_contents", "get_defect_occurrences", "coverity_api_get"} <= {
        tool.name for tool in asyncio.run(server.list_tools())
    }


@pytest.mark.parametrize("module", SERVERS)
def test_new_tools_are_registered_with_schema(module):
    with patch.object(module, "initialize_client", return_value=object()):
        server = module.create_server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {"get_view_contents", "get_defect_occurrences", "coverity_api_get"} <= tools.keys()
    view = tools["get_view_contents"].inputSchema
    assert set(view["required"]) == {"view_id", "project_id"}
    assert view["properties"]["row_count"]["default"] == 100
    assert view["properties"]["offset"]["default"] == 0
    assert tools["coverity_api_get"].inputSchema["required"] == ["path"]
