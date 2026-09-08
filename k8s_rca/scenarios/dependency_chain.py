"""
Multi-tier microservice dependency failure scenario (Scenario 3 from specification).
Frontend -> Order API -> Payment Service -> Database Lock.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class DependencyChainScenario(BenchmarkScenario):
    """
    Scenario matching specification Scenario 3:
    Frontend -> Order API -> Payment Service -> Database unavailable / locked
    Demonstrates multi-source distributed tracing, span waterfalls, and dependency correlation.
    """

    def __init__(self):
        super().__init__(
            id="sc-08-dependency-chain",
            name="Multi-Tier Service Dependency Failure",
            incident_class=IncidentClass.APPLICATION_ERROR_SPIKE,
            description="Frontend and Order API experiencing sudden spike in 504 Gateway Timeouts following downstream database lock in Payment Service.",
            ground_truth_root_cause="PostgreSQL row lock contention and database query timeout in payment-service causing cascading 504 Gateway Timeouts upstream to order-api and frontend.",
            expected_keywords=["payment", "database", "timeout", "lock", "dependency", "504"],
            incident=Incident(
                id="inc-dep-chain-504",
                title="Frontend experiencing sudden spike in 504 Gateway Timeouts",
                description="Frontend checkout traffic failing with 504 Gateway Timeouts across prod microservices cluster.",
                namespace="prod",
                affected_service="frontend",
                symptom_class=IncidentClass.APPLICATION_ERROR_SPIKE,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="microservices-prod-cluster")
        ns = "prod"

        # 1. Kubernetes Workloads
        for svc in ["frontend", "order-api", "payment-service", "postgres-payment-db"]:
            sim.add_resource("Deployment", svc, ns, {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": svc, "namespace": ns, "labels": {"app": svc}},
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {"containers": [{"name": svc, "image": f"registry.internal/{svc}:v2.1.0"}]}
                    }
                },
                "status": {"replicas": 2, "readyReplicas": 2},
            })

            sim.add_resource("Pod", f"{svc}-pod-1", ns, {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": f"{svc}-pod-1", "namespace": ns, "labels": {"app": svc}},
                "spec": {"containers": [{"name": svc}]},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{"name": svc, "ready": True, "restartCount": 0}],
                }
            })

        # 2. Application Logs across services
        sim.add_logs("frontend-pod-1", ns, (
            "2026-09-08T14:20:01Z INFO  [HTTP] GET /healthz 200 OK\n"
            "2026-09-08T14:20:10Z ERROR [HTTP] POST /checkout -> upstream order-api:8080 returned HTTP 504 Gateway Timeout (elapsed: 5012ms)\n"
            "2026-09-08T14:20:12Z ERROR [HTTP] POST /checkout -> upstream order-api:8080 returned HTTP 504 Gateway Timeout (elapsed: 5008ms)\n"
            "2026-09-08T14:20:15Z WARN  [CircuitBreaker] order-api circuit breaker half-open due to consecutive 504 timeouts\n"
        ))

        sim.add_logs("order-api-pod-1", ns, (
            "2026-09-08T14:20:00Z INFO  [OrderService] Received order req_id=ord-8831 for user=usr-9102\n"
            "2026-09-08T14:20:05Z ERROR [OrderService] Call to downstream payment-service:8082 timed out after 4800ms: java.net.SocketTimeoutException: Read timed out\n"
            "2026-09-08T14:20:11Z ERROR [OrderService] Aborting order transaction: downstream payment-service unresponsive\n"
        ))

        sim.add_logs("payment-service-pod-1", ns, (
            "2026-09-08T14:19:55Z INFO  [PaymentProcessor] Processing debit transaction txn_id=tx-4401\n"
            "2026-09-08T14:20:03Z ERROR [Database] LockWaitTimeoutException: Lock wait timeout exceeded (4000ms) on postgres-payment-db.prod.svc:5432 query: SELECT balance FROM accounts WHERE id = 1044 FOR UPDATE\n"
            "2026-09-08T14:20:04Z ERROR [PaymentProcessor] Database transaction failed: could not obtain row exclusive lock on account ledger\n"
            "2026-09-08T14:20:08Z ERROR [Database] Pool acquisition timeout: all 30 pool connections blocked waiting for transaction lock\n"
        ))

        # 3. Distributed Traces (Jaeger / OpenTelemetry spans)
        sim.add_trace(
            trace_id="tr-checkout-8831",
            root_service="frontend",
            root_operation="POST /checkout",
            total_duration_ms=5012.0,
            status_code=504,
            has_error=True,
            error_summary="504 Gateway Timeout due to downstream payment-service database lock timeout",
            spans=[
                {
                    "span_id": "span-front-01",
                    "trace_id": "tr-checkout-8831",
                    "parent_span_id": None,
                    "service_name": "frontend",
                    "operation_name": "HTTP POST /checkout",
                    "duration_ms": 5012.0,
                    "status_code": 504,
                    "error": True,
                },
                {
                    "span_id": "span-order-02",
                    "trace_id": "tr-checkout-8831",
                    "parent_span_id": "span-front-01",
                    "service_name": "order-api",
                    "operation_name": "POST /api/v1/orders",
                    "duration_ms": 4850.0,
                    "status_code": 504,
                    "error": True,
                },
                {
                    "span_id": "span-payment-03",
                    "trace_id": "tr-checkout-8831",
                    "parent_span_id": "span-order-02",
                    "service_name": "payment-service",
                    "operation_name": "POST /api/v1/payments/charge",
                    "duration_ms": 4600.0,
                    "status_code": 500,
                    "error": True,
                    "error_message": "LockWaitTimeout: could not obtain row exclusive lock on accounts table",
                },
                {
                    "span_id": "span-db-04",
                    "trace_id": "tr-checkout-8831",
                    "parent_span_id": "span-payment-03",
                    "service_name": "payment-service",
                    "operation_name": "SQL SELECT FOR UPDATE accounts",
                    "duration_ms": 4050.0,
                    "status_code": 500,
                    "error": True,
                    "error_message": "PostgreSQL lock timeout exceeded",
                },
            ],
        )

        sim.add_trace(
            trace_id="tr-checkout-8832",
            root_service="frontend",
            root_operation="POST /checkout",
            total_duration_ms=5008.0,
            status_code=504,
            has_error=True,
            error_summary="504 Gateway Timeout downstream row lock",
            spans=[
                {
                    "span_id": "span-front-11",
                    "trace_id": "tr-checkout-8832",
                    "parent_span_id": None,
                    "service_name": "frontend",
                    "operation_name": "HTTP POST /checkout",
                    "duration_ms": 5008.0,
                    "status_code": 504,
                    "error": True,
                },
                {
                    "span_id": "span-order-12",
                    "trace_id": "tr-checkout-8832",
                    "parent_span_id": "span-front-11",
                    "service_name": "order-api",
                    "operation_name": "POST /api/v1/orders",
                    "duration_ms": 4820.0,
                    "status_code": 504,
                    "error": True,
                },
                {
                    "span_id": "span-payment-13",
                    "trace_id": "tr-checkout-8832",
                    "parent_span_id": "span-order-12",
                    "service_name": "payment-service",
                    "operation_name": "POST /api/v1/payments/charge",
                    "duration_ms": 4580.0,
                    "status_code": 500,
                    "error": True,
                },
            ],
        )

        # 4. Metrics
        sim.add_metrics("deployment", "frontend", ns, {
            "http_5xx_rate": 0.42,
            "latency_p99_ms": 5120.0,
            "request_rate_rps": 120.0,
        })
        sim.add_metrics("deployment", "order-api", ns, {
            "http_5xx_rate": 0.45,
            "latency_p99_ms": 4900.0,
            "request_rate_rps": 115.0,
        })
        sim.add_metrics("deployment", "payment-service", ns, {
            "http_5xx_rate": 0.98,
            "latency_p99_ms": 4650.0,
            "db_connection_pool_active": 30,
            "db_connection_pool_max": 30,
            "db_lock_contention_waiting": 28,
        })

        # 5. Events
        sim.add_event(
            reason="Unhealthy",
            message="Readiness probe failed: HTTP 504 Gateway Timeout connecting to order-api",
            involved_kind="Pod",
            involved_name="frontend-pod-1",
            namespace=ns,
            event_type="Warning",
            count=12,
        )

        return sim
