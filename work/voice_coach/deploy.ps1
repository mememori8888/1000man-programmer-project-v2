param([ValidateSet('Prepare','Deploy','EnableSchedule')][string]$Stage = 'Prepare')
$ErrorActionPreference = 'Stop'
$projectId = 'eng-empire-498517-c6'
$region = 'asia-northeast1'
$bucketName = "$projectId-voice-coach"
$runner = "voice-coach-runner@$projectId.iam.gserviceaccount.com"
$scheduler = "voice-coach-scheduler@$projectId.iam.gserviceaccount.com"
function Invoke-Gcloud {
    & gcloud @args
    if ($LASTEXITCODE -ne 0) { throw 'gcloud command failed; stopping.' }
}
Set-Location -LiteralPath $PSScriptRoot
if ($Stage -eq 'Prepare') {
    Invoke-Gcloud services enable aiplatform.googleapis.com run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com drive.googleapis.com calendar-json.googleapis.com tasks.googleapis.com --project=$projectId
    foreach ($account in @('voice-coach-runner','voice-coach-scheduler')) {
        & gcloud iam service-accounts describe "$account@$projectId.iam.gserviceaccount.com" --project=$projectId 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { Invoke-Gcloud iam service-accounts create $account --project=$projectId }
    }
    & gcloud storage buckets describe "gs://$bucketName" --project=$projectId 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Gcloud storage buckets create "gs://$bucketName" --project=$projectId --location=$region --uniform-bucket-level-access --public-access-prevention
    }
    Invoke-Gcloud storage buckets add-iam-policy-binding "gs://$bucketName" --member="serviceAccount:$runner" --role=roles/storage.objectUser
    Invoke-Gcloud projects add-iam-policy-binding $projectId --member="serviceAccount:$runner" --role=roles/aiplatform.user --condition=None --quiet
    Write-Host 'Preparation complete. Run setup_oauth.py next.'
}
if ($Stage -eq 'Deploy') {
    Invoke-Gcloud secrets add-iam-policy-binding voice-coach-oauth --project=$projectId --member="serviceAccount:$runner" --role=roles/secretmanager.secretAccessor
    # Source deployment builds the Dockerfile; Scheduler stays absent until the live test passes.
    $jobs = @(
        @{ Name = 'voice-coach-daily'; Args = '--voice-and-finance'; Memory = '2Gi' },
        @{ Name = 'voice-coach-finance'; Args = '--finance'; Memory = '2Gi' },
        @{ Name = 'voice-coach-daily-focus'; Args = '--daily-focus' },
        @{ Name = 'voice-coach-weekly-focus'; Args = '--weekly-focus' },
        @{ Name = 'voice-coach-monthly-focus'; Args = '--monthly-focus' }
    )
    foreach ($job in $jobs) {
        $memory = if ($job.Memory) { $job.Memory } else { '1Gi' }
        Invoke-Gcloud run jobs deploy $job.Name --source=. --project=$projectId --region=$region --service-account=$runner --tasks=1 --parallelism=1 --cpu=1 --memory=$memory --task-timeout=3600s --max-retries=1 --set-env-vars "GOOGLE_CLOUD_PROJECT=$projectId,STATE_BUCKET=$bucketName" --args=$($job.Args) --quiet
        Invoke-Gcloud run jobs add-iam-policy-binding $job.Name --project=$projectId --region=$region --member="serviceAccount:$scheduler" --role=roles/run.invoker
    }
    Write-Host 'Deployed without schedule. Run a read check, then one live execution before enabling schedule.'
}
function Upsert-SchedulerJob([string]$Name, [string]$RunJob, [string]$Schedule) {
    $triggerUri = "https://run.googleapis.com/v2/projects/$projectId/locations/$region/jobs/$RunJob`:run"
    & gcloud scheduler jobs describe $Name --project=$projectId --location=$region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $verb = 'update' } else { $verb = 'create' }
    Invoke-Gcloud scheduler jobs $verb http $Name --project=$projectId --location=$region --schedule=$Schedule --time-zone=Asia/Tokyo --uri=$triggerUri --http-method=POST --oauth-service-account-email=$scheduler --message-body='{}'
}
if ($Stage -eq 'EnableSchedule') {
    # The upload-day window closes at 05:00 JST. Run after it closes so the
    # closing day's transcript and coaching are complete before focus planning.
    Upsert-SchedulerJob 'voice-coach-0600' 'voice-coach-daily' '10 5 * * *'
    Upsert-SchedulerJob 'voice-coach-monthly-focus-0620' 'voice-coach-monthly-focus' '20 6 1 * *'
    Upsert-SchedulerJob 'voice-coach-focus-0640' 'voice-coach-daily-focus' '40 6 * * *'
    Upsert-SchedulerJob 'voice-coach-weekly-focus-friday' 'voice-coach-weekly-focus' '10 7 * * 5'
}
