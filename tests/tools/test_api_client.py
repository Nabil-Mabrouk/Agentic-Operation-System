# tests/tools/test_api_client.py
import pytest
from aos.tools.plugins.api_client import ApiClientTool
import json

@pytest.mark.asyncio
async def test_successful_get_request(httpx_mock, monkeypatch):
    """Vérifie qu'une requête GET simple réussit."""
    test_url = "https://api.example.com/data"
    mock_response = {"key": "value", "data": [1, 2, 3]}
    httpx_mock.add_response(url=test_url, json=mock_response)
    
    tool = ApiClientTool()
    # On remplace la validation par une fonction qui ne fait rien
    monkeypatch.setattr(tool, "_validate_url", lambda url: None)

    result = await tool.execute({
        "method": "GET",
        "url": test_url
    }, "test-agent")
    
    assert result["status"] == "success"
    assert result["status_code"] == 200
    assert result["body"] == mock_response

@pytest.mark.asyncio
async def test_post_request_with_json_body(httpx_mock, monkeypatch):
    """Vérifie qu'une requête POST avec un corps JSON est correctement envoyée."""
    test_url = "https://api.example.com/submit"
    httpx_mock.add_response(url=test_url, status_code=201, json={"status": "created"})
    
    tool = ApiClientTool()
        # --- PATCH ICI ---
    monkeypatch.setattr(tool, "_validate_url", lambda url: None)

    payload = {"name": "AOS", "version": "1.0"}
    result = await tool.execute({
        "method": "POST",
        "url": test_url,
        "json_body": payload
    }, "test-agent")

    assert result["status"] == "success"
    assert result["status_code"] == 201
    
    # Vérifie que la requête a été faite avec le bon corps JSON
    sent_request = httpx_mock.get_request()
    sent_data = json.loads(sent_request.content) # sent_request.content est en bytes
    assert sent_data == payload

@pytest.mark.asyncio
async def test_prevents_calling_localhost():
    """Teste la sécurité : l'appel à localhost doit être bloqué."""
    tool = ApiClientTool()
    result = await tool.execute({
        "method": "GET",
        "url": "http://localhost/api"
    }, "test-agent")

    assert result["code"] == "SECURITY_VALIDATION_FAILED"
    assert "loopback" in result["error"]

@pytest.mark.asyncio
async def test_prevents_calling_private_ip():
    """Teste la sécurité : l'appel à une IP privée doit être bloqué."""
    tool = ApiClientTool()
    result = await tool.execute({
        "method": "GET",
        "url": "http://192.168.1.1/data"
    }, "test-agent")

    assert result["code"] == "SECURITY_VALIDATION_FAILED"
    assert "private" in result["error"]