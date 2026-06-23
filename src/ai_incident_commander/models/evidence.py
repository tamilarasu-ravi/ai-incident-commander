"""Evidence models collected during incident investigation."""

from pydantic import BaseModel, Field


class CommitEvidence(BaseModel):
    """A Git commit relevant to the incident."""

    sha: str
    message: str
    author: str
    age_minutes: int
    url: str = ""


class LogClusterEvidence(BaseModel):
    """A cluster of error logs from the observability platform."""

    message: str
    count: int
    service: str
    status: str = "error"


class PriorIncidentEvidence(BaseModel):
    """A historical incident with a similar signature."""

    incident_id: str
    summary: str
    service: str
    resolved: bool = True


class DeploymentEvidence(BaseModel):
    """A deployment event near the incident window."""

    deployment_id: str
    environment: str
    service: str
    deployed_at_minutes_ago: int


class EvidenceBundle(BaseModel):
    """All evidence gathered for a single investigation."""

    commits: list[CommitEvidence] = Field(default_factory=list)
    log_clusters: list[LogClusterEvidence] = Field(default_factory=list)
    prior_incidents: list[PriorIncidentEvidence] = Field(default_factory=list)
    deployments: list[DeploymentEvidence] = Field(default_factory=list)

    def has_commit(self) -> bool:
        """Return True when at least one commit is present."""
        return len(self.commits) > 0

    def has_log_cluster(self) -> bool:
        """Return True when at least one log cluster is present."""
        return len(self.log_clusters) > 0

    def has_prior_incident_or_deployment(self) -> bool:
        """Return True when a prior incident or deployment is present."""
        return len(self.prior_incidents) > 0 or len(self.deployments) > 0
