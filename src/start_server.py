from __future__ import annotations

from os import environ

from aiohttp.web import Application, Request, Response, run_app
from microsoft_agents.hosting.aiohttp import (
    CloudAdapter,
    jwt_authorization_middleware,
    start_agent_process,
)
from microsoft_agents.hosting.core import AgentApplication, AgentAuthConfiguration
from opentelemetry import trace


def start_server(
    agent_application: AgentApplication,
    auth_configuration: AgentAuthConfiguration | None,
) -> None:
    async def entry_point(req: Request) -> Response:
        span = trace.get_current_span()
        # Capture selected inbound headers to help correlate Bot Service requests.
        for header in (
            "x-ms-request-id",
            "x-ms-client-request-id",
            "request-id",
            "traceparent",
        ):
            value = req.headers.get(header)
            if value:
                span.set_attribute(f"bot.http.header.{header}", value)

        agent: AgentApplication = req.app["agent_app"]
        adapter: CloudAdapter = req.app["adapter"]
        return await start_agent_process(req, agent, adapter)

    # Only enforce JWT validation when an auth configuration is supplied.
    middlewares = [jwt_authorization_middleware] if auth_configuration is not None else []
    app = Application(middlewares=middlewares)
    # Bot Framework activity endpoint.
    app.router.add_post("/api/messages", entry_point)
    # Simple probe endpoints for reachability and liveness checks.
    app.router.add_get("/api/messages", lambda _: Response(status=200))
    app.router.add_get("/healthz", lambda _: Response(status=200, text="ok"))

    app["agent_configuration"] = auth_configuration
    app["agent_app"] = agent_application
    app["adapter"] = agent_application.adapter

    run_app(app, host="0.0.0.0", port=int(environ.get("PORT", "3978")))
