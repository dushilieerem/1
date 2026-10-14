import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
for (const key of ["window", "document", "navigator", "HTMLElement", "HTMLTextAreaElement", "Node", "MutationObserver", "localStorage", "DOMParser"])
  Object.defineProperty(globalThis, key, { value: dom.window[key], configurable: true });
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
