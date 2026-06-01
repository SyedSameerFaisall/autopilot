const APPLY_PILOT_ATTRIBUTE = "data-applypilot-id";

function textFromIds(ids) {
  return (ids || "")
    .split(/\s+/)
    .map((id) => document.getElementById(id)?.innerText || document.getElementById(id)?.textContent || "")
    .join(" ")
    .trim();
}

function getQuestionLabel(element) {
  const container = element.closest('[role="listitem"], .Qr7Oae');
  return (
    container?.querySelector('[role="heading"]')?.innerText ||
    container?.querySelector(".M7eMe")?.innerText ||
    ""
  ).trim();
}

function getLabel(element) {
  return (
    element.labels?.[0]?.innerText ||
    getQuestionLabel(element) ||
    textFromIds(element.getAttribute("aria-labelledby")) ||
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

function isGoogleFormsPage() {
  return window.location.hostname === "docs.google.com" && window.location.pathname.includes("/forms/");
}

function isGoogleFormsEditor() {
  return isGoogleFormsPage() && /\/edit\/?$/.test(window.location.pathname);
}

function isRelevant(element) {
  return (
    !element.disabled &&
    element.getClientRects().length > 0 &&
    !["hidden", "submit", "button", "reset"].includes(getFieldType(element))
  );
}

function collectFields() {
  return Array.from(document.querySelectorAll("input, textarea, select")).filter((element) => {
    if (!isRelevant(element)) return false;
    if (isGoogleFormsPage()) return Boolean(element.closest('[role="listitem"], .Qr7Oae'));
    return true;
  }).map((element, index) => {
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

function setNativeValue(element, value) {
  const prototype =
    element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : element instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
  if (setter) setter.call(element, value);
  else element.value = value;
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
    setNativeValue(element, field.mapped_value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    filled.push(field.label);
  }
  return { filled, skipped, submitted: false };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "APPLYPILOT_SCAN") {
    if (isGoogleFormsEditor()) {
      sendResponse({ error: "This is the Google Forms editor. Open Preview, then run ApplyPilot on the respondent form." });
      return;
    }
    sendResponse({ fields: collectFields(), source_url: window.location.href });
  }
  if (message.type === "APPLYPILOT_FILL") sendResponse(fillPlan(message.fields));
});
