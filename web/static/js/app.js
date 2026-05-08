let currentTaskId = null;
let currentMarkdown = "";

function setTopic(topic) {
    document.getElementById("topicInput").value = topic;
}

async function startCollect() {
    const topic = document.getElementById("topicInput").value.trim();
    const btn = document.getElementById("collectBtn");

    btn.disabled = true;
    btn.textContent = "采集中...";

    document.getElementById("progressSection").style.display = "block";
    document.getElementById("reportSection").style.display = "none";
    document.getElementById("progressLog").innerHTML = "";
    document.getElementById("progressBar").style.width = "10%";

    try {
        const response = await fetch("/api/collect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic: topic }),
        });
        const data = await response.json();
        currentTaskId = data.task_id;
        listenProgress(data.task_id);
    } catch (err) {
        addLog("ERROR", "请求失败: " + err.message);
        btn.disabled = false;
        btn.textContent = "开始采集";
    }
}

function listenProgress(taskId) {
    const evtSource = new EventSource("/api/status/" + taskId);
    let progressPercent = 10;

    evtSource.addEventListener("progress", function(event) {
        const data = JSON.parse(event.data);
        addLog(data.level, data.message);
        progressPercent = Math.min(progressPercent + 5, 90);
        document.getElementById("progressBar").style.width = progressPercent + "%";
    });

    evtSource.addEventListener("done", function(event) {
        const data = JSON.parse(event.data);
        evtSource.close();

        document.getElementById("progressBar").style.width = "100%";
        document.getElementById("progressBar").style.animation = "none";

        const btn = document.getElementById("collectBtn");
        btn.disabled = false;
        btn.textContent = "开始采集";

        if (data.status === "completed" && data.result) {
            currentMarkdown = data.result.markdown || "";
            showReport(data.result.report_title, currentMarkdown);
            loadReports();
        } else {
            addLog("ERROR", "采集失败: " + (data.error || "未知错误"));
        }
    });

    evtSource.onerror = function() {
        evtSource.close();
        const btn = document.getElementById("collectBtn");
        btn.disabled = false;
        btn.textContent = "开始采集";
        addLog("ERROR", "连接中断");
    };
}

function addLog(level, message) {
    const log = document.getElementById("progressLog");
    const entry = document.createElement("div");
    entry.className = "log-entry " + level.toLowerCase();
    const time = new Date().toLocaleTimeString();
    entry.textContent = "[" + time + "] " + message;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function showReport(title, markdown) {
    document.getElementById("reportSection").style.display = "block";
    document.getElementById("reportTitle").textContent = title || "报告";
    document.getElementById("reportContent").innerHTML = renderMarkdown(markdown);
}

function renderMarkdown(md) {
    if (!md) return "<p class='empty-hint'>暂无内容</p>";

    let html = md;
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>");
    html = html.replace(/^---$/gm, "<hr>");
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    const lines = html.split("\n");
    let result = [];
    let inList = false;

    for (let line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("- ")) {
            if (!inList) {
                result.push("<ul>");
                inList = true;
            }
            result.push("<li>" + trimmed.substring(2) + "</li>");
        } else if (trimmed.startsWith("  - ")) {
            result.push("<li style='margin-left:20px;list-style:circle;'>" + trimmed.substring(4) + "</li>");
        } else {
            if (inList) {
                result.push("</ul>");
                inList = false;
            }
            if (trimmed === "") {
                continue;
            } else if (!trimmed.startsWith("<")) {
                result.push("<p>" + trimmed + "</p>");
            } else {
                result.push(trimmed);
            }
        }
    }
    if (inList) result.push("</ul>");

    return result.join("\n");
}

function downloadReport() {
    if (!currentMarkdown) return;
    const blob = new Blob([currentMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "env-news-report.md";
    a.click();
    URL.revokeObjectURL(url);
}

async function loadReports() {
    try {
        const response = await fetch("/api/reports");
        const data = await response.json();
        const list = document.getElementById("reportList");

        if (!data.reports || data.reports.length === 0) {
            list.innerHTML = "<p class='empty-hint'>暂无历史报告</p>";
            return;
        }

        list.innerHTML = data.reports.map(function(r) {
            const date = new Date(r.modified * 1000).toLocaleString("zh-CN");
            return '<div class="report-item" onclick="loadReport(\'' + r.filename + '\')">' +
                '<span>' + r.name + '</span>' +
                '<span class="report-date">' + date + '</span>' +
                '</div>';
        }).join("");
    } catch (err) {
        console.error("Failed to load reports:", err);
    }
}

async function loadReport(filename) {
    try {
        const response = await fetch("/api/reports/" + encodeURIComponent(filename));
        const data = await response.json();
        if (data.content) {
            currentMarkdown = data.content;
            const titleMatch = data.content.match(/^# (.+)$/m);
            showReport(titleMatch ? titleMatch[1] : filename, data.content);
            document.getElementById("progressSection").style.display = "none";
        }
    } catch (err) {
        console.error("Failed to load report:", err);
    }
}

document.addEventListener("DOMContentLoaded", loadReports);
