from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable
from typing import Optional

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


@dataclass(frozen=True)
class FoundryCorrelationContext:
    # Correlation fields propagated from bot turn context into Foundry calls.
    traceparent: str
    request_id: str
    bot_conversation_id: str
    bot_activity_id: str
    user_id: str


@dataclass
class FoundryResult:
    # Normalized response shape returned to the bot handler.
    text: str
    conversation_id: str
    response_id: str
    response_status: str
    agent_name: str


class FoundryPromptAgentClient:
    def __init__(
        self,
        project_endpoint: str,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        if not agent_name and not agent_id:
            raise ValueError("Either agent_name or agent_id must be provided")

        # DefaultAzureCredential enables local/dev and managed identity auth paths.
        self._credential = DefaultAzureCredential()
        self._project = AIProjectClient(
            endpoint=project_endpoint,
            credential=self._credential,
            allow_preview=True,
        )
        self._openai = self._project.get_openai_client()
        self._conversation_id: Optional[str] = None
        # Runtime calls target prompt agents by name.
        self._agent_name = agent_name or self._resolve_agent_name_from_id(agent_id or "")

    def ask(self, user_text: str) -> FoundryResult:
        return self.ask_with_correlation(user_text)

    def ask_with_correlation(
        self,
        user_text: str,
        correlation: Optional[FoundryCorrelationContext] = None,
    ) -> FoundryResult:
        # Include optional cross-service headers/metadata for diagnostics joins.
        extra_headers = None
        metadata = None
        user = None
        if correlation is not None:
            extra_headers = {
                "traceparent": correlation.traceparent,
                "x-ms-client-request-id": correlation.request_id,
                "x-ms-correlation-request-id": correlation.request_id,
            }
            metadata = {
                "bot_conversation_id": correlation.bot_conversation_id,
                "bot_activity_id": correlation.bot_activity_id,
                "app_request_id": correlation.request_id,
            }
            user = normalize_foundry_user_id(correlation.user_id)

        if not self._conversation_id:
            # Keep one Foundry conversation per app process for continuity.
            conversation = self._openai.conversations.create(
                extra_headers=extra_headers,
                metadata=metadata,
            )
            self._conversation_id = str(conversation.id)

        response = self._openai.responses.create(
            conversation=self._conversation_id,
            input=user_text,
            user=user,
            extra_headers=extra_headers,
            metadata=metadata,
            extra_body={
                "agent_reference": {
                    "type": "agent_reference",
                    "name": self._agent_name,
                }
            },
        )

        response_status = str(getattr(response, "status", "completed"))
        response_id = str(getattr(response, "id", ""))
        if response_status != "completed":
            # Return status detail to caller instead of raising for non-completed outcomes.
            error_text = f"Foundry response ended with status '{response_status}'."
            return FoundryResult(
                text=error_text,
                conversation_id=self._conversation_id,
                response_id=response_id,
                response_status=response_status,
                agent_name=self._agent_name,
            )

        response_text = getattr(response, "output_text", "") or ""
        if not response_text:
            response_text = "The Foundry agent completed but returned no text output."

        return FoundryResult(
            text=response_text,
            conversation_id=self._conversation_id,
            response_id=response_id,
            response_status=response_status,
            agent_name=self._agent_name,
        )

    def close(self) -> None:
        self._project.close()
        self._credential.close()

    def _resolve_agent_name_from_id(self, agent_id: str) -> str:
        for agent in self._list_agents():
            if str(getattr(agent, "id", "")).lower() != agent_id.lower():
                continue
            found_name = str(getattr(agent, "name", "")).strip()
            if found_name:
                return found_name
            break

        raise ValueError(f"Unable to resolve Foundry agent name from id: {agent_id}")

    def _list_agents(self) -> Iterable[object]:
        return self._project.agents.list()


def normalize_foundry_user_id(raw_user_id: str) -> str:
    # Foundry user field has a length limit; hash long ids to keep correlation stable.
    user_id = (raw_user_id or "").strip()
    if not user_id:
        return "anonymous"

    if len(user_id) <= 64:
        return user_id

    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    return f"u-{digest}"
