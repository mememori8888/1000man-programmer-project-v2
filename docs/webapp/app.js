const GITHUB_OWNER = "mememori8888";
const GITHUB_REPO = "1000man-programmer-project-v2";

const commandMap = {
  facility: "/run-facility",
  reviews: "/run-reviews",
  reviews_sequential: "/run-reviews-sequential",
  reviews_recent_relevance: "/run-reviews-relevance",
};

const workflowNames = {
  facility: "Facility Job",
  reviews: "Reviews Job",
  reviews_sequential: "Reviews Sequential Job",
  reviews_recent_relevance: "Reviews Relevance Job",
};

const form = document.getElementById("jobForm");
const preview = document.getElementById("preview");
const workflow = document.getElementById("workflow");
const copyButton = document.getElementById("copyButton");

function fieldValue(id) {
  return document.getElementById(id).value.trim();
}

function buildParams() {
  const selected = workflow.value;
  if (selected === "facility") {
    return {
      workflow: selected,
      csv_file: "settings/address.csv",
      custom_settings: {
        query: "歯科医院",
        address_csv_path: "settings/address.csv",
      },
    };
  }

  const params = {
    workflow: selected,
    csv_file: fieldValue("csvFile"),
    output_file: fieldValue("outputFile"),
    days_back: fieldValue("daysBack"),
    start_from_batch: "1",
    rows_per_batch: fieldValue("rowsPerBatch"),
    max_parallel_jobs: fieldValue("maxParallelJobs"),
    batch_wait: "120",
    api_batch_size: fieldValue("apiBatchSize"),
    max_wait_minutes: "90",
    dataset_id: fieldValue("datasetId"),
    skip_column: fieldValue("skipColumn"),
    generate_report: true,
  };

  if (selected === "reviews_recent_relevance") {
    params.relevance_rank_limit = fieldValue("relevanceRankLimit");
    params.serp_max_workers = fieldValue("serpMaxWorkers");
    params.serp_zone_name = fieldValue("serpZoneName");
    params.summary_file = fieldValue("summaryFile");
  }

  if (selected === "reviews") {
    return {
      workflow: selected,
      config_file: "settings/settings.json",
      fid_file: "results/fid.csv",
      process_count: "100",
      workers: "10",
      custom_settings: {
        review_file: fieldValue("outputFile"),
      },
    };
  }

  return params;
}

function buildIssueBody() {
  const selected = workflow.value;
  const params = buildParams();
  return `${commandMap[selected]}

## Job parameters

\`\`\`json
${JSON.stringify(params, null, 2)}
\`\`\`

## Execution policy

この Issue は v2 の ELT IssueOps により検証されます。
管理者が \`/承認\` とコメントすると、raw payload を GCS/BigQuery ELT 境界へ送る準備ジョブが実行されます。
`;
}

function refreshPreview() {
  preview.textContent = buildIssueBody();
  document.body.dataset.workflow = workflow.value;
}

function openIssue() {
  const selected = workflow.value;
  const title = `[${workflowNames[selected]}] ${new Date().toISOString().slice(0, 10)}`;
  const params = new URLSearchParams({
    title,
    body: buildIssueBody(),
  });
  window.open(`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/issues/new?${params}`, "_blank");
}

form.addEventListener("input", refreshPreview);
form.addEventListener("submit", (event) => {
  event.preventDefault();
  openIssue();
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(buildIssueBody());
});

refreshPreview();
