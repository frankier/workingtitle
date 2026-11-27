"""Commit numeric range-slider changes to a Bokeh server session."""

import json
from math import isfinite

from bokeh.events import DocumentReady
from bokeh.models import CustomJS, Div


def on_range_commit(doc, slider, callback, *, pause_ms=100, name=None):
    """Call callback(low, high) on release or pause, with one browser request in flight.

    Python assignments to the slider call the callback directly. Browser previews
    stay local; the hidden request model belongs to the slider's callback graph.
    """
    if type(pause_ms) is not int or pause_ms < 0:
        raise ValueError("pause_ms must be a nonnegative integer")
    last_value = tuple(slider.value)

    def deliver(low, high):
        nonlocal last_value
        if (low, high) != last_value:
            callback(low, high)
            last_value = (low, high)

    slider.on_change("value", lambda attr, old, new: deliver(*new))
    if doc.session_context is None:
        return
    slider.syncable = False
    request = Div(text="", visible=False, name=name)
    last_sequence = 0

    def receive(attr, old, new):
        nonlocal last_sequence
        try:
            sequence, low, high = json.loads(new)
        except (TypeError, ValueError):
            return
        if type(sequence) is not int or sequence <= last_sequence:
            return
        last_sequence = sequence
        try:
            if (
                type(low) in (int, float)
                and type(high) in (int, float)
                and slider.start <= low <= high <= slider.end
                and isfinite(low)
                and isfinite(high)
            ):
                deliver(low, high)
        finally:
            request.tags = [sequence]

    request.on_change("text", receive)
    notify = CustomJS(
        args=dict(slider=slider, request=request, pause=pause_ms, initial=last_value),
        code="""
        let timer, pending, sent, view, sequence, inFlight = false
        export default ({slider, request, pause, initial}, sender) => {
            sequence ??= request.tags[0] ?? 0
            sent ??= initial
            function sendLatest() {
                if (inFlight || !pending) return
                const range = pending
                pending = undefined
                if (range.every((v, i) => v === sent[i])) return
                sent = range
                inFlight = true
                request.text = JSON.stringify([++sequence, ...range])
            }
            function commit() {
                clearTimeout(timer)
                pending = [...slider.value]
                sendLatest()
            }
            if (sender === request) {
                if (request.tags[0] === sequence) {
                    inFlight = false
                    sendLatest()
                }
                return
            }
            if (!view) {
                view = Bokeh.index.find_one(slider)
                if (!view) return
                // A release may return to the previous value_throttled after
                // a pause committed an intermediate value.
                const track = view._noUiSlider
                if (track) track.on("change.workingtitleRange", commit)
                else slider.properties.value_throttled.change.connect(commit)
                view.removed.connect(() => {
                    clearTimeout(timer)
                    pending = undefined
                    if (track) track.off(".workingtitleRange")
                    else slider.properties.value_throttled.change.disconnect(commit)
                    view = undefined
                })
            }
            if (sender === slider) {
                pending = undefined
                clearTimeout(timer)
                timer = setTimeout(commit, pause)
            }
        }
    """,
    )
    doc.js_on_event(DocumentReady, notify)
    slider.js_on_change("value", notify)
    request.js_on_change("tags", notify)
