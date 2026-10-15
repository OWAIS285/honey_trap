param(
    [Parameter(Mandatory)][string]$ProjectId,
    [string]$Region = "asia-south1"
)

gcloud config set project $ProjectId

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
    aiplatform.googleapis.com firestore.googleapis.com secretmanager.googleapis.com `
    firebase.googleapis.com logging.googleapis.com monitoring.googleapis.com

$sa = "stallwart-run"
$member = "serviceAccount:$sa@$ProjectId.iam.gserviceaccount.com"
gcloud iam service-accounts create $sa --display-name "Stallwart Cloud Run"
foreach ($role in "roles/aiplatform.user", "roles/datastore.user", "roles/logging.logWriter") {
    gcloud projects add-iam-policy-binding $ProjectId --member $member --role $role --condition=None | Out-Null
}

gcloud firestore databases create --location=$Region
