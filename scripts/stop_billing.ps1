param(
    [string]$ProjectId = (gcloud config get-value project 2>$null)
)

# Emergency stop: Cloud Run, Firestore and Vertex AI calls stop working until billing is re-linked.
gcloud billing projects unlink $ProjectId

# To resume: gcloud billing projects link $ProjectId --billing-account=<BILLING_ACCOUNT_ID>
