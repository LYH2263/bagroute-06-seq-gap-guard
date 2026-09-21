/** Fired when stops of a route are added/renumbered/moved/resequenced. */
export const STOPS_CHANGED = "bagroute:stops-changed";

export function notifyStopsChanged() {
  window.dispatchEvent(new Event(STOPS_CHANGED));
}
