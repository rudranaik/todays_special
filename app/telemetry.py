import phoenix as px
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

def setup_telemetry(app):
    # Start a Phoenix session
    session = px.launch_app()

    # Set up OpenTelemetry
    resource = Resource(attributes={
        "service.name": "pantry-suggest-api",
    })

    trace_provider = TracerProvider(resource=resource)
    # Set up an exporter to send traces to Phoenix
    exporter = OTLPSpanExporter(endpoint="http://127.0.0.1:6006/v1/traces")

    trace_provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace_api.set_tracer_provider(trace_provider)

    # Instrument the FastAPI app
    FastAPIInstrumentor().instrument_app(app)

    print("Phoenix is running on: ", session.url)
    return session
