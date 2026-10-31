/* BIKA Live Stream — accessible visual dropdown adapter.
   Uses the existing native select and dispatches its normal change events.
   This file intentionally does not touch camera APIs, RTSP, AI or permissions. */
(() => {
  'use strict';
  const page = document.querySelector('[data-live-stream-page]');
  if (!page) return;

  const descriptions = {
    main: 'Hikvision · Full resolution, channel 101',
    sub: 'Hikvision · Lower bandwidth, channel 102',
    camo: 'iPhone or local camera via Camo Studio'
  };
  const instances = [];
  let currentOpen = null;

  function closeDropdown(item, restoreFocus = false) {
    if (!item) return;
    item.menu.hidden = true;
    item.button.setAttribute('aria-expanded', 'false');
    item.shell.classList.remove('is-open');
    if (currentOpen === item) currentOpen = null;
    if (restoreFocus && !item.button.disabled) item.button.focus();
  }

  function enhance(select, order) {
    const shell = select.closest('.lsi-select-shell');
    if (!shell || select.dataset.visualEnhanced === 'true') return;
    const id = 'lsi-visual-list-' + order;
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'lsi-source-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-controls', id);
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-label', select.id === 'lsi-camera-stream' ? 'Camera Source' : 'Local Camera Device Index');

    const label = document.createElement('span');
    label.className = 'lsi-source-trigger-label';
    const chevron = document.createElement('span');
    chevron.className = 'lsi-source-chevron';
    chevron.setAttribute('aria-hidden', 'true');
    trigger.append(label, chevron);

    const menu = document.createElement('div');
    menu.id = id;
    menu.className = 'lsi-source-menu';
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', trigger.getAttribute('aria-label'));
    menu.hidden = true;

    const item = { select, shell, button: trigger, label, menu, options: [] };
    for (const nativeOption of Array.from(select.options)) {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = 'lsi-source-option';
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      option.dataset.value = nativeOption.value;
      option.disabled = nativeOption.disabled;
      const title = document.createElement('span');
      title.className = 'lsi-source-option-title';
      title.textContent = nativeOption.textContent.trim();
      option.append(title);
      if (select.id === 'lsi-camera-stream') {
        const hint = document.createElement('span');
        hint.className = 'lsi-source-option-hint';
        hint.textContent = descriptions[nativeOption.value] || '';
        option.append(hint);
      }
      menu.append(option);
      item.options.push(option);
      option.addEventListener('click', () => {
        if (select.disabled || nativeOption.disabled) return;
        const changed = select.value !== nativeOption.value;
        select.value = nativeOption.value;
        update(item);
        closeDropdown(item, true);
        if (changed) select.dispatchEvent(new Event('change', { bubbles: true }));
      });
      option.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          event.preventDefault();
          closeDropdown(item, true);
        } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          focusOption(item, event.key, item.options.indexOf(option));
        } else if (event.key === 'Tab') {
          closeDropdown(item);
        }
      });
    }

    function update(item) {
      const selected = Array.from(select.options).find(option => option.value === select.value);
      item.label.textContent = selected ? selected.textContent.trim() : '';
      item.button.disabled = select.disabled;
      item.shell.classList.toggle('is-disabled', select.disabled);
      for (const option of item.options) {
        const active = option.dataset.value === select.value;
        option.classList.toggle('is-selected', active);
        option.setAttribute('aria-selected', String(active));
      }
      if (select.disabled && currentOpen === item) closeDropdown(item);
    }
    item.update = () => update(item);
    shell.append(trigger, menu);
    select.dataset.visualEnhanced = 'true';
    shell.classList.add('lsi-enhanced-select');
    instances.push(item);
    item.update();
    select.addEventListener('change', item.update);

    trigger.addEventListener('click', () => {
      item.update();
      if (select.disabled) return;
      const wasOpen = currentOpen === item;
      if (currentOpen) closeDropdown(currentOpen);
      if (wasOpen) return;
      menu.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      shell.classList.add('is-open');
      currentOpen = item;
    });
    trigger.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        if (currentOpen === item) { event.preventDefault(); closeDropdown(item); }
      } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) && !select.disabled) {
        event.preventDefault();
        if (currentOpen && currentOpen !== item) closeDropdown(currentOpen);
        menu.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        shell.classList.add('is-open');
        currentOpen = item;
        focusOption(item, event.key, item.options.findIndex(o => o.dataset.value === select.value));
      }
    });
  }

  function focusOption(item, key, currentIndex) {
    const options = item.options.filter(option => !option.disabled);
    if (!options.length) return;
    const current = item.options[currentIndex];
    const at = options.indexOf(current);
    let next = 0;
    if (key === 'End') next = options.length - 1;
    else if (key === 'ArrowUp') next = (at < 0 ? options.length : at) - 1;
    else if (key === 'ArrowDown') next = (at + 1) % options.length;
    options[(next + options.length) % options.length].focus();
  }

  page.querySelectorAll('.lsi-select-shell > select').forEach((select, index) => enhance(select, index));
  document.addEventListener('pointerdown', event => {
    if (currentOpen && !currentOpen.shell.contains(event.target)) closeDropdown(currentOpen);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && currentOpen) closeDropdown(currentOpen, true);
  });
  // The original camera-status poll changes select.value/disabled without
  // firing change; refresh this tiny visual adapter periodically.
  const refresh = window.setInterval(() => {
    instances.forEach(item => item.update());
  }, 700);
  window.addEventListener('pagehide', () => window.clearInterval(refresh), { once: true });
})();
