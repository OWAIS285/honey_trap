param(
    [string]$ProjectId = "honeytrap-aibc-2026",
    [string]$Region = "asia-south1"
)

$bucket = "$ProjectId-recordings"
$sa = "serviceAccount:honeytrap-run@$ProjectId.iam.gserviceaccount.com"

# Private bucket for call recordings; objects are deleted automatically after 14 days.
gcloud storage buckets create "gs://$bucket" --project $ProjectId --location $Region `
    --uniform-bucket-level-access --public-access-prevention
$lifecycle = Join-Path $env:TEMP "lifecycle.json"
'{"rule":[{"action":{"type":"Delete"},"condition":{"age":14}}]}' | Set-Content $lifecycle -Encoding ascii
gcloud storage buckets update "gs://$bucket" --lifecycle-file=$lifecycle --project $ProjectId
gcloud storage buckets add-iam-policy-binding "gs://$bucket" --member $sa --role roles/storage.objectAdmin --project $ProjectId

# Firestore documents carry an expiresAt timestamp; TTL policies purge them automatically.
foreach ($group in "calls", "turns", "details", "strains", "drills") {
    gcloud firestore fields ttls update expiresAt --collection-group=$group --enable-ttl --project $ProjectId --async
}
