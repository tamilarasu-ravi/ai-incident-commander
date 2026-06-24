"""PostgreSQL-backed investigation store."""

import asyncio

import structlog

from ai_incident_commander.db import repository
from ai_incident_commander.db.session import dispose_database_runtime, session_scope
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.store.types import StoredInvestigation

logger = structlog.get_logger(__name__)


class PostgresInvestigationStore:
    """Persist investigations in PostgreSQL for long-lived approval workflows."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def _execute(self, coroutine):
        """Run a coroutine and always dispose DB resources before the loop closes."""
        try:
            return await coroutine
        finally:
            await dispose_database_runtime()

    def _run(self, coroutine):
        """
        Execute async repository code from synchronous Slack handlers.

        Each call uses a fresh event loop and disposes the shared async engine
        afterward so asyncpg connections are not bound to a closed loop.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._execute(coroutine))
        raise RuntimeError("PostgresInvestigationStore cannot be used inside a running event loop")

    def save(
        self,
        investigation_id: str,
        state: InvestigationState,
        channel_id: str,
        message_ts: str,
    ) -> StoredInvestigation:
        """
        Persist a surfaced investigation for later Block Kit actions.

        Args:
            investigation_id: Unique investigation identifier.
            state: Final investigation state from the graph.
            channel_id: Slack channel containing the RCA card.
            message_ts: Slack message timestamp for updates.

        Returns:
            Stored investigation record.
        """
        async def _save() -> StoredInvestigation:
            async with session_scope(self._database_url) as session:
                return await repository.upsert_investigation(
                    session,
                    investigation_id,
                    state,
                    channel_id,
                    message_ts,
                )

        record = self._run(_save())
        logger.info(
            "investigation_persisted_postgres",
            investigation_id=investigation_id,
        )
        return record

    def get(self, investigation_id: str) -> StoredInvestigation | None:
        """
        Load a stored investigation by ID.

        Args:
            investigation_id: Unique investigation identifier.

        Returns:
            Stored record when present, otherwise ``None``.
        """
        async def _get() -> StoredInvestigation | None:
            async with session_scope(self._database_url) as session:
                return await repository.get_investigation(session, investigation_id)

        return self._run(_get())

    def update_message_ts(self, investigation_id: str, message_ts: str) -> StoredInvestigation | None:
        """
        Attach the Slack message timestamp after the RCA card is posted.

        Args:
            investigation_id: Unique investigation identifier.
            message_ts: Slack message timestamp for card updates.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        async def _update() -> StoredInvestigation | None:
            async with session_scope(self._database_url) as session:
                return await repository.update_message_ts(
                    session,
                    investigation_id,
                    message_ts,
                )

        return self._run(_update())

    def mark_approved(
        self,
        investigation_id: str,
        jira_issue_key: str,
        actor_slack_id: str = "",
    ) -> StoredInvestigation | None:
        """
        Mark an investigation as approved and record the created Jira issue.

        Args:
            investigation_id: Unique investigation identifier.
            jira_issue_key: Created Jira issue key such as ``SCRUM-42``.
            actor_slack_id: Slack user ID that approved the RCA.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        async def _approve() -> StoredInvestigation | None:
            async with session_scope(self._database_url) as session:
                return await repository.mark_approved(
                    session,
                    investigation_id,
                    jira_issue_key,
                    actor_slack_id=actor_slack_id,
                )

        return self._run(_approve())

    def mark_rejected(
        self,
        investigation_id: str,
        actor_slack_id: str = "",
    ) -> StoredInvestigation | None:
        """
        Mark an investigation as rejected.

        Args:
            investigation_id: Unique investigation identifier.
            actor_slack_id: Slack user ID that rejected the RCA.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        async def _reject() -> StoredInvestigation | None:
            async with session_scope(self._database_url) as session:
                return await repository.mark_rejected(
                    session,
                    investigation_id,
                    actor_slack_id=actor_slack_id,
                )

        return self._run(_reject())

    def count(self) -> int:
        """Return the number of investigations currently stored."""
        async def _count() -> int:
            async with session_scope(self._database_url) as session:
                return await repository.count_investigations(session)

        return self._run(_count())

    def list_ids(self) -> list[str]:
        """Return stored investigation IDs (for debugging store misses)."""
        async def _list_ids() -> list[str]:
            async with session_scope(self._database_url) as session:
                return await repository.list_investigation_ids(session)

        return self._run(_list_ids())

    def clear(self) -> None:
        """Remove all stored investigations (used in tests)."""
        async def _clear() -> None:
            async with session_scope(self._database_url) as session:
                await repository.clear_investigations(session)

        self._run(_clear())
