// Package tracing provides OpenTelemetry tracing utilities.
package tracing

import (
	"context"
	"log"
	"os"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// Config holds tracing configuration.
type Config struct {
	ServiceName  string
	OTLPEndpoint string
	Enabled      bool
}

// NewConfig creates a new tracing config with defaults.
func NewConfig() *Config {
	return &Config{
		ServiceName:  "api-gateway",
		OTLPEndpoint: getDefaultEndpoint(),
		Enabled:      true,
	}
}

func getDefaultEndpoint() string {
	if endpoint := os.Getenv("OTEL_COLLECTOR_HOST"); endpoint != "" {
		return endpoint + ":4317"
	}
	return "localhost:4317"
}

// InitTracer initializes and returns a TracerProvider.
// Caller should call Shutdown() on the returned provider during cleanup.
func InitTracer(ctx context.Context, cfg *Config) (*sdktrace.TracerProvider, error) {
	if !cfg.Enabled {
		log.Println("Tracing disabled")
		return nil, nil
	}

	// Create OTLP exporter
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(cfg.OTLPEndpoint),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	// Create resource with service name
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(cfg.ServiceName),
		),
	)
	if err != nil {
		log.Printf("Warning: Failed to create resource: %v", err)
		res = nil
	}

	// Create TracerProvider with batch exporter
	opts := []sdktrace.TracerProviderOption{
		sdktrace.WithBatcher(exporter),
	}
	if res != nil {
		opts = append(opts, sdktrace.WithResource(res))
	}

	tp := sdktrace.NewTracerProvider(opts...)

	// Set global propagator (W3C Trace Context)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	log.Printf("Tracing initialized: service=%s endpoint=%s", cfg.ServiceName, cfg.OTLPEndpoint)
	return tp, nil
}
