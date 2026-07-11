import json
import os
import sys
import glob
import argparse
from datetime import datetime
from collections import Counter, defaultdict
from flask import Flask, render_template_string, request

app = Flask(__name__)

LOG_DATA = []
STATS = {}
TIMELINE = []
CATEGORY_COUNTS = Counter()
ERRORS = []
DAILY_COUNTS = Counter()
TOTAL_FILES = 0
SUCCESS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Renamer Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
h1 { font-size: 1.8rem; margin-bottom: 8px; }
.subtitle { color: #94a3b8; margin-bottom: 24px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
.stat-card { background: #1e293b; border-radius: 10px; padding: 20px; text-align: center; }
.stat-card .value { font-size: 2rem; font-weight: 700; }
.stat-card .label { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }
.stat-card.success .value { color: #22c55e; }
.stat-card.fail .value { color: #ef4444; }
.stat-card.skip .value { color: #f59e0b; }
.stat-card.total .value { color: #3b82f6; }
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
@media (max-width: 768px) { .charts-row { grid-template-columns: 1fr; } }
.chart-card { background: #1e293b; border-radius: 10px; padding: 20px; }
.chart-card h3 { margin-bottom: 12px; font-size: 1rem; color: #94a3b8; }
.chart-card canvas { max-height: 300px; }
table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #334155; }
th { background: #1e293b; color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
tr:hover { background: #334155; }
tr td:first-child { font-family: 'SF Mono', 'Consolas', monospace; font-size: 0.85rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
.badge-success { background: #22c55e22; color: #22c55e; }
.badge-error { background: #ef444422; color: #ef4444; }
.badge-info { background: #3b82f622; color: #3b82f6; }
.badge-warning { background: #f59e0b22; color: #f59e0b; }
.detail-row { display: none; }
.detail-row td { background: #0f172a; padding: 14px; }
.detail-row pre { font-size: 0.8rem; color: #94a3b8; white-space: pre-wrap; word-break: break-word; }
.expand-btn { cursor: pointer; color: #3b82f6; font-size: 0.85rem; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
.filter-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.filter-bar input, .filter-bar select { background: #1e293b; border: 1px solid #334155; color: #e2e8f0; padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
.filter-bar input::placeholder { color: #64748b; }
.error-section { margin-top: 24px; }
.error-section h3 { color: #ef4444; margin-bottom: 12px; }
</style>
</head>
<body>
<div class="card-header">
  <div>
    <h1>AI Video Renamer Dashboard</h1>
    <p class="subtitle">Log file: {{ log_file }} &middot; {{ file_count }} log entries</p>
  </div>
  <div class="filter-bar">
    <input type="text" id="search" placeholder="Search files..." oninput="filterTable()">
    <select id="levelFilter" onchange="filterTable()">
      <option value="all">All levels</option>
      <option value="INFO">INFO</option>
      <option value="WARNING">WARNING</option>
      <option value="ERROR">ERROR</option>
    </select>
    <select id="eventFilter" onchange="filterTable()">
      <option value="all">All events</option>
      <option value="file_committed">Committed</option>
      <option value="file_skipped">Skipped</option>
      <option value="ai_analysis_failed">AI Failed</option>
      <option value="ai_analysis_success">AI Success</option>
      <option value="extraction_failed">Extraction Failed</option>
      <option value="category_override">Category Override</option>
    </select>
  </div>
</div>

<div class="stats-grid">
  <div class="stat-card total">
    <div class="value">{{ total_files }}</div>
    <div class="label">Total Files Processed</div>
  </div>
  <div class="stat-card success">
    <div class="value">{{ success_count }}</div>
    <div class="label">Committed</div>
  </div>
  <div class="stat-card fail">
    <div class="value">{{ fail_count }}</div>
    <div class="label">Failed</div>
  </div>
  <div class="stat-card skip">
    <div class="value">{{ skip_count }}</div>
    <div class="label">Skipped</div>
  </div>
</div>

<div class="charts-row">
  <div class="chart-card">
    <h3>Category Distribution</h3>
    <canvas id="categoryChart"></canvas>
  </div>
  <div class="chart-card">
    <h3>Daily Activity</h3>
    <canvas id="dailyChart"></canvas>
  </div>
</div>

<h3 style="margin-bottom:12px;">Activity Timeline</h3>
<table id="logTable">
  <thead>
    <tr>
      <th>Timestamp</th>
      <th>Level</th>
      <th>Event</th>
      <th>File</th>
      <th>Details</th>
    </tr>
  </thead>
  <tbody>
    {% for entry in timeline %}
    <tr class="log-row" data-level="{{ entry.level }}" data-event="{{ entry.event }}">
      <td style="white-space:nowrap">{{ entry.timestamp }}</td>
      <td><span class="badge badge-{{ entry.level.lower() }}">{{ entry.level }}</span></td>
      <td><span class="badge badge-info">{{ entry.event }}</span></td>
      <td>{{ entry.file or '-' }}</td>
      <td class="expand-btn" onclick="toggleDetail(this)">Show details &darr;</td>
    </tr>
    <tr class="detail-row">
      <td colspan="5"><pre>{{ entry.detail_text }}</pre></td>
    </tr>
    {% endfor %}
  </tbody>
</table>

{% if errors %}
<div class="error-section">
  <h3>Errors ({{ errors|length }})</h3>
  <table>
    <thead><tr><th>Timestamp</th><th>File</th><th>Detail</th></tr></thead>
    <tbody>
      {% for err in errors %}
      <tr>
        <td style="white-space:nowrap">{{ err.timestamp }}</td>
        <td>{{ err.file or '-' }}</td>
        <td style="color:#ef4444">{{ err.detail }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<script>
const catLabels = {{ cat_labels | safe }};
const catValues = {{ cat_values | safe }};
const dailyLabels = {{ daily_labels | safe }};
const dailyValues = {{ daily_values | safe }};

new Chart(document.getElementById('categoryChart'), {
  type: 'pie',
  data: { labels: catLabels, datasets: [{ data: catValues, backgroundColor: [
    '#3b82f6','#22c55e','#ef4444','#f59e0b','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16',
    '#6366f1','#d946ef','#0ea5e9','#10b981','#eab308','#64748b'
  ]}]},
  options: { responsive: true, plugins: { legend: { position: 'right', labels: { color: '#94a3b8' } } } }
});

new Chart(document.getElementById('dailyChart'), {
  type: 'bar',
  data: { labels: dailyLabels, datasets: [{ label: 'Events', data: dailyValues, backgroundColor: '#3b82f6' }] },
  options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#94a3b8' } }, y: { ticks: { color: '#94a3b8' } } } }
});

function toggleDetail(el) {
  const row = el.closest('tr').nextElementSibling;
  if (row && row.classList.contains('detail-row')) {
    row.style.display = row.style.display === 'table-row' ? 'none' : 'table-row';
    el.innerHTML = row.style.display === 'table-row' ? 'Hide details &uarr;' : 'Show details &darr;';
  }
}

function filterTable() {
  const q = document.getElementById('search').value.toLowerCase();
  const level = document.getElementById('levelFilter').value;
  const event = document.getElementById('eventFilter').value;
  document.querySelectorAll('.log-row').forEach(row => {
    const text = row.textContent.toLowerCase();
    const rl = row.dataset.level;
    const re = row.dataset.event;
    const match = text.includes(q) && (level === 'all' || rl === level) && (event === 'all' || re === event);
    row.style.display = match ? '' : 'none';
    const detail = row.nextElementSibling;
    if (detail && detail.classList.contains('detail-row')) {
      detail.style.display = 'none';
    }
  });
}
</script>
</body>
</html>
"""

def load_logs(log_paths):
    global LOG_DATA, STATS, TIMELINE, CATEGORY_COUNTS, ERRORS, DAILY_COUNTS, TOTAL_FILES, SUCCESS_COUNT, FAIL_COUNT, SKIP_COUNT

    LOG_DATA = []
    for path in log_paths:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        LOG_DATA.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    if not LOG_DATA:
        return

    CATEGORY_COUNTS = Counter()
    ERRORS = []
    TIMELINE = []
    DAILY_COUNTS = Counter()

    for entry in LOG_DATA:
        event = entry.get('event', '')
        file_name = entry.get('file', '')
        details = entry.get('details', {}) or {}
        ts = entry.get('timestamp', '')
        day = ts[:10] if ts else ''
        if day:
            DAILY_COUNTS[day] += 1

        detail_text = json.dumps(details, indent=2) if details else '-'

        if event == 'file_committed':
            SUCCESS_COUNT += 1
            cat = details.get('category', 'unknown')
            CATEGORY_COUNTS[cat] += 1
        elif event in ('ai_analysis_failed', 'extraction_failed', 'file_commit_failed'):
            FAIL_COUNT += 1
            ERRORS.append({"timestamp": ts, "file": file_name, "detail": details.get('error', detail_text[:200])})
        elif event == 'file_skipped':
            SKIP_COUNT += 1

        TIMELINE.append({
            "timestamp": ts,
            "level": entry.get('level', 'INFO'),
            "event": event,
            "file": file_name,
            "detail_text": detail_text,
        })

    TOTAL_FILES = len(TIMELINE)


@app.route("/")
def index():
    return render_template_string(
        INDEX_HTML,
        log_file=", ".join(args.log) if args.log else (args.dir or "logs/"),
        file_count=len(LOG_DATA),
        total_files=TOTAL_FILES,
        success_count=SUCCESS_COUNT,
        fail_count=FAIL_COUNT,
        skip_count=SKIP_COUNT,
        timeline=TIMELINE,
        errors=ERRORS,
        cat_labels=json.dumps([k for k in CATEGORY_COUNTS.keys()]),
        cat_values=json.dumps([v for v in CATEGORY_COUNTS.values()]),
        daily_labels=json.dumps([k for k in sorted(DAILY_COUNTS.keys())]),
        daily_values=json.dumps([DAILY_COUNTS[k] for k in sorted(DAILY_COUNTS.keys())]),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Renamer Log Dashboard")
    parser.add_argument("--log", "-l", nargs="+", help="Path(s) to JSONL log file(s) (supports glob)", default=None)
    parser.add_argument("--port", "-p", type=int, default=5050, help="Dashboard port")
    parser.add_argument("--dir", "-d", help="Directory containing log files (scans for renamer_*.jsonl)")
    args = parser.parse_args()

    log_paths = []
    if args.log:
        for pattern in args.log:
            log_paths.extend(glob.glob(pattern, recursive=True))
    if args.dir:
        log_dir = args.dir
        if not log_paths:
            log_paths = glob.glob(os.path.join(log_dir, "renamer_*.jsonl"))
    if not log_paths:
        default_logs = glob.glob("logs/renamer_*.jsonl")
        if default_logs:
            log_paths = default_logs
        else:
            print("No log files found. Use --log /path/to/log.jsonl or --dir /path/to/logs/")
            sys.exit(1)

    load_logs(log_paths)
    print(f"Loaded {len(LOG_DATA)} log entries from {len(log_paths)} file(s)")
    print(f"Dashboard: http://127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
