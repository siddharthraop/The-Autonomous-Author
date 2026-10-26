/* The Autonomous Author app: commit a feature, watch the agent, review the draft. */
(() => {
  const C = window.AUTHOR_CONFIG, API = C.api.replace(/\/$/, "");
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const STAGES = {
    commit: "Commit to main", change: "Read the code change", ticket: "Read the doc ticket", pages: "Find affected pages",
    rules: "Apply fixed rules", model_start: "Draft with Gemini", model: "Draft with Gemini", grounding: "Check every sentence's source",
    revise: "Revise failed sentences", checks: "Style, build and link checks", score: "Score the draft",
    dita: "Write DITA 1.3 and validate", done: "Draft ready for review",
  };
  let samples = [], current = null, run = null, busy = false;

  $("#design-link").href = C.design; $("#repo-link").href = C.repo;
  const theme = () => { const t = document.documentElement.dataset.theme; document.documentElement.dataset.theme = t === "dark" ? "light" : "dark";
    try { localStorage.setItem("aa-theme", document.documentElement.dataset.theme); } catch (e) {} };
  try { const t = localStorage.getItem("aa-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
  $("#theme").onclick = theme;

  const diffHtml = (d) => esc(d).replace(/\n$/, "").split("\n").map((l) =>
    `<span class="${l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") ? "h" : l.startsWith("+") ? "a" : l.startsWith("-") ? "d" : "c"}">${l || " "}</span>`).join("");

  async function api(path, opts) {
    const r = await fetch(API + path, opts);
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
    return r;
  }

  // Step 1 ---------------------------------------------------------------
  function renderSamples() {
    const cards = samples.map((s) => `<button class="card" role="radio" aria-checked="false" data-id="${s.id}"><b>${esc(s.title)}</b><span>${esc(s.why.split(". ")[0])}.</span></button>`);
    cards.push(`<button class="card" role="radio" aria-checked="false" data-id="custom"><b>Write your own</b><span>Choose a setting and a change, and describe it in your words.</span></button>`);
    $("#samples").innerHTML = cards.join("");
    $("#samples").querySelectorAll(".card").forEach((b) => (b.onclick = () => pick(b.dataset.id)));
  }

  function pick(id) {
    current = id;
    $("#samples").querySelectorAll(".card").forEach((b) => b.setAttribute("aria-checked", b.dataset.id === id));
    const s = samples.find((x) => x.id === id);
    $("#custom").hidden = !!s;
    if (s) {
      $("#f-title").value = s.title; $("#f-text").value = s.text; $("#f-doctype").value = s.doc_type;
      $("#f-diff").innerHTML = diffHtml(s.diff); $("#f-why").textContent = "What a good draft does: " + s.why; $("#f-why").hidden = false;
    } else {
      $("#f-title").value = ""; $("#f-text").value = ""; $("#f-why").hidden = true; customChanged();
    }
  }

  function customOps() {
    const kind = $("#c-kind").value, setting = $("#c-setting").value, v = +$("#c-value").value, name = $("#c-name").value.trim();
    if (kind === "field") return [{ op: "field", name }];
    if (kind === "setting") return [{ op: "setting", name, value: v }];
    return [{ op: "set", setting, attr: kind, value: v }];
  }

  let previewTimer;
  function customChanged() {
    const kind = $("#c-kind").value;
    $("#c-setting-l").hidden = kind === "field" || kind === "setting";
    $("#c-name-l").hidden = !(kind === "field" || kind === "setting");
    $("#c-value-l").hidden = kind === "field";
    if (kind === "field" && !/^[a-z][A-Za-z0-9]+$/.test($("#c-name").value)) $("#c-name").value = "tcpTimeWaitSourceLabel";
    if (kind === "setting" && !/^[a-z][a-z0-9_]+$/.test($("#c-name").value)) $("#c-name").value = "icmp";
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => {
      try { const r = await api("/api/change-preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ops: customOps() }) });
        $("#f-diff").innerHTML = diffHtml((await r.json()).diff); $("#commit-note").textContent = "";
      } catch (e) { $("#f-diff").textContent = ""; $("#commit-note").textContent = e.message; }
    }, 250);
  }
  ["#c-kind", "#c-setting", "#c-value", "#c-name"].forEach((s) => $(s).addEventListener("input", customChanged));

  // Step 2 ---------------------------------------------------------------
  function stageRow(stage, detail, cls = "") {
    const list = $("#stages"), label = STAGES[stage] || stage;
    let li = [...list.children].find((x) => x.dataset.label === label && x.classList.contains("run"));
    if (!li) { list.querySelectorAll(".run").forEach((x) => x.classList.remove("run")); li = document.createElement("li"); li.dataset.label = label; list.appendChild(li); }
    li.className = cls; li.innerHTML = `<span class="dot" aria-hidden="true"></span><b>${esc(label)}</b><span class="d">${esc(detail)}</span>`;
  }

  async function commit() {
    if (busy || !current) return;
    const body = { title: $("#f-title").value.trim(), text: $("#f-text").value.trim(), doc_type: $("#f-doctype").value, audience: $("#f-audience").value.trim() };
    if (current === "custom") body.ops = customOps(); else body.sample = current;
    if (!body.title || !body.text) { $("#commit-note").textContent = "Give the feature a title and a description."; return; }
    busy = true; $("#commit").disabled = true; $("#commit-note").textContent = "";
    $("#step2").hidden = false; $("#step3").hidden = true; $("#stages").innerHTML = "";
    $("#step2").scrollIntoView({ behavior: "smooth", block: "start" });
    stageRow("commit", "committing as Developer…", "run");
    try {
      const r = await api("/api/features", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const reader = r.body.getReader(), dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true }); let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const ev = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1);
          if (ev.stage === "done") { stageRow("done", `${ev.result.seconds ?? ""} s from commit to draft`); showResult(ev.result); }
          else if (ev.stage === "error") { stageRow("error", ev.detail, "err"); }
          else stageRow(ev.stage, ev.detail, ev.stage === "model_start" ? "run" : "");
        }
      }
    } catch (e) { stageRow("error", e.message.includes("fetch") ? "The demo service didn't answer. It may be starting up; try again in a few seconds." : e.message, "err"); }
    busy = false; $("#commit").disabled = false;
  }
  $("#commit").onclick = commit;

  // Step 3 ---------------------------------------------------------------
  const TABS = [["compare", "Compare with expected"], ["myst", "Docs as code"], ["dita", "DITA"], ["preview", "Preview"], ["report", "Report"], ["commit", "Code commit"]];
  let tab = "compare";

  function showResult(r) {
    run = r; $("#step3").hidden = false;
    if (r.status === "no docs change") { $("#summary").innerHTML = `<p class="notice">This change has nothing a reader can see, so no docs change is needed.</p>`; $("#tabs").innerHTML = $("#panels").innerHTML = $("#review").innerHTML = ""; return; }
    const sc = r.score, ok = r.expected.filter((e) => e.ok).length;
    $("#summary").innerHTML = `<span class="score">${sc.total} / 10</span>
      <span class="badge ${sc.label === "ready for review" ? "b-ready" : "b-review"}">${esc(sc.label)}</span>
      <span class="meta">${ok} of ${r.expected.length} expectations met · ${r.questions.length} question(s) · model ${esc(r.model)} · ${esc(r.status)}</span>
      ${r.model_error ? `<p class="notice">The model call failed, so fixed rules and questions made this draft: ${esc(r.model_error.slice(0, 160))}</p>` : ""}`;
    $("#tabs").innerHTML = TABS.map(([k, l]) => `<button role="tab" aria-selected="${k === tab}" data-k="${k}">${l}</button>`).join("");
    $("#tabs").querySelectorAll("button").forEach((b) => (b.onclick = () => { tab = b.dataset.k; showResult(run); }));
    $("#panels").innerHTML = `<div class="panel" role="tabpanel">${panel(r)}</div>`;
    review(r);
    if (tab === "compare") $("#step3").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function files(diffs) {
    const k = Object.keys(diffs);
    return k.length ? k.map((p) => `<h3>${esc(p)}</h3><pre class="diff">${diffHtml(diffs[p])}</pre>`).join("") : `<p class="meta">No changes.</p>`;
  }

  function panel(r) {
    if (tab === "compare") return `<p>What a good draft for this feature should do, and what this draft did.</p>
      <table class="cmp">${r.expected.map((e) => `<tr><td class="${e.ok ? "ok" : "no"}">${e.ok ? "✓" : "✗"}</td><td>${esc(e.label)}${e.detail ? `<div class="meta">${esc(e.detail)}</div>` : ""}</td></tr>`).join("")}</table>
      <h3>Change items the agent read from the code</h3><ul>${r.items.map((i) => `<li><code>${i.id}</code> ${esc(i.text)}</li>`).join("")}</ul>`;
    if (tab === "myst") return `<p>The draft in the docs-as-code source: MyST Markdown, built with Sphinx. The checks ran on this.</p>${files(r.myst_diff)}`;
    if (tab === "dita") return `<p>The same draft as DITA 1.3 topics and a map. Values are <code>&lt;keyword keyref&gt;</code> keys defined in the map;
      questions are <code>&lt;draft-comment&gt;</code> elements. ${r.dita_errors.length ? `<span class="no">Not valid: ${esc(r.dita_errors.join("; "))}</span>` : `<span class="ok">✓ Valid against the OASIS DITA 1.3 DTDs.</span>`}</p>${files(r.dita_diff)}`;
    if (tab === "preview") return r.preview.length ? r.preview.map((p) => `<h3>${esc(p.replace(".html", ""))}</h3><iframe title="Preview of ${esc(p)}" src="${API}/api/runs/${r.run_id}/preview/${p}"></iframe>`).join("") : `<p class="meta">Only the substitution file changed; every page that shows the value updates on the next build.</p>`;
    if (tab === "report") return `<div class="report">${r.report_html}</div>`;
    return `<h3>Commit ${esc(r.commit.sha)} by ${esc(r.commit.author)}</h3><pre>${esc(r.commit.message)}</pre><pre class="diff">${diffHtml(r.code_diff)}</pre>`;
  }

  function review(r) {
    const qs = r.questions;
    let h = `<h3>Your review</h3>`;
    if (r.status === "approved") h += `<p class="ok">✓ Approved. In the real workflow this merges the docs pull request, and the docs publish with the release tag.</p>`;
    else if (qs.length) h += `<p>The agent couldn't source ${qs.length} fact(s), so it asked instead of guessing. Answer as the developer or writer would; the checks run again.</p>` +
      qs.map((q, i) => `<div class="q"><label for="q${i}">${esc(q.question)}</label><textarea id="q${i}" rows="2" data-q="${esc(q.question)}"></textarea></div>`).join("") +
      `<div class="actions"><button class="btn" id="answer" type="button">Apply answers and re-check</button></div>`;
    else h += `<p>Nothing is open. Read the draft, then approve it or start again.</p>`;
    h += `<div class="actions"><button class="btn btn-fill" id="approve" type="button" ${r.can_approve ? "" : "disabled"}>Approve draft</button>
      <a class="btn" href="${API}/api/runs/${r.run_id}/download">Download MyST, DITA and report (.zip)</a>
      <span class="meta">${r.can_approve || r.status === "approved" ? "" : "Approve unlocks when every question is answered and every check passes."}</span></div>`;
    $("#review").innerHTML = h;
    const post = async (path, body) => {
      try { const res = await api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); showResult(await res.json()); }
      catch (e) { $("#review").insertAdjacentHTML("beforeend", `<p class="notice">${esc(e.message)}</p>`); }
    };
    if ($("#answer")) $("#answer").onclick = () => {
      const answers = {}; $("#review").querySelectorAll("textarea").forEach((t) => { if (t.value.trim()) answers[t.dataset.q] = t.value.trim(); });
      post(`/api/runs/${r.run_id}/answers`, { answers });
    };
    $("#approve").onclick = () => post(`/api/runs/${r.run_id}/approve`);
  }

  // Start ----------------------------------------------------------------
  (async () => {
    try {
      const h = await (await api("/api/health")).json();
      $("#live").textContent = h.model === "none" ? "Live · rules only (no model key)" : `Live · ${h.model}`;
      samples = await (await api("/api/samples")).json();
      renderSamples(); pick(samples[0].id);
    } catch (e) {
      $("#live").textContent = "Demo service unavailable";
      $("#samples").innerHTML = `<p class="notice">The demo service isn't reachable right now (${esc(e.message)}). It may be starting; reload in a few seconds.</p>`;
      $("#commit").disabled = true;
    }
  })();
})();
