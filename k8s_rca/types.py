"""
Pydantic data models and schemas for Kubernetes Root-Cause Analysis.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IncidentClass(str, Enum):
    CRASHLOOP_BACKOFF = "CrashLoopBackOff"
    OOM_KILLED = "OOMKilled"
    FAILED_READINESS_PROBE = "FailedReadinessProbe"
    FAILED_LIVENESS_PROBE = "FailedLivenessProbe"
    IMAGE_PULL_FAILURE = "ImagePullFailure"
    FAILED_DEPLOYMENT = "FailedDeployment"
    RESOURCE_EXHAUSTION = "ResourceExhaustion"
    APPLICATION_ERROR_SPIKE = "ApplicationErrorSpike"
    UNKNOWN = "Unknown"


class EvidenceType(str, Enum):
    RESOURCE_STATE = "resource_state"
    POD_STATE = "pod_state"
    EVENT = "event"
    LOG = "log"
    METRIC = "metric"
    CONFIG = "config"
    CHANGE = "change"
    DEPENDENCY = "dependency"
    NETWORK = "network"
    TRACE = "trace"


class Span(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    service_name: str
    operation_name: str
    start_time_offset_ms: float = 0.0
    duration_ms: float
    status_code: int = 200
    error: bool = False
    error_message: Optional[str] = None
    tags: Dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    trace_id: str
    root_service: str
    root_operation: str
    total_duration_ms: float
    status_code: int = 200
    spans: List[Span] = Field(default_factory=list)
    has_error: bool = False
    error_summary: Optional[str] = None


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: f"inc-{int(datetime.utcnow().timestamp())}")
    title: str
    description: str
    namespace: str = "default"
    affected_service: Optional[str] = None
    symptom_class: IncidentClass = IncidentClass.UNKNOWN
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    id: str
    evidence_type: EvidenceType
    source_resource: str
    description: str
    raw_data: Optional[str] = None
    timestamp: Optional[datetime] = None
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    supports_hypotheses: List[str] = Field(default_factory=list)
    refutes_hypotheses: List[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str
    title: str
    description: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    refuting_evidence_ids: List[str] = Field(default_factory=list)
    reasoning: str = ""
    created_iteration: int = 0
    last_updated_iteration: int = 0


class CausalStep(BaseModel):
    step_order: int
    component: str
    phenomenon: str
    evidence_ids: List[str] = Field(default_factory=list)


class CausalChain(BaseModel):
    steps: List[CausalStep] = Field(default_factory=list)
    narrative: str = ""


class RCAReport(BaseModel):
    incident_id: str
    incident_title: str
    summary: str
    root_cause: str
    causal_chain: CausalChain
    primary_hypothesis: Hypothesis
    alternative_hypotheses: List[Hypothesis] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_rationale: str
    uncertainty_notes: Optional[str] = None
    recommended_actions: List[str] = Field(default_factory=list)
    investigation_timeline: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    is_error: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0


class InvestigationAction(BaseModel):
    thought: str
    tool_name: Optional[str] = None
    tool_arguments: Dict[str, Any] = Field(default_factory=dict)
    hypothesis_updates: List[Dict[str, Any]] = Field(default_factory=list)
    is_concluded: bool = False
    conclusion_rationale: Optional[str] = None
