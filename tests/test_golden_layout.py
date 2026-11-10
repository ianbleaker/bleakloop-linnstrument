"""The #116 refactor's fence: every view's buttons and holds behave as captured. Temporary."""

import json

from tests.golden import capture


def test_every_view_matches_the_golden_capture():
    expected = json.loads(capture.FIXTURE.read_text())
    actual = json.loads(json.dumps(capture.run(), sort_keys=True))
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(key for key in set(expected) & set(actual) if expected[key] != actual[key])
    report = [f"missing: {key}" for key in missing[:10]] + [f"extra: {key}" for key in extra[:10]]
    for key in changed[:10]:
        was, now = expected[key], actual[key]
        if isinstance(was, dict) and "steps" not in was:  # a frame: only the pads that differ
            pads = sorted(pad for pad in set(was) | set(now) if was.get(pad) != now.get(pad))
            was, now = {pad: was.get(pad) for pad in pads}, {pad: now.get(pad) for pad in pads}
        report.append(f"changed: {key}\n  was {json.dumps(was)[:600]}\n  now {json.dumps(now)[:600]}")
    assert not (missing or extra or changed), f"{len(changed)} changed\n" + "\n".join(report)
