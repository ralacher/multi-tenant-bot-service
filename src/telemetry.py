from __future__ import annotations

import logging
import os

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

LOGGER = logging.getLogger("bot-service.telemetry")

# These SDK loggers are very chatty at INFO and can drown out app-level diagnostics.
NOISY_SDK_LOGGERS = (
    "azure.monitor.opentelemetry.exporter",
    "azure.monitor.opentelemetry.exporter.export._base",
    "azure.core.pipeline.policies.http_logging_policy"
)


def _connection_string_from_env() -> str | None:
    # Prefer full connection string, then fallback to instrumentation key.
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if conn:
        return conn

    ikey = os.getenv("APPINSIGHTS_INSTRUMENTATIONKEY", "").strip()
    if ikey:
        return f"InstrumentationKey={ikey}"

    return None


def configure_telemetry() -> None:
    # Telemetry is optional; app can run without App Insights configured.
    connection_string = _connection_string_from_env()
    if not connection_string:
        LOGGER.info("Application Insights is not configured. Skipping telemetry setup.")
        return

    configure_azure_monitor(connection_string=connection_string)
    # Enrich stdlib logging records with trace context.
    LoggingInstrumentor().instrument(set_logging_format=True)

    for logger_name in NOISY_SDK_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    LOGGER.info("Application Insights telemetry is enabled.")
