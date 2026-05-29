const textareas = Array.from(document.querySelectorAll("textarea"));
const output = document.querySelector("#promptOutput");

document.querySelector("#buildPlan").addEventListener("click", () => {
  const [emails, teams, calendar, planner] = textareas.map((textarea) => textarea.value.trim());
  output.textContent = [
    "Create my daily work plan from the information below.",
    "",
    "Please summarize the key signals, identify what needs a reply, list meeting prep, rank priorities, and suggest a practical schedule for today.",
    "",
    "Emails:",
    emails || "- No email input provided.",
    "",
    "Teams:",
    teams || "- No Teams input provided.",
    "",
    "Calendar:",
    calendar || "- No calendar input provided.",
    "",
    "Planner:",
    planner || "- No Planner input provided."
  ].join("\n");
});

document.querySelector("#clearAll").addEventListener("click", () => {
  textareas.forEach((textarea) => {
    textarea.value = "";
  });
  output.textContent = "Add your daily inputs, then build a prompt.";
});
