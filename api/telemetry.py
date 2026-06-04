import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("telemetry")

# Global flag to check if telemetry is active
telemetry_active = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    
    telemetry_active = True
except ImportError:
    logger.warning("OpenTelemetry packages not installed. Telemetry is disabled.")
    telemetry_active = False

def setup_telemetry():
    """
    Initializes the OpenTelemetry TracerProvider and registers the OTLP exporter to Jaeger.
    """
    if not telemetry_active:
        return
    
    service_name = os.getenv("OTEL_SERVICE_NAME", "lesson-plan-architect")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    
    try:
        # Define Resource metadata
        resource = Resource.create(attributes={
            "service.name": service_name
        })
        
        # Initialize Tracer Provider
        provider = TracerProvider(resource=resource)
        
        # Configure OTLP Exporter (sending spans to Jaeger)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        
        # Register global Tracer Provider
        trace.set_tracer_provider(provider)
        print(f"OpenTelemetry successfully initialized. Service: {service_name}, Exporter: {otlp_endpoint}")
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {str(e)}")

def instrument_app(app):
    """
    Auto-instruments the FastAPI application requests.
    """
    if not telemetry_active:
        return
    
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        print("FastAPI application auto-instrumented with OpenTelemetry.")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI application: {str(e)}")

def instrument_celery():
    """
    Auto-instruments Celery task executions.
    """
    if not telemetry_active:
        return
    
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor().instrument()
        print("Celery background worker auto-instrumented with OpenTelemetry.")
    except Exception as e:
        logger.error(f"Failed to instrument Celery: {str(e)}")

def get_tracer(name: str):
    """
    Retrieves a tracer instance. Falls back to a dummy tracer if OTel is not initialized.
    """
    if telemetry_active:
        return trace.get_tracer(name)
    else:
        # Return a dummy tracer mock object
        class DummyTracer:
            def start_as_current_span(self, name, *args, **kwargs):
                from contextlib import nullcontext
                return nullcontext()
        return DummyTracer()
