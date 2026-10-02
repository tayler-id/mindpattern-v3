(function () {
  "use strict";

  var STORAGE_KEY = "mindpattern.agent-development.tutorial.v1";
  var STORAGE_VERSION = 1;
  var memoryState;
  var canPersist = true;
  var lessons = [];
  var lessonById = Object.create(null);
  var activeIndex = 0;

  function emptyState() {
    return {
      version: STORAGE_VERSION,
      completions: [],
      quizAnswers: {},
      notes: {},
      activeId: null,
      mode: "guided",
      labs: {
        brief: {
          action: "A reader enters a remembered word from a story title.",
          result: "The matching published story appears.",
          constraints: "Keep drafts private and preserve the public response shape.",
          evidence: "Show the query, returned titles, no-match result, and draft exclusion.",
          prompt: ""
        },
        verification: { checks: ["status"], repaired: false },
        prototypes: { query: "", choice: "" }
      }
    };
  }

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function stringMap(value, allowedKeys) {
    var output = {};
    if (!isRecord(value)) return output;
    Object.keys(value).forEach(function (key) {
      if (allowedKeys.indexOf(key) !== -1 && typeof value[key] === "string") output[key] = value[key];
    });
    return output;
  }

  function parseState(raw, knownIds, knownNotes) {
    var value = JSON.parse(raw);
    if (!isRecord(value) || value.version !== STORAGE_VERSION) throw new Error("Unsupported saved course data");

    var state = emptyState();
    if (!Array.isArray(value.completions)) throw new Error("Invalid completion data");
    state.completions = value.completions.filter(function (id, index, all) {
      return typeof id === "string" && knownIds.indexOf(id) !== -1 && all.indexOf(id) === index;
    });

    if (!isRecord(value.quizAnswers)) throw new Error("Invalid quiz data");
    Object.keys(value.quizAnswers).forEach(function (id) {
      var answer = value.quizAnswers[id];
      if (knownIds.indexOf(id) === -1 || !isRecord(answer)) return;
      if (typeof answer.value !== "string" || typeof answer.correct !== "boolean") return;
      if (!Number.isInteger(answer.attempts) || answer.attempts < 1) return;
      state.quizAnswers[id] = { value: answer.value, correct: answer.correct, attempts: answer.attempts };
    });

    if (!isRecord(value.notes) || Object.keys(value.notes).some(function (key) {
      return typeof value.notes[key] !== "string";
    })) throw new Error("Invalid saved notebook");
    state.notes = stringMap(value.notes, knownNotes);
    state.activeId = typeof value.activeId === "string" && knownIds.indexOf(value.activeId) !== -1 ? value.activeId : null;
    state.mode = value.mode === "read-all" ? "read-all" : "guided";

    if (isRecord(value.labs)) {
      var brief = value.labs.brief;
      if (isRecord(brief)) {
        ["action", "result", "constraints", "evidence", "prompt"].forEach(function (key) {
          if (typeof brief[key] === "string") state.labs.brief[key] = brief[key];
        });
      }
      var verification = value.labs.verification;
      if (isRecord(verification)) {
        if (Array.isArray(verification.checks)) {
          state.labs.verification.checks = verification.checks.filter(function (item) {
            return ["status", "body", "exclusion"].indexOf(item) !== -1;
          });
        }
        if (typeof verification.repaired === "boolean") state.labs.verification.repaired = verification.repaired;
      }
      var prototypes = value.labs.prototypes;
      if (isRecord(prototypes)) {
        if (typeof prototypes.query === "string") state.labs.prototypes.query = prototypes.query;
        if (["", "exact", "substring"].indexOf(prototypes.choice) !== -1) state.labs.prototypes.choice = prototypes.choice;
      }
    }
    return state;
  }

  function showStorageWarning(message) {
    var warning = document.getElementById("storage-warning");
    warning.textContent = message;
    warning.hidden = false;
  }

  function loadState() {
    var knownIds = lessons.map(function (lesson) { return lesson.id; });
    var knownNotes = Array.prototype.map.call(document.querySelectorAll("[data-note]"), function (note) {
      return note.getAttribute("data-note");
    });
    var fallback = emptyState();
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null) return fallback;
      return parseState(raw, knownIds, knownNotes);
    } catch (error) {
      canPersist = false;
      showStorageWarning("Saved progress could not be read. This session will stay in memory, and export still works. The unreadable saved copy will not be replaced.");
      return fallback;
    }
  }

  function saveState(message) {
    if (canPersist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(memoryState));
      } catch (error) {
        canPersist = false;
        showStorageWarning("Progress cannot be saved in this browser. This session will stay in memory, and export still works.");
      }
    }
    if (message) announce(canPersist ? message : "Updated for this session. Export your notebook to keep a copy.");
  }

  function announce(message) {
    var status = document.getElementById("course-status");
    status.textContent = "";
    window.setTimeout(function () { status.textContent = message; }, 10);
  }

  function lessonTitle(lesson) {
    return lesson.getAttribute("data-title") || (lesson.querySelector("h2") ? lesson.querySelector("h2").textContent.trim() : lesson.id);
  }

  function collectLessons() {
    lessons = Array.prototype.slice.call(document.querySelectorAll("#lessons > .lesson"));
    lessons.forEach(function (lesson) {
      if (!lesson.id || lessonById[lesson.id]) return;
      lessonById[lesson.id] = lesson;
    });
    lessons = lessons.filter(function (lesson) { return lesson.id && lessonById[lesson.id] === lesson; });
  }

  function makeNavigation() {
    var nav = document.getElementById("lesson-nav");
    nav.textContent = "";
    lessons.forEach(function (lesson, index) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      var title = document.createElement("span");
      var check = document.createElement("span");
      button.type = "button";
      button.setAttribute("data-lesson-id", lesson.id);
      title.textContent = lessonTitle(lesson);
      check.className = "nav-check";
      check.setAttribute("aria-hidden", "true");
      button.appendChild(title);
      button.appendChild(check);
      button.addEventListener("click", function () { showLesson(index, true); });
      item.appendChild(button);
      nav.appendChild(item);
    });
  }

  function updateProgress() {
    var count = memoryState.completions.length;
    var total = lessons.length;
    var percent = total ? Math.round((count / total) * 100) : 0;
    document.getElementById("progress-count").textContent = count + " of " + total + " complete";
    document.getElementById("progress-bar").style.width = percent + "%";
    document.querySelectorAll("#lesson-nav button").forEach(function (button) {
      button.setAttribute("data-complete", String(memoryState.completions.indexOf(button.getAttribute("data-lesson-id")) !== -1));
    });
    lessons.forEach(function (lesson) {
      var button = lesson.querySelector(".complete-lesson");
      if (!button) return;
      var complete = memoryState.completions.indexOf(lesson.id) !== -1;
      button.setAttribute("aria-pressed", String(complete));
      button.textContent = complete ? "Lesson complete" : "Mark lesson complete";
    });
  }

  function updateMode() {
    document.body.setAttribute("data-mode", memoryState.mode);
    var toggle = document.getElementById("mode-toggle");
    var readAll = memoryState.mode === "read-all";
    toggle.setAttribute("aria-pressed", String(readAll));
    toggle.textContent = readAll ? "Use guided focus" : "Read all lessons";
    document.querySelector(".lesson-controls").hidden = readAll;
    lessons.forEach(function (lesson, index) {
      lesson.hidden = !readAll && index !== activeIndex;
    });
  }

  function showLesson(index, moveFocus) {
    if (!lessons.length) return;
    activeIndex = Math.max(0, Math.min(index, lessons.length - 1));
    var active = lessons[activeIndex];
    memoryState.activeId = active.id;
    saveState();

    lessons.forEach(function (lesson, lessonIndex) {
      lesson.hidden = memoryState.mode === "guided" && lessonIndex !== activeIndex;
    });
    document.querySelectorAll("#lesson-nav button").forEach(function (button) {
      if (button.getAttribute("data-lesson-id") === active.id) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    document.getElementById("lesson-position").textContent = "Lesson " + (activeIndex + 1) + " of " + lessons.length + " · " + (active.getAttribute("data-minutes") || "") + " min";
    document.getElementById("previous-lesson").disabled = activeIndex === 0;
    document.getElementById("next-lesson").disabled = activeIndex === lessons.length - 1;
    if (moveFocus) {
      var heading = active.querySelector("h2");
      active.scrollIntoView({ block: "start" });
      if (heading) heading.focus({ preventScroll: true });
    }
  }

  function enhancePrompts() {
    document.querySelectorAll("pre.prompt").forEach(function (prompt, index) {
      if (prompt.parentElement.classList.contains("prompt-shell")) return;
      var shell = document.createElement("div");
      var button = document.createElement("button");
      shell.className = "prompt-shell";
      button.type = "button";
      button.className = "copy-prompt";
      button.textContent = "Copy prompt";
      button.setAttribute("aria-label", "Copy prompt " + (index + 1));
      prompt.parentNode.insertBefore(shell, prompt);
      shell.appendChild(prompt);
      shell.appendChild(button);
      button.addEventListener("click", function () {
        copyText(prompt.innerText, prompt.querySelector("code") || prompt, button);
      });
    });
  }

  function selectElementText(element) {
    var selection = window.getSelection();
    var range = document.createRange();
    range.selectNodeContents(element);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function copyText(text, fallbackElement, button) {
    function copied() {
      var original = button ? button.textContent : "";
      if (button) button.textContent = "Copied";
      announce("Copied to clipboard.");
      window.setTimeout(function () { if (button) button.textContent = original; }, 1400);
    }
    function fallback() {
      if (fallbackElement.tagName === "TEXTAREA" || fallbackElement.tagName === "INPUT") fallbackElement.select();
      else selectElementText(fallbackElement);
      announce("Clipboard access is unavailable. The text is selected so you can copy it.");
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(copied, fallback);
    } else {
      fallback();
    }
  }

  function setupNotes() {
    document.querySelectorAll("[data-note]").forEach(function (note) {
      var id = note.getAttribute("data-note");
      if (Object.prototype.hasOwnProperty.call(memoryState.notes, id)) note.value = memoryState.notes[id];
      note.addEventListener("input", function () {
        memoryState.notes[id] = note.value;
        saveState("Notebook saved.");
      });
    });
  }

  function quizId(form) {
    return form.closest(".lesson").id;
  }

  function feedbackFor(form, saved) {
    var selected = form.querySelector('input[type="radio"][value="' + CSS.escape(saved.value) + '"]');
    var feedback = form.querySelector(".quiz-feedback");
    var detail = selected ? selected.getAttribute("data-feedback") : "";
    form.setAttribute("data-result", saved.correct ? "correct" : "incorrect");
    feedback.textContent = (saved.correct ? "That reasoning holds. " : "Try that again. ") + detail + " Attempts: " + saved.attempts + ".";
  }

  function setupQuizzes() {
    document.querySelectorAll("form.quiz").forEach(function (form) {
      var id = quizId(form);
      var saved = memoryState.quizAnswers[id];
      if (saved) {
        var selected = form.querySelector('input[type="radio"][value="' + CSS.escape(saved.value) + '"]');
        if (selected) {
          selected.checked = true;
          saved.correct = selected.value === form.getAttribute("data-answer");
          feedbackFor(form, saved);
        } else {
          delete memoryState.quizAnswers[id];
        }
      }
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var selected = form.querySelector('input[type="radio"]:checked');
        if (!selected) {
          form.querySelector(".quiz-feedback").textContent = "Choose an answer before checking your reasoning.";
          return;
        }
        var prior = memoryState.quizAnswers[id];
        var answer = {
          value: selected.value,
          correct: selected.value === form.getAttribute("data-answer"),
          attempts: prior ? prior.attempts + 1 : 1
        };
        memoryState.quizAnswers[id] = answer;
        saveState();
        feedbackFor(form, answer);
      });
    });
  }

  function setupCompletionButtons() {
    lessons.forEach(function (lesson) {
      var button = lesson.querySelector(".complete-lesson");
      if (!button) return;
      button.addEventListener("click", function () {
        var index = memoryState.completions.indexOf(lesson.id);
        if (index === -1) {
          memoryState.completions.push(lesson.id);
          saveState("Lesson marked complete.");
        } else {
          memoryState.completions.splice(index, 1);
          saveState("Lesson marked incomplete.");
        }
        updateProgress();
      });
    });
  }

  function fieldMarkup(id, label, value) {
    return '<label for="' + id + '">' + label + '</label><textarea id="' + id + '" rows="3">' + escapeHtml(value) + '</textarea>';
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  function buildBriefPrompt(data) {
    return [
      "Task: " + (data.action || "Describe what the reader should be able to do."),
      "Expected result: " + (data.result || "Name the observable outcome."),
      "Constraints: " + (data.constraints || "List the boundaries the agent must respect."),
      "Evidence: " + (data.evidence || "State what will prove the result works.")
    ].join("\n");
  }

  function setupBriefLab(container) {
    var data = memoryState.labs.brief;
    container.className = "lab brief-lab";
    container.innerHTML = '<p class="lab-kicker">Practice lab</p><h3>Turn an intention into a work brief</h3><p>Write what the agent should do and how you will recognize the result.</p><div class="lab-grid"><div>' +
      fieldMarkup("brief-action", "Reader action", data.action) + fieldMarkup("brief-result", "Expected result", data.result) +
      '</div><div>' + fieldMarkup("brief-constraints", "Constraints", data.constraints) + fieldMarkup("brief-evidence", "Evidence", data.evidence) +
      '</div></div><div class="lab-actions"><button class="primary" type="button" data-generate>Build the prompt</button></div><label for="brief-prompt">Editable prompt</label><textarea id="brief-prompt" rows="7"></textarea><div class="lab-actions"><button type="button" data-copy>Copy this prompt</button></div><p class="save-status" role="status"></p>';
    var fields = {
      action: container.querySelector("#brief-action"),
      result: container.querySelector("#brief-result"),
      constraints: container.querySelector("#brief-constraints"),
      evidence: container.querySelector("#brief-evidence"),
      prompt: container.querySelector("#brief-prompt")
    };
    fields.prompt.value = data.prompt || buildBriefPrompt(data);
    Object.keys(fields).forEach(function (key) {
      fields[key].addEventListener("input", function () {
        data[key] = fields[key].value;
        saveState();
        container.querySelector(".save-status").textContent = canPersist ? "Saved locally." : "Kept in memory for this session.";
      });
    });
    container.querySelector("[data-generate]").addEventListener("click", function () {
      ["action", "result", "constraints", "evidence"].forEach(function (key) { data[key] = fields[key].value; });
      data.prompt = buildBriefPrompt(data);
      fields.prompt.value = data.prompt;
      saveState("Prompt built and saved.");
    });
    container.querySelector("[data-copy]").addEventListener("click", function (event) {
      copyText(fields.prompt.value, fields.prompt, event.currentTarget);
    });
  }

  function verificationStories(repaired) {
    var stories = [
      { title: "A field guide to small agents", status: "published" },
      { title: "The quiet work of verification", status: "published" },
      { title: "Unreviewed launch notes", status: "draft" }
    ];
    return repaired ? stories.filter(function (story) { return story.status === "published"; }) : stories;
  }

  function verificationOutcomes(state) {
    var visible = verificationStories(state.repaired);
    return {
      status: { pass: true, text: "Status check: PASS. The response returned 200." },
      body: { pass: visible.length > 0, text: "Body check: " + (visible.length ? "PASS. Story records are present." : "FAIL. No story records are present.") },
      exclusion: { pass: visible.every(function (story) { return story.status !== "draft"; }), text: "Draft exclusion: " + (visible.every(function (story) { return story.status !== "draft"; }) ? "PASS. No draft is visible." : "FAIL. Unreviewed launch notes is still visible.") }
    };
  }

  function setupVerificationLab(container) {
    var state = memoryState.labs.verification;
    container.className = "lab verification-lab";
    container.innerHTML = '<p class="lab-kicker">Verification lab</p><h3>Catch a false green</h3><p class="simulation-label">Practice simulation. No repository commands run.</p><p>The invented response starts with a bug. A draft story appears beside published stories.</p><div class="dataset"><strong>Current response</strong><ul data-stories></ul></div><fieldset class="check-list"><legend>Choose what your proof should check</legend><label><input type="checkbox" value="status"> Response status is 200</label><label><input type="checkbox" value="body"> Response contains story records</label><label><input type="checkbox" value="exclusion"> Draft stories are excluded</label></fieldset><div class="lab-actions"><button class="primary" type="button" data-run>Run checks</button><button type="button" data-repair>Repair the simulated filter</button><button type="button" data-reset>Reset simulation</button></div><p class="lab-result" role="status" aria-live="polite"></p><ul class="check-outcomes" data-outcomes></ul>';
    var checks = Array.prototype.slice.call(container.querySelectorAll('input[type="checkbox"]'));
    checks.forEach(function (check) {
      check.checked = state.checks.indexOf(check.value) !== -1;
      check.addEventListener("change", function () {
        state.checks = checks.filter(function (item) { return item.checked; }).map(function (item) { return item.value; });
        container.querySelector(".lab-result").textContent = "Checks changed. Run them again to see the result.";
        container.querySelector(".lab-result").removeAttribute("data-result");
        container.querySelector("[data-outcomes]").textContent = "";
        saveState();
      });
    });
    function renderStories() {
      var list = container.querySelector("[data-stories]");
      list.innerHTML = verificationStories(state.repaired).map(function (story) {
        return "<li>" + escapeHtml(story.title) + " <small>(" + story.status + ")</small></li>";
      }).join("");
      container.querySelector("[data-repair]").disabled = state.repaired;
    }
    function runChecks() {
      var result = container.querySelector(".lab-result");
      var list = container.querySelector("[data-outcomes]");
      if (!state.checks.length) {
        result.textContent = "Choose at least one check.";
        result.removeAttribute("data-result");
        list.textContent = "";
        return;
      }
      var all = verificationOutcomes(state);
      var chosen = state.checks.map(function (id) { return all[id]; });
      var passed = chosen.every(function (item) { return item.pass; });
      result.setAttribute("data-result", passed ? "pass" : "fail");
      result.textContent = passed ? "Selected checks report PASS." : "Selected checks report FAIL.";
      if (passed && state.checks.length === 1 && state.checks[0] === "status" && !state.repaired) {
        result.textContent += " This is a false green because the draft remains visible.";
      }
      list.innerHTML = chosen.map(function (item) {
        return '<li data-pass="' + item.pass + '">' + escapeHtml(item.text) + "</li>";
      }).join("");
    }
    container.querySelector("[data-run]").addEventListener("click", runChecks);
    container.querySelector("[data-repair]").addEventListener("click", function () {
      state.repaired = true;
      saveState("The simulated filter now excludes drafts.");
      renderStories();
      runChecks();
      container.querySelector("[data-run]").focus();
    });
    container.querySelector("[data-reset]").addEventListener("click", function () {
      state.checks = ["status"];
      state.repaired = false;
      checks.forEach(function (check) { check.checked = check.value === "status"; });
      container.querySelector(".lab-result").textContent = "Simulation reset. The draft is visible again.";
      container.querySelector(".lab-result").removeAttribute("data-result");
      container.querySelector("[data-outcomes]").textContent = "";
      saveState();
      renderStories();
    });
    renderStories();
  }

  function prototypeMatches(query, kind) {
    var titles = ["Agents Need Receipts", "A Field Guide to Verification", "Working in Small Steps"];
    var trimmed = query.trim();
    if (kind === "exact") return trimmed ? titles.filter(function (title) { return title === trimmed; }) : [];
    if (!trimmed) return titles.slice();
    var needle = trimmed.toLocaleLowerCase();
    return titles.filter(function (title) { return title.toLocaleLowerCase().indexOf(needle) !== -1; });
  }

  function setupPrototypesLab(container) {
    var state = memoryState.labs.prototypes;
    container.className = "lab prototypes-lab";
    container.innerHTML = '<p class="lab-kicker">Prototype lab</p><h3>Compare search rules with the same input</h3><p class="simulation-label">Practice simulation. No repository commands run.</p><label for="prototype-query">Search the three invented published titles</label><input id="prototype-query" type="text" autocomplete="off" placeholder="Try verification or a full title"><div class="prototype-grid"><section class="result-panel" aria-labelledby="exact-title"><h4 id="exact-title">Exact title</h4><p data-exact-summary></p><ul data-exact aria-live="polite"></ul></section><section class="result-panel" aria-labelledby="substring-title"><h4 id="substring-title">Case-insensitive substring</h4><p data-substring-summary></p><ul data-substring aria-live="polite"></ul></section></div><fieldset class="choice-list"><legend>Which behavior better fits story discovery?</legend><label><input type="radio" name="prototype-choice" value="exact"> Exact title</label><label><input type="radio" name="prototype-choice" value="substring"> Case-insensitive substring</label></fieldset><p class="save-status" role="status"></p>';
    var query = container.querySelector("#prototype-query");
    query.value = state.query;
    function renderResults() {
      var exact = prototypeMatches(query.value, "exact");
      var substring = prototypeMatches(query.value, "substring");
      container.querySelector("[data-exact-summary]").textContent = exact.length + " result" + (exact.length === 1 ? "" : "s") + ". Empty input returns none.";
      container.querySelector("[data-substring-summary]").textContent = substring.length + " result" + (substring.length === 1 ? "" : "s") + ". Empty input returns all titles.";
      container.querySelector("[data-exact]").innerHTML = exact.length ? exact.map(function (title) { return "<li>" + escapeHtml(title) + "</li>"; }).join("") : "<li>No match</li>";
      container.querySelector("[data-substring]").innerHTML = substring.length ? substring.map(function (title) { return "<li>" + escapeHtml(title) + "</li>"; }).join("") : "<li>No match</li>";
    }
    query.addEventListener("input", function () {
      state.query = query.value;
      saveState();
      renderResults();
      container.querySelector(".save-status").textContent = canPersist ? "Query saved locally." : "Query kept in memory for this session.";
    });
    container.querySelectorAll('input[name="prototype-choice"]').forEach(function (choice) {
      choice.checked = choice.value === state.choice;
      choice.addEventListener("change", function () {
        state.choice = choice.value;
        saveState("Prototype choice saved.");
      });
    });
    renderResults();
  }

  function setupLabs() {
    document.querySelectorAll("[data-lab]").forEach(function (container) {
      var kind = container.getAttribute("data-lab");
      if (kind === "brief") setupBriefLab(container);
      if (kind === "verification") setupVerificationLab(container);
      if (kind === "prototypes") setupPrototypesLab(container);
    });
  }

  function notebookMarkdown() {
    var lines = ["# Develop with agents", "", "Prompt notebook exported " + new Date().toLocaleString() + ".", "",
      "Completion is self-reported. Quiz results concern course scenarios. Simulations do not establish real application behavior.", ""];
    lessons.forEach(function (lesson) {
      var notes = Array.prototype.slice.call(lesson.querySelectorAll("[data-note]")).map(function (note) {
        return { label: note.previousElementSibling && note.previousElementSibling.tagName === "LABEL" ? note.previousElementSibling.textContent.trim() : "Notes", value: note.value.trim() };
      }).filter(function (note) { return note.value; });
      lines.push("## " + lessonTitle(lesson), "");
      lines.push("Marked complete: " + (memoryState.completions.indexOf(lesson.id) !== -1 ? "yes" : "no") + ".", "");
      var quiz = memoryState.quizAnswers[lesson.id];
      if (quiz) lines.push("Latest quiz: " + (quiz.correct ? "correct" : "needs another look") + "; attempts: " + quiz.attempts + ".", "");
      var prompt = lesson.querySelector("pre.prompt code");
      if (prompt) lines.push("### Prompt to adapt", "", prompt.textContent.trim(), "");
      notes.forEach(function (note) { lines.push("### " + note.label, "", note.value, ""); });
    });
    lines.push("## Agent brief", "", document.getElementById("brief-prompt").value.trim(), "");
    lines.push("## Prototype decision", "", "Practice query: " + memoryState.labs.prototypes.query,
      "Chosen behavior: " + (memoryState.labs.prototypes.choice || "Not selected"), "");
    return lines.join("\n");
  }

  function exportNotebook() {
    var markdown = notebookMarkdown();
    var fallback = document.getElementById("notebook-fallback");
    document.getElementById("notebook-text").textContent = markdown;
    fallback.open = true;
    try {
      var url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
      var link = document.createElement("a");
      link.href = url;
      link.download = "develop-with-agents-notebook.md";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      announce("Notebook download started. A selectable copy is open below.");
    } catch (error) {
      selectElementText(document.getElementById("notebook-text"));
      announce("The download could not start. The notebook text is selected below.");
    }
  }

  function bindCourseControls() {
    var narrowLayout = window.matchMedia("(max-width: 860px)");
    function updateLessonPicker() {
      document.querySelector(".lesson-picker").open = !narrowLayout.matches;
    }
    updateLessonPicker();
    narrowLayout.addEventListener("change", updateLessonPicker);
    document.getElementById("mode-toggle").addEventListener("click", function () {
      memoryState.mode = memoryState.mode === "guided" ? "read-all" : "guided";
      saveState();
      updateMode();
      showLesson(activeIndex, false);
    });
    document.getElementById("previous-lesson").addEventListener("click", function () { showLesson(activeIndex - 1, true); });
    document.getElementById("next-lesson").addEventListener("click", function () { showLesson(activeIndex + 1, true); });
    document.getElementById("export-notebook").addEventListener("click", exportNotebook);
    var printDetails = [];
    window.addEventListener("beforeprint", function () {
      printDetails = Array.from(document.querySelectorAll("details:not([open])"));
      printDetails.forEach(function (detail) { detail.open = true; });
    });
    window.addEventListener("afterprint", function () {
      printDetails.forEach(function (detail) { detail.open = false; });
      printDetails = [];
    });
  }

  function init() {
    collectLessons();
    makeNavigation();
    memoryState = loadState();
    var restoredIndex = lessons.findIndex(function (lesson) { return lesson.id === memoryState.activeId; });
    activeIndex = restoredIndex === -1 ? 0 : restoredIndex;
    enhancePrompts();
    setupNotes();
    setupQuizzes();
    setupCompletionButtons();
    setupLabs();
    bindCourseControls();
    updateProgress();
    updateMode();
    showLesson(activeIndex, false);
    document.body.setAttribute("data-enhanced", "true");
  }

  init();
}());
