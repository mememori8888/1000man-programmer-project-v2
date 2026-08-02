const GITHUB_OWNER = "mememori8888";
const GITHUB_REPO = "1000man-programmer-project-v2";
const FILE_PRESETS_URL = "file-presets.json";

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
const csvPathError = "Use a .csv path under settings/ or results/.";
let filePresets = { settings: [], results: [] };

function fieldValue(id) {
  return document.getElementById(id).value.trim();
}

function csvPathOrDefault(id, fallback) {
  return fieldValue(id) || fallback;
}

function validateCsvPath(path) {
  const normalized = path.replaceAll("\\", "/").trim();
  const parts = normalized.split("/");
  return (
    normalized.endsWith(".csv") &&
    !normalized.startsWith("/") &&
    (parts[0] === "settings" || parts[0] === "results") &&
    parts.every((part) => part && part !== "." && part !== "..")
  );
}

function validateCsvField(id, fallback) {
  const input = document.getElementById(id);
  const path = csvPathOrDefault(id, fallback);
  input.setCustomValidity(validateCsvPath(path) ? "" : csvPathError);
  return input.validationMessage === "";
}

function clearCsvValidity() {
  ["csvFile", "outputFile", "fidFile", "summaryFile"].forEach((id) => {
    document.getElementById(id).setCustomValidity("");
  });
}

function validateCurrentForm() {
  const selected = workflow.value;
  const checks = [];
  clearCsvValidity();

  if (selected === "reviews") {
    checks.push(validateCsvField("fidFile", "results/fid.csv"));
    checks.push(validateCsvField("outputFile", "results/dental_reviews.csv"));
  }

  if (selected === "reviews_sequential" || selected === "reviews_recent_relevance") {
    checks.push(validateCsvField("csvFile", "results/dental_new.csv"));
    checks.push(validateCsvField("outputFile", "results/dental_reviews.csv"));
  }

  if (selected === "reviews_recent_relevance") {
    checks.push(validateCsvField("summaryFile", "results/relevance_rank_summary.csv"));
  }

  return checks.every(Boolean);
}

function hasPurpose(entry, purpose) {
  return Array.isArray(entry.purposes) && entry.purposes.includes(purpose);
}

function pathsForPurpose(group, purpose) {
  return (filePresets[group] || [])
    .filter((entry) => hasPurpose(entry, purpose))
    .map((entry) => entry.path)
    .filter(Boolean);
}

function uniquePaths(paths) {
  return [...new Set(paths)].sort((left, right) => left.localeCompare(right, "ja"));
}

function populateDatalist(id, paths) {
  const datalist = document.getElementById(id);
  if (!datalist) return;

  datalist.replaceChildren(
    ...uniquePaths(paths).map((path) => {
      const option = document.createElement("option");
      option.value = path;
      return option;
    }),
  );
}

async function loadFilePresets() {
  try {
    const response = await fetch(FILE_PRESETS_URL, { cache: "no-store" });
    if (!response.ok) return;

    const presets = await response.json();
    filePresets = {
      settings: Array.isArray(presets.settings) ? presets.settings : [],
      results: Array.isArray(presets.results) ? presets.results : [],
    };

    populateDatalist("sequentialInputFiles", [
      "results/dental_new.csv",
      ...pathsForPurpose("results", "sequential_input"),
      ...pathsForPurpose("results", "facility_output"),
    ]);
    populateDatalist("fidInputFiles", [
      "results/fid.csv",
      ...pathsForPurpose("results", "fid_input"),
    ]);
    populateDatalist("reviewOutputFiles", [
      "results/dental_reviews.csv",
      "results/dental_review.csv",
      ...pathsForPurpose("results", "review_output"),
    ]);
    populateDatalist("summaryOutputFiles", [
      "results/relevance_rank_summary.csv",
      ...pathsForPurpose("results", "relevance_summary_output"),
    ]);
  } catch (error) {
    console.warn("file presets could not be loaded", error);
  }
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
    csv_file: csvPathOrDefault("csvFile", "results/dental_new.csv"),
    output_file: csvPathOrDefault("outputFile", "results/dental_reviews.csv"),
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
      fid_file: csvPathOrDefault("fidFile", "results/fid.csv"),
      start_line: fieldValue("startLine"),
      process_count: fieldValue("processCount"),
      workers: fieldValue("workers"),
      custom_settings: {
        review_file: csvPathOrDefault("outputFile", "results/dental_reviews.csv"),
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
管理者が \`/承認\` とコメントすると、BrightData extract、raw保存、BigQuery load/transform が実行されます。
`;
}

function refreshPreview() {
  preview.textContent = buildIssueBody();
  document.body.dataset.workflow = workflow.value;
}

function openIssue() {
  const selected = workflow.value;
  if (!validateCurrentForm()) {
    form.reportValidity();
    return;
  }
  const title = `[${workflowNames[selected]}] ${new Date().toISOString().slice(0, 10)}`;
  const queryParams = new URLSearchParams({
    title,
    body: buildIssueBody(),
  });
  window.open(`https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/issues/new?${queryParams}`, "_blank");
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
loadFilePresets();
