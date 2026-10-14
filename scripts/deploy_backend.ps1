param(
    [Parameter(Mandatory)][string]$ProjectId,
    [string]$Region = "asia-south1",
    [string]$LiveLocation = "us-central1",
    [string]$TextLocation = "global",
    [string]$AllowedOrigins = ""
)

$envVars = "^|^GOOGLE_GENAI_USE_VERTEXAI=true|GOOGLE_CLOUD_PROJECT=$ProjectId|LIVE_LOCATION=$LiveLocation|TEXT_LOCATION=$TextLocation|ALLOWED_ORIGINS=$AllowedOrigins"

gcloud run deploy honeytrap-api `
    --project $ProjectId `
    --region $Region `
    --source backend `
    --service-account "honeytrap-run@$ProjectId.iam.gserviceaccount.com" `
    --allow-unauthenticated `
    --max-instances 3 `
    --timeout 900 `
    --session-affinity `
    --set-env-vars $envVars `
    --quiet
