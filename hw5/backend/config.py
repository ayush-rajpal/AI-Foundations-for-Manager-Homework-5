"""Model, paths, and MCP connection for the Campus Customs agent team.

- MODEL_NAME (default gpt-6-luna), served through Portkey with PORTKEY_API_KEY from .env
- build_model(): PydanticAI OpenAI Responses model pointed at the Portkey gateway
- build_mcp_toolset(): stdio connection to mcp_server/server.py (campus-customs), the ONLY
  way the agents touch data/campus_customs_new.db
- .env is loaded from Homework 5/ and its parents (nearest file wins)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from openai import AsyncOpenAI
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent  # Homework 5/
PROMPTS_DIR = BACKEND_DIR / "prompts"
MCP_SERVER = PROJECT_ROOT / "mcp_server" / "server.py"

# Homework 5/.env, then AI Classwork/.env. load_dotenv never overrides a set variable.
for folder in (PROJECT_ROOT, PROJECT_ROOT.parent):
    load_dotenv(folder / ".env")

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-6-luna").strip() or "gpt-6-luna"
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")


def require_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to a .env in Homework 5/ or a parent folder.")
    return key


def build_model() -> OpenAIResponsesModel:
    api_key = require_api_key()
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
        max_retries=4,
        timeout=120,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def build_mcp_client() -> Client:
    """A FastMCP client for the campus-customs server over stdio (used directly by the API routes)."""
    # CAMPUS_CUSTOMS_DB (tests only) points the server at a scratch copy of the database.
    db_override = os.getenv("CAMPUS_CUSTOMS_DB")
    env = {"CAMPUS_CUSTOMS_DB": db_override} if db_override else None
    transport = PythonStdioTransport(MCP_SERVER, python_cmd=sys.executable, cwd=str(PROJECT_ROOT), env=env)
    return Client(transport)


def build_mcp_toolset() -> MCPToolset:
    """One stdio connection to the campus-customs MCP server, shared by every agent in a run.

    Tool errors (e.g. a refused draft) come back to the model as a final failure it must
    adapt to, not a retry prompt; repeated calls are capped by the run's tool_calls_limit.
    """
    return MCPToolset(build_mcp_client(), id="campus-customs", tool_error_behavior="failed")


def load_prompt(agent_id: str) -> str:
    return (PROMPTS_DIR / f"{agent_id}.md").read_text(encoding="utf-8")
