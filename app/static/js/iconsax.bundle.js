// node_modules/iconsax/dist/index.js
var manifestPromise = null;
var nameIndexPromise = null;
function loadManifest() {
  if (!manifestPromise) {
    manifestPromise = fetch(new URL("./manifest.json", import.meta.url)).then((r) => {
      if (!r.ok) throw new Error(`manifest.json ${r.status}`);
      return r.json();
    });
  }
  return manifestPromise;
}
function getNameIndex() {
  if (!nameIndexPromise) {
    nameIndexPromise = loadManifest().then((manifest) => {
      const index = /* @__PURE__ */ new Map();
      for (const [name, meta] of Object.entries(manifest)) {
        index.set(name.toLowerCase(), { name, ...meta });
      }
      return index;
    });
  }
  return nameIndexPromise;
}
var categoryPromises = /* @__PURE__ */ new Map();
function loadCategory(category) {
  if (!categoryPromises.has(category)) {
    categoryPromises.set(
      category,
      fetch(new URL(`./data/${category}.json`, import.meta.url)).then((r) => {
        if (!r.ok) throw new Error(`data/${category}.json ${r.status}`);
        return r.json();
      })
    );
  }
  return categoryPromises.get(category);
}
async function resolveFreeIcon(name, style) {
  const index = await getNameIndex();
  const entry = index.get(name.toLowerCase());
  if (!entry) return null;
  const finalStyle = entry.styles.includes(style) ? style : entry.styles[0];
  const data = await loadCategory(entry.category);
  return data[entry.name]?.[finalStyle] || null;
}
var proIcons = /* @__PURE__ */ new Map();
var pendingProInstances = /* @__PURE__ */ new Set();
function resolveProIcon(name, style) {
  const key = name.toLowerCase();
  const exact = proIcons.get(`${key}:${style}`);
  if (exact) return exact;
  for (const [k, svg] of proIcons) {
    if (k.startsWith(`${key}:`)) return svg;
  }
  return null;
}
function applySvgProps(svg, size, color) {
  const withSize = svg.replace(/<svg([^>]*)>/, (match, attrs) => {
    let next = attrs.replace(/\swidth="[^"]*"/, "").replace(/\sheight="[^"]*"/, "").replace(/\sstyle="[^"]*"/, "");
    return `<svg${next} width="${size}" height="${size}" style="color:${color}">`;
  });
  return withSize.replace(/(fill|stroke)="(?!none)[^"]*"/g, '$1="currentColor"');
}
var MISSING_ICON_MSG = `[iconsax] Icon "%s" (%s) not found. Check the name, or run "npx iconsax sync" if it's a Pro icon.`;
var IconsaxIcon = class extends HTMLElement {
  static get observedAttributes() {
    return ["name", "type", "size", "color", "pro"];
  }
  connectedCallback() {
    this._scheduleRender();
  }
  disconnectedCallback() {
    pendingProInstances.delete(this);
  }
  attributeChangedCallback() {
    if (this.isConnected) this._scheduleRender();
  }
  // The parser sets several attributes in a row when mounting the element —
  // each one fires attributeChangedCallback separately. Without this we'd
  // render (and, for free icons, fetch) once per attribute instead of once.
  _scheduleRender() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    queueMicrotask(() => {
      this._renderScheduled = false;
      this._render();
    });
  }
  async _render() {
    const token = this._token = /* @__PURE__ */ Symbol();
    const name = this.getAttribute("name");
    if (!name) {
      this.innerHTML = "";
      return;
    }
    const type = this.getAttribute("type") || "linear";
    const size = this.getAttribute("size") || "24";
    const color = this.getAttribute("color") || "currentColor";
    const isPro = this.hasAttribute("pro");
    let svg = null;
    if (isPro) {
      svg = resolveProIcon(name, type);
      if (svg) {
        pendingProInstances.delete(this);
      } else {
        pendingProInstances.add(this);
        console.warn(
          `[iconsax] Pro icon "${name}" (${type}) not resolved yet. It will re-render automatically once you call registerProIcons(). If you already did, run "npx iconsax sync" with your API key.`
        );
      }
    } else {
      try {
        svg = await resolveFreeIcon(name, type);
      } catch (err) {
        console.warn(`[iconsax] Error loading "${name}":`, err.message);
      }
      if (this._token !== token) return;
      if (!svg) console.warn(MISSING_ICON_MSG.replace("%s", name).replace("%s", type));
    }
    this.innerHTML = svg ? applySvgProps(svg, size, color) : "";
  }
};
if (typeof customElements !== "undefined" && !customElements.get("iconsax-icon")) {
  customElements.define("iconsax-icon", IconsaxIcon);
}
