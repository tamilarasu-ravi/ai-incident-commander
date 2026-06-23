"""Application-wide constants for incident handling and evaluation."""

INCIDENT_SLASH_COMMAND = "/incident"

EVIDENCE_COVERAGE_THRESHOLD = 0.6

CONFIDENCE_WEIGHT_EVIDENCE = 0.4
CONFIDENCE_WEIGHT_GROUNDING = 0.4
CONFIDENCE_WEIGHT_CONSISTENCY = 0.2

INCIDENT_USAGE_HINT = "/incident <service> <description>"

INVESTIGATION_ANNOUNCEMENT_TEMPLATE = (
    ":mag: Investigating *{service}* — {description}"
)

EVIDENCE_LOOKBACK_HOURS = 2
INTEGRATION_FETCH_TIMEOUT_SECONDS = 30
