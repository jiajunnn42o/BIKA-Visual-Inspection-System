/* BIKA Backup Schedule pickers.
 * Additive enhancement only. All values remain on the existing native form
 * controls, so about_system.js continues to own frequency visibility and saving.
 */
(() => {
  "use strict";
  const modal = document.querySelector('[data-schedule-modal]');
  if (!modal || modal.dataset.bikaSchedulePickersReady === "true") return;
  modal.dataset.bikaSchedulePickersReady = "true";

  const fields = Array.from(modal.querySelectorAll(
    'select[data-schedule-frequency], select[data-schedule-weekday], select[data-schedule-month-day]'
  ));
  const nativeTime = modal.querySelector('input[type="time"][data-schedule-time]');
  if (fields.length !== 3 || !nativeTime) return;

  let active = null;
  const nativeLabel = (option) => (option.textContent || "").trim();

  function closePopover(restoreFocus = false) {
    if (!active) return;
    const { trigger, menu, wrapper } = active;
    if (menu && menu.parentNode) menu.remove();
    wrapper?.classList.remove('is-open');
    trigger?.setAttribute('aria-expanded', 'false');
    active = null;
    if (restoreFocus) trigger?.focus();
  }

  function positionPopover() {
    if (!active) return;
    const { trigger, menu } = active;
    if (!trigger || !menu || !document.body.contains(trigger)) { closePopover(); return; }
    const rect = trigger.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight;
    const margin = 10;
    const left = Math.max(margin, Math.min(rect.left, viewportWidth - margin - Math.min(rect.width, viewportWidth - margin * 2)));
    const width = Math.max(180, Math.min(rect.width, viewportWidth - margin * 2));
    menu.style.left = `${left}px`;
    menu.style.width = `${width}px`;
    menu.style.maxHeight = `${Math.max(110, Math.min(310, viewportHeight - 2 * margin))}px`;
    menu.style.visibility = 'hidden';
    const naturalHeight = Math.min(menu.scrollHeight, 310);
    const below = viewportHeight - rect.bottom - margin;
    const above = rect.top - margin;
    const openUp = below < Math.min(naturalHeight, 170) && above > below;
    let top, available;
    if (openUp) {
      available = Math.max(90, above - 7);
      top = Math.max(margin, rect.top - 7 - Math.min(naturalHeight, available));
    } else {
      available = Math.max(90, below - 7);
      top = Math.max(margin, rect.bottom + 7);
    }
    menu.style.top = `${top}px`;
    menu.style.maxHeight = `${Math.min(310, available)}px`;
    menu.style.visibility = 'visible';
  }

  function makeChevron() {
    const span = document.createElement('span');
    span.className = 'bika-schedule-chevron';
    span.setAttribute('aria-hidden', 'true');
    return span;
  }

  function buildSelect(native) {
    native.classList.add('bika-schedule-native');
    native.setAttribute('tabindex', '-1');
    const wrapper = document.createElement('div');
    wrapper.className = 'bika-schedule-select';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'bika-schedule-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-label', native.closest('label')?.querySelector('span')?.textContent?.trim() || 'Select value');
    const valueText = document.createElement('span');
    valueText.className = 'bika-schedule-trigger-text';
    trigger.append(valueText, makeChevron());
    wrapper.appendChild(trigger);
    native.insertAdjacentElement('afterend', wrapper);

    const sync = () => {
      const option = native.selectedOptions[0];
      valueText.textContent = option ? nativeLabel(option) : 'Select';
    };
    native.addEventListener('change', sync);
    sync();

    const open = () => {
      if (active?.trigger === trigger) { closePopover(); return; }
      closePopover();
      sync();
      const menu = document.createElement('div');
      menu.className = 'bika-schedule-popover bika-schedule-options';
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('aria-label', trigger.getAttribute('aria-label'));
      const many = native.options.length > 9;
      if (many) menu.classList.add('bika-schedule-scroll');
      for (const option of native.options) {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'bika-schedule-option';
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(native.value === option.value));
        if (native.value === option.value) item.classList.add('is-selected');
        item.textContent = nativeLabel(option);
        item.addEventListener('click', () => {
          native.value = option.value;
          native.dispatchEvent(new Event('change', { bubbles: true }));
          sync();
          closePopover();
          trigger.focus();
        });
        menu.appendChild(item);
      }
      document.body.appendChild(menu);
      wrapper.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      active = { trigger, menu, wrapper };
      positionPopover();
      const selected = menu.querySelector('.is-selected');
      selected?.scrollIntoView({ block: 'nearest' });
    };
    trigger.addEventListener('click', open);
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        if (!active || active.trigger !== trigger) open();
        const options = Array.from(active?.menu.querySelectorAll('.bika-schedule-option') || []);
        const selectedIndex = Math.max(0, native.selectedIndex);
        options[Math.min(options.length - 1, Math.max(0, selectedIndex + (event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0)))]?.focus();
      }
    });
    return sync;
  }

  const syncSelects = fields.map(buildSelect);

  function minutesToLabel(time) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(time || '');
    if (!match) return 'Choose time';
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    const twelve = hour % 12 || 12;
    return `${String(twelve).padStart(2, '0')}:${String(minute).padStart(2, '0')} ${hour >= 12 ? 'PM' : 'AM'}`;
  }
  nativeTime.classList.add('bika-schedule-native');
  nativeTime.setAttribute('tabindex', '-1');
  const timeWrapper = document.createElement('div');
  timeWrapper.className = 'bika-schedule-select bika-schedule-time-wrap';
  const timeTrigger = document.createElement('button');
  timeTrigger.className = 'bika-schedule-trigger';
  timeTrigger.type = 'button';
  timeTrigger.setAttribute('aria-label', 'Choose backup time');
  timeTrigger.setAttribute('aria-haspopup', 'dialog');
  timeTrigger.setAttribute('aria-expanded', 'false');
  const timeText = document.createElement('span');
  timeText.className = 'bika-schedule-trigger-text';
  const icon = document.createElement('span');
  icon.className = 'bika-schedule-clock';
  icon.setAttribute('aria-hidden', 'true');
  icon.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
  timeTrigger.append(timeText, icon);
  timeWrapper.appendChild(timeTrigger);
  nativeTime.insertAdjacentElement('afterend', timeWrapper);
  const syncTime = () => { timeText.textContent = minutesToLabel(nativeTime.value); };
  nativeTime.addEventListener('change', syncTime);
  nativeTime.addEventListener('input', syncTime);
  syncTime();

  function openTime() {
    if (active?.trigger === timeTrigger) { closePopover(); return; }
    closePopover();
    const match = /^(\d{1,2}):(\d{2})$/.exec(nativeTime.value || '') || ['', '02', '00'];
    const hour24 = Number(match[1]);
    const minute = Number(match[2]);
    const menu = document.createElement('div');
    menu.className = 'bika-schedule-popover bika-schedule-time-panel';
    menu.setAttribute('role', 'dialog');
    menu.setAttribute('aria-label', 'Choose backup time');
    const controls = document.createElement('div');
    controls.className = 'bika-schedule-time-grid';
    // Selection-only time controls: no editable text or numeric inputs.
    // A bounded scroll list provides every hour (01–12) and minute (00–59).
    function choiceColumn(label, values, initiallySelected) {
      const field = document.createElement('div');
      field.className = 'bika-schedule-time-choice';
      const heading = document.createElement('span');
      heading.className = 'bika-schedule-time-heading';
      heading.textContent = label;
      const list = document.createElement('div');
      list.className = 'bika-schedule-time-list';
      list.setAttribute('role', 'listbox');
      list.setAttribute('aria-label', label);
      list.tabIndex = 0;
      let selected = initiallySelected;
      const buttons = [];
      function choose(value, focus = false) {
        selected = value;
        for (const button of buttons) {
          const isCurrent = Number(button.dataset.value) === value;
          button.classList.toggle('is-selected', isCurrent);
          button.setAttribute('aria-selected', String(isCurrent));
          button.tabIndex = isCurrent ? 0 : -1;
          if (isCurrent && focus) {
            button.scrollIntoView({ block: 'nearest' });
            button.focus({ preventScroll: true });
          }
        }
      }
      for (const value of values) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'bika-schedule-time-choice-option';
        button.textContent = String(value).padStart(2, '0');
        button.dataset.value = String(value);
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', 'false');
        button.addEventListener('click', () => choose(value));
        button.addEventListener('keydown', event => {
          const delta = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
          if (!delta) return;
          event.preventDefault();
          const index = values.indexOf(selected);
          choose(values[Math.min(values.length - 1, Math.max(0, index + delta))], true);
        });
        buttons.push(button);
        list.appendChild(button);
      }
      choose(initiallySelected);
      field.append(heading, list);
      controls.appendChild(field);
      return {
        get value() { return selected; },
        focusSelected() {
          const option = buttons.find(b => Number(b.dataset.value) === selected);
          if (option) {
            // Center the current selection in its own scroll list only.
            list.scrollTop = option.offsetTop - list.offsetTop - (list.clientHeight - option.offsetHeight) / 2;
          }
        }
      };
    }
    const h = choiceColumn('Hour', Array.from({ length: 12 }, (_, i) => i + 1), hour24 % 12 || 12);
    const m = choiceColumn('Minute', Array.from({ length: 60 }, (_, i) => i), minute);
    const ampm = document.createElement('div');
    ampm.className = 'bika-schedule-time-ampm';
    const label = document.createElement('span');
    label.textContent = 'Period';
    ampm.appendChild(label);
    let isPM = hour24 >= 12;
    const switcher = document.createElement('div');
    switcher.className = 'bika-schedule-time-period';
    for (const period of ['AM', 'PM']) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = period;
      b.className = 'bika-schedule-period-button';
      b.setAttribute('aria-pressed', String((period === 'PM') === isPM));
      b.addEventListener('click', () => {
        isPM = (period === 'PM');
        for (const button of switcher.children) button.setAttribute('aria-pressed', String((button.textContent === 'PM') === isPM));
      });
      switcher.appendChild(b);
    }
    ampm.appendChild(switcher);
    controls.appendChild(ampm);
    const done = document.createElement('button');
    done.type = 'button';
    done.className = 'bika-schedule-time-done';
    done.textContent = 'Done';
    function applyTime() {
      const converted = (h.value % 12) + (isPM ? 12 : 0);
      nativeTime.value = `${String(converted).padStart(2, '0')}:${String(m.value).padStart(2, '0')}`;
      nativeTime.dispatchEvent(new Event('input', { bubbles: true }));
      nativeTime.dispatchEvent(new Event('change', { bubbles: true }));
      syncTime();
      closePopover();
      timeTrigger.focus();
    }
    done.addEventListener('click', applyTime);
    menu.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); applyTime(); }
    });
    menu.append(controls, done);
    document.body.appendChild(menu);
    timeWrapper.classList.add('is-open');
    timeTrigger.setAttribute('aria-expanded', 'true');
    active = { trigger: timeTrigger, menu, wrapper: timeWrapper };
    positionPopover();
    h.focusSelected();
    m.focusSelected();
  }
  timeTrigger.addEventListener('click', openTime);

  // about_system.js parses the saved schedule on opening and sets .value
  // programmatically. Refresh our visible text AFTER that existing handler.
  document.querySelector('[data-open-schedule]')?.addEventListener('click', () => {
    closePopover();
    syncSelects.forEach(sync => sync());
    syncTime();
  });
  for (const attr of ['data-close-schedule', 'data-cancel-schedule', 'data-apply-schedule']) {
    modal.querySelector(`[${attr}]`)?.addEventListener('click', () => closePopover());
  }
  modal.addEventListener('click', event => { if (event.target === modal) closePopover(); });
  document.addEventListener('pointerdown', (event) => {
    if (!active) return;
    if (!active.trigger.contains(event.target) && !active.menu.contains(event.target)) closePopover();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && active) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closePopover(true);
    }
  }, true);
  window.addEventListener('resize', positionPopover);
  window.addEventListener('scroll', positionPopover, true);
})();
