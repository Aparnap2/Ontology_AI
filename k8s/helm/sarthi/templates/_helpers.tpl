{{/*
  OntologyAI Helm Chart - Helper Templates
  Common template functions for the umbrella chart
*/}}

{{/*
  Generate labels for all resources
*/}}
{{- define "ontology_ai.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: sarthi
{{- end }}

{{/*
  Common labels for service selector
*/}}
{{- define "ontology_ai.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
  Service labels with component
*/}}
{{- define "ontology_ai.componentLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .name }}
{{- end }}

{{/*
  Full image name with registry
*/}}
{{- define "ontology_ai.image" -}}
{{- $registry := .global.imageRegistry | default "ghcr.io/iterateswarm" -}}
{{- $image := .image -}}
{{- if not (hasPrefix "/" $image) -}}
{{- printf "%s/%s" $registry $image -}}
{{- else -}}
{{- $image -}}
{{- end -}}
{{- end }}

{{/*
  Generate OTel environment variables
*/}}
{{- define "ontology_ai.otelEnv" -}}
- name: OTEL_SERVICE_NAME
  value: {{ .serviceName | default .Chart.Name }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ .global.otel.endpoint | default "http://otel-collector:4317" }}
- name: OTEL_EXPORTER_OTLP_INSECURE
  value: "true"
- name: OTEL_EXPORTER_OTLP_COMPRESSION
  value: "none"
{{- end }}

{{/*
  Default resource limits (optimized for 16GB RAM constraint)
*/}}
{{- define "ontology_ai.defaultResources" -}}
limits:
  cpu: 500m
  memory: 512Mi
requests:
  cpu: 100m
  memory: 256Mi
{{- end }}

{{/*
  Default health check configuration
*/}}
{{- define "ontology_ai.defaultHealthCheck" -}}
livenessProbe:
  httpGet:
    path: {{ .path | default "/health" }}
    port: {{ .port }}
  initialDelaySeconds: {{ .initialDelaySeconds | default 10 }}
  periodSeconds: {{ .periodSeconds | default 30 }}
  timeoutSeconds: {{ .timeoutSeconds | default 5 }}
  failureThreshold: {{ .failureThreshold | default 3 }}
readinessProbe:
  httpGet:
    path: {{ .path | default "/health" }}
    port: {{ .port }}
  initialDelaySeconds: {{ .initialDelaySeconds | default 5 }}
  periodSeconds: {{ .periodSeconds | default 10 }}
  timeoutSeconds: {{ .timeoutSeconds | default 3 }}
  failureThreshold: {{ .failureThreshold | default 3 }}
{{- end }}