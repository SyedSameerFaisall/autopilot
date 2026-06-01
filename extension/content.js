const APPLY_PILOT_ATTRIBUTE = "data-applypilot-id";

function getLabel(element) {
  return (
    element.labels?.[0]?.innerText ||
    element.getAttribute("aria-label") ||
    element.getAttribute("placeholder") ||
    element.name ||
    element.id ||
    "Unlabelled field"
  ).trim();
}

function getFieldType(element) {
  const tag = element.tagName.toLowerCase();
  if (tag === "textarea" || tag === "select") return tag;
  return element.type || tag;
}

function collectFields() {
  return Array.from(document.querySelectorAll("input, textarea, select")).map((element, index) => {
    const locatorId = `applypilot-${index}`;
    element.setAttribute(APPLY_PILOT_ATTRIBUTE, locatorId);
    return {
      locator_id: locatorId,
      label: getLabel(element),
      name: element.name || element.id || locatorId,
      field_type: getFieldType(element),
      required: Boolean(element.required || element.getAttribute("aria-required") === "true"),
    };
  });
}

function fillPlan(fields) {
  const filled = [];
  const skipped = [];
  for (const field of fields) {
    const element = document.querySelector(`[${APPLY_PILOT_ATTRIBUTE}="${field.locator_id}"]`);
    if (!element || !field.mapped_value || ["checkbox", "radio", "file", "submit", "button"].includes(field.field_type)) {
      skipped.push(field.label);
      continue;
    }
    element.value = field.mapped_value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    filled.push(field.label);
  }
  return { filled, skipped, submitted: false };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "APPLYPILOT_SCAN") sendResponse({ fields: collectFields(), source_url: window.location.href });
  if (message.type === "APPLYPILOT_FILL") sendResponse(fillPlan(message.fields));
});
