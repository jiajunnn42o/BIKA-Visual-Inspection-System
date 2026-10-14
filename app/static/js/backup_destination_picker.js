(() => {
  "use strict";
  const page = document.querySelector("[data-about-system-page]");
  const modal = document.querySelector("[data-destination-modal]");
  if (!page || !modal) return;

  const browse = modal.querySelector("[data-bika-browse-backup-folder]");
  const field = modal.querySelector("[data-custom-destination]");
  const feedback = modal.querySelector("[data-bika-folder-feedback]");
  const customRadio = modal.querySelector('[data-destination-option][value="Custom Server Folder"]');
  const endpoint = page.dataset.backupFolderPickerUrl;
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  if (!browse || !field || !customRadio || !endpoint) return;

  function report(message, isError = false) {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.dataset.error = isError ? "true" : "false";
  }

  let selecting = false;
  async function selectFolder() {
    if (selecting) return;
    selecting = true;
    browse.disabled = true;
    browse.textContent = "Opening…";
    report("Select the directory on this Windows computer.");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {"X-CSRFToken": csrfToken, "Content-Type": "application/json"},
        body: "{}",
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) throw new Error(result.message || "Unable to open folder picker.");
      if (result.cancelled) {
        report("Folder selection cancelled.");
        return;
      }
      if (typeof result.path !== "string" || !result.path) throw new Error("No folder was returned.");
      customRadio.checked = true;
      customRadio.dispatchEvent(new Event("change", {bubbles: true}));
      field.value = result.path;
      field.title = result.path;
      field.dispatchEvent(new Event("input", {bubbles: true}));
      report("Folder selected. Click Apply, then Save Schedule to save it.");
    } catch (error) {
      report(error.message || "Could not open the folder picker.", true);
    } finally {
      selecting = false;
      browse.disabled = false;
      browse.textContent = "Browse Folder";
    }
  }

  browse.addEventListener("click", selectFolder);
  field.addEventListener("click", selectFolder);
  // Selecting the Custom Folder option starts the Windows picker directly.
  customRadio.addEventListener("change", () => {
    if (customRadio.checked && !field.value.trim()) selectFolder();
  });
})();
