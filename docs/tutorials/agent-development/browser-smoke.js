async function runAgentTutorialSmoke() {
  "use strict";

  const checks = [];
  const $ = (selector) => {
    const element = document.querySelector(selector);
    if (!element) throw new Error("Missing control: " + selector);
    return element;
  };
  const assert = (condition, label) => {
    if (!condition) throw new Error(label);
    checks.push(label);
  };
  const fill = (selector, value) => {
    const element = $(selector);
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const go = (id) => $('[data-lesson-id="lesson-' + id + '"]').click();
  const visible = () => [...document.querySelectorAll(".lesson")].filter((lesson) => !lesson.hidden);

  assert(document.querySelectorAll("#lessons > .lesson").length === 14, "All 14 lessons load");
  assert(document.querySelectorAll("#lesson-nav button").length === 14, "Every lesson has a navigation control");
  if (document.body.dataset.mode !== "guided") $("#mode-toggle").click();
  go("orientation");
  assert(visible().length === 1 && visible()[0].id === "lesson-orientation", "Guided mode shows the selected lesson");
  assert(document.activeElement === $("#lesson-orientation h2"), "Lesson navigation moves focus to its heading");
  assert($("#previous-lesson").disabled, "Previous is disabled at the first lesson");
  $("#next-lesson").click();
  assert(visible()[0].id === "lesson-brief", "Next opens the next lesson");
  $("#previous-lesson").click();
  assert(visible()[0].id === "lesson-orientation", "Previous returns to the earlier lesson");

  const first = $("#lesson-orientation .quiz");
  first.querySelectorAll("input").forEach((input) => { input.checked = false; });
  first.requestSubmit();
  assert(first.querySelector(".quiz-feedback").textContent.includes("Choose an answer"), "An unanswered quiz gives useful feedback");
  first.querySelector('[value="a"]').click();
  first.requestSubmit();
  assert(first.dataset.result === "incorrect", "A mistaken answer receives corrective feedback");
  assert($("#lesson-orientation .complete-lesson").getAttribute("aria-pressed") !== "true", "Quiz results do not mark lessons complete");

  for (const form of document.querySelectorAll("form.quiz")) {
    const lesson = form.closest(".lesson");
    $('[data-lesson-id="' + lesson.id + '"]').click();
    form.querySelector('[value="' + form.dataset.answer + '"]').click();
    form.requestSubmit();
    assert(form.dataset.result === "correct" && form.querySelector(".quiz-feedback").textContent.length > 35, lesson.id + " supplies explanatory quiz feedback");
  }
  assert($("#next-lesson").disabled, "Next is disabled at the final lesson");
  go("orientation");
  $("#lesson-orientation .complete-lesson").click();
  assert($("#progress-count").textContent.startsWith("1 of 14"), "Completion updates progress separately");
  $("#lesson-orientation .complete-lesson").click();
  assert($("#progress-count").textContent.startsWith("0 of 14"), "Completion can be undone");
  fill("#note-orientation", "Smoke note: I define the outcome and inspect evidence.");
  assert($("#note-orientation").value.includes("inspect evidence"), "Notebook text remains editable");

  go("brief");
  fill("#brief-action", "A reader searches for agents");
  fill("#brief-result", "A published story appears");
  fill("#brief-constraints", "Keep drafts private");
  fill("#brief-evidence", "Observe query and returned titles");
  $("[data-generate]").click();
  assert($("#brief-prompt").value.includes("Keep drafts private") && $("#brief-prompt").value.includes("Observe query"), "The brief builder uses the learner's fields");
  fill("#brief-prompt", $("#brief-prompt").value + "\nKeep the first step read-only.");
  assert($("#brief-prompt").value.includes("first step read-only"), "Generated prompts can be edited");

  go("false-green");
  $("[data-reset]").click();
  $("[data-run]").click();
  assert($(".lab-result").dataset.result === "pass", "The weak status check passes");
  assert($("[data-stories]").textContent.includes("draft"), "The weak pass still exposes the draft");
  $('.verification-lab input[value="exclusion"]').click();
  $("[data-run]").click();
  assert($(".lab-result").dataset.result === "fail" && $("[data-outcomes]").textContent.includes("still visible"), "The stronger check detects the observed defect");
  $("[data-repair]").click();
  assert(document.activeElement === $("[data-run]"), "Repair keeps keyboard focus on an available action");
  $("[data-run]").click();
  assert($(".lab-result").dataset.result === "pass" && !$("[data-stories]").textContent.includes("draft"), "The repaired simulation passes while excluding the draft");
  document.querySelectorAll('.verification-lab input:checked').forEach((input) => input.click());
  $("[data-run]").click();
  assert($(".lab-result").textContent.includes("Choose at least one"), "An empty check selection cannot claim success");
  $("[data-reset]").click();
  assert($("[data-stories]").textContent.includes("draft"), "Reset restores the known wrong state for another attempt");

  go("prototypes");
  fill("#prototype-query", "agents");
  assert($("[data-exact]").textContent === "No match" && $("[data-substring]").textContent.includes("Agents Need Receipts"), "A fragment distinguishes the two search prototypes");
  fill("#prototype-query", "Agents Need Receipts");
  assert($("[data-exact]").textContent.includes("Agents Need Receipts") && $("[data-substring]").textContent.includes("Agents Need Receipts"), "The full title matches both prototypes");
  fill("#prototype-query", "AGENTS NEED RECEIPTS");
  assert($("[data-exact]").textContent === "No match" && $("[data-substring]").textContent.includes("Agents Need Receipts"), "Capitalization exposes the matching-rule difference");
  fill("#prototype-query", "no-such-story-9762");
  assert($("[data-exact]").textContent === "No match" && $("[data-substring]").textContent === "No match", "Absent terms return no matches");
  fill("#prototype-query", "");
  assert($("[data-exact]").textContent === "No match" && document.querySelectorAll("[data-substring] li").length === 3, "Empty input reveals the explicit prototype tradeoff");
  $('input[name="prototype-choice"][value="substring"]').click();

  $("#mode-toggle").click();
  assert(visible().length === 14, "Read-all mode exposes every lesson");
  $("#mode-toggle").click();
  assert(visible().length === 1, "Guided focus can be restored");
  $("#export-notebook").click();
  assert($("#notebook-fallback").open && $("#notebook-text").textContent.includes("Smoke note"), "Export retains notes in a selectable fallback");
  assert($("#notebook-text").textContent.includes("Keep drafts private"), "Export retains the edited work brief");
  assert($("#notebook-text").textContent.includes("Use poteto-mode"), "Export includes reusable lesson prompts");
  const saved = JSON.parse(localStorage.getItem("mindpattern.agent-development.tutorial.v1"));
  assert(saved.notes.orientation.includes("Smoke note") && saved.quizAnswers["lesson-orientation"].correct, "Notes and quiz results reach browser storage");
  assert(saved.labs.prototypes.choice === "substring", "The prototype decision reaches browser storage");
  go("orientation");
  return { passed: checks.length, checks, reloadExpected: { activeId: "lesson-orientation", note: "Smoke note", correctQuiz: true } };
}
