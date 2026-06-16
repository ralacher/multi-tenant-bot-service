from __future__ import annotations

import asyncio
import logging
import os
import uuid

from dotenv import load_dotenv
from microsoft_agents.activity import load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import CloudAdapter
from microsoft_agents.hosting.core import (
    AgentApplication,
    AgentAuthConfiguration,
    MemoryStorage,
    TurnContext,
    TurnState,
)
from microsoft_agents.hosting.core.rest_channel_service_client_factory import (
    RestChannelServiceClientFactory,
)
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from foundry_client import FoundryCorrelationContext, FoundryPromptAgentClient
from start_server import start_server
from telemetry import configure_telemetry

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("bot-service")

# Initialize environment/config/telemetry once at process startup.
load_dotenv()
configure_telemetry()
FOUNDRY_PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
FOUNDRY_AGENT_NAME = os.environ["FOUNDRY_AGENT_NAME"]
FOUNDRY_AGENT_ID = os.getenv("FOUNDRY_AGENT_ID", "").strip() or None
AGENTS_SDK_CONFIG = load_configuration_from_env(os.environ)
CONNECTION_MANAGER = MsalConnectionManager(**AGENTS_SDK_CONFIG)
BOT_AUTH_CONFIGURATION: AgentAuthConfiguration = CONNECTION_MANAGER.get_default_connection_configuration()
CHANNEL_SERVICE_CLIENT_FACTORY = RestChannelServiceClientFactory(connection_manager=CONNECTION_MANAGER)

TRACER = trace.get_tracer("bot-service")
TRACE_PROPAGATOR = TraceContextTextMapPropagator()

# FOUNDRY_AGENT_NAME is required; always initialize client by name.
FOUNDRY = FoundryPromptAgentClient(
    project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
    agent_name=FOUNDRY_AGENT_NAME,
    agent_id=FOUNDRY_AGENT_ID,
)

AGENT_APP = AgentApplication[TurnState](
    storage=MemoryStorage(),
    adapter=CloudAdapter(
        connection_manager=CONNECTION_MANAGER,
        channel_service_client_factory=CHANNEL_SERVICE_CLIENT_FACTORY,
    ),
)


async def _help(context: TurnContext, _: TurnState) -> None:
    await context.send_activity(
        "Hi. I am your Teams bridge to a Foundry prompt agent. "
        "Send me a question and I will forward it to Foundry."
    )


AGENT_APP.message("/help")(_help)


@AGENT_APP.activity("message")
async def on_message(context: TurnContext, _: TurnState) -> None:
    with TRACER.start_as_current_span("bot.handle_message") as span:
        # Record stable bot activity fields to make cross-service diagnostics easier.
        span.set_attribute("bot.channel_id", context.activity.channel_id or "")
        span.set_attribute("bot.activity_type", context.activity.type or "")
        span.set_attribute(
            "bot.conversation_id", (context.activity.conversation.id if context.activity.conversation else "")
        )
        span.set_attribute("bot.activity_id", context.activity.id or "")
        span.set_attribute("bot.from_id", context.activity.from_property.id if context.activity.from_property else "")
        span.set_attribute("bot.recipient_id", context.activity.recipient.id if context.activity.recipient else "")
        span.set_attribute("bot.activity_timestamp", str(context.activity.timestamp or ""))
        span.set_attribute("bot.service_url", context.activity.service_url or "")

        user_text = (context.activity.text or "").strip()
        if not user_text:
            await context.send_activity("Please send a non-empty message.")
            return

        try:
            with TRACER.start_as_current_span("foundry.ask"):
                correlation = _build_foundry_correlation_context(context)
                foundry_span = trace.get_current_span()
                foundry_span.set_attribute("foundry.request_id", correlation.request_id)
                foundry_span.set_attribute("foundry.traceparent", correlation.traceparent)
                foundry_span.set_attribute("bot.activity_id", correlation.bot_activity_id)
                foundry_span.set_attribute("bot.conversation_id", correlation.bot_conversation_id)
                # Run blocking SDK call in a worker thread so the event loop stays responsive.
                result = await asyncio.to_thread(
                    FOUNDRY.ask_with_correlation,
                    user_text,
                    correlation,
                )
            await context.send_activity(result.text)
        except Exception as ex:
            LOGGER.exception("Foundry call failed")
            span.record_exception(ex)
            await context.send_activity(
                "The Foundry backend call failed. Check App Insights logs for details. "
                f"Error: {ex}"
            )


def _build_foundry_correlation_context(context: TurnContext) -> FoundryCorrelationContext:
    headers: dict[str, str] = {}
    # Inject W3C trace context so Foundry receives the current trace lineage.
    TRACE_PROPAGATOR.inject(headers)

    conversation_id = context.activity.conversation.id if context.activity.conversation else ""
    activity_id = context.activity.id or ""
    user_id = context.activity.from_property.id if context.activity.from_property else ""

    # Prefer bot activity id for deterministic correlation; otherwise fall back to a UUID.
    request_id_suffix = activity_id or uuid.uuid4().hex
    request_id = f"bot-{request_id_suffix}"

    return FoundryCorrelationContext(
        traceparent=headers.get("traceparent", ""),
        request_id=request_id,
        bot_conversation_id=conversation_id,
        bot_activity_id=activity_id,
        user_id=user_id,
    )


if __name__ == "__main__":
    start_server(AGENT_APP, BOT_AUTH_CONFIGURATION)
