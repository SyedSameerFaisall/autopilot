const backendInput = document.getElementById("backend");
const fillButton = document.getElementById("fill");
const status = document.getElementById("status");

backendInput.value = localStorage.getItem("applypilot-backend") || backendInput.value;

function show(message, className = "") {
  status.className = className;
  status.textContent = message;
}

async function messageActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("Open an application form in the active tab.");
  return chrome.tabs.sendMessage(tab.id, message);
}

fillButton.addEventListener("click", async () => {
  fillButton.disabled = true;
  const backend = backendInput.value.replace(/\/$/, "");
  localStorage.setItem("applypilot-backend", backend);
  try {
    show("Scanning the current page...");
    const scan = await messageActiveTab({ type: "APPLYPILOT_SCAN" });
    const response = await fetch(`${backend}/api/browser-extension/fill-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scan),
    });
    if (!response.ok) throw new Error("ApplyPilot backend is unavailable or rejected the page.");
    const plan = await response.json();
    const result = await messageActiveTab({ type: "APPLYPILOT_FILL", fields: plan.fields });
    show(`${result.filled.length} fields filled. ${result.skipped.length} left for review. Nothing submitted.`, "success");
  } catch (error) {
    show(error.message || "Could not fill this page.", "error");
  } finally {
    fillButton.disabled = false;
  }
});
