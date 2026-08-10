# Getting workouts onto your watch

## Why there is no direct Garmin or COROS integration

Both vendors gate their workout-push APIs behind partner programs, and neither
is open to a self-hosted personal app:

- **Garmin.** The [Training API](https://developer.garmin.com/gc-developer-program/training-api/)
  publishes structured workouts to devices, but the Connect Developer Program
  [is business-use only and requires a legal entity](https://developer.garmin.com/gc-developer-program/program-faq/),
  and new applications are currently suspended.
- **COROS.** The Training Hub API is partner-only; you apply through COROS.
  Community projects reach it by reverse-engineering the private API, which
  breaks on their release schedule and **invalidates your COROS web session
  every time it logs in** — logging in on the web then invalidates the tool.

Reverse-engineering either one would give you a sync that silently breaks.
Pulse takes two routes that do not depend on anyone's approval.

## Route 1 — intervals.icu (automatic, recommended)

```
Pulse ──> intervals.icu calendar ──> Garmin / COROS / Wahoo / Polar / Suunto
```

intervals.icu already holds official integrations with every major watch
vendor, and [pushes planned workouts to the connected device automatically](https://forum.intervals.icu/t/upload-planned-workouts-to-garmin-connect/1521)
for sessions on today's or tomorrow's calendar. Pulse writes to that calendar;
intervals.icu does the last hop.

**Setup**

1. In Pulse → Settings, add your intervals.icu API key and athlete ID
   (intervals.icu → Settings → Developer).
2. In intervals.icu → Settings → Connections, connect your watch account and
   tick **Upload planned workouts**.

Then from the Plan page: **Send week N to watch**, **Send whole plan**, or the
watch icon on a single session. Sessions are written as calendar events with a
stable `external_id`, so re-sending updates the entry rather than duplicating
it. Each one carries a `.fit` workout attachment, so the interval structure and
targets reach the device rather than just a title.

Turn on **auto-push** in your profile to have the day's sessions pushed
automatically at 05:00.

### What intervals.icu can and cannot read

Their FIT importer does not handle every step type, so the pushed copy is
encoded a little differently from the file you download:

| | pushed to intervals.icu | downloaded `.fit` |
|---|---|---|
| strength sets | timed equivalents | true rep counts |
| swim steps | metres | metres |
| run / bike targets | pace / watts | pace / watts |

intervals.icu logs `Unhandled duration_type: REPS` and drops rep-based steps
entirely, which is why a strength session pushed there shows only the warmup,
rests and cooldown. The download keeps reps, which watches do understand.

If a run shows `null-null for 0km` next to its pace target, that is intervals.icu
being unable to resolve a percentage without your **threshold pace** set under
Settings → Sport Settings. The target itself is structured and reaches the watch.

## Route 2 — `.fit` workout files (manual, no accounts)

The download icon on any session produces a standard FIT workout file.

- **Garmin Connect** — Training → Workouts → Import
- **COROS app** — Training Hub → Workouts → Import

This works with no integration at all, and is the fallback if you would rather
not route through intervals.icu. The same encoder produces the attachment used
in route 1, so the two are identical in content.

Targets are written in the units each sport actually uses: watts for cycling
(derived from your FTP), speed for running and swimming (derived from your
threshold and CSS paces), and plain text for strength.

## Route 3 — calendar subscription

**Copy calendar feed** on the Plan page gives a URL any calendar app can
subscribe to (Apple Calendar, Google Calendar, Outlook):

```
http://<your-host>:8080/api/ai/plan/<id>/calendar.ics
```

Each session becomes an event with the full step list, targets and coach notes
in the description. The feed is read-only and unauthenticated — calendar
clients cannot log in — so treat the URL as private.

## What syncs the other way

Completed activities come in from **Strava** and **intervals.icu** on the
regular sync (every 15 minutes by default). Indoor trainer rides recorded in
Pulse export as activity `.fit` files for upload to Strava or Garmin.

That inbound data feeds back into planning:

- **Where the ramp starts.** The last four weeks of synced activity set the
  opening volume of a new block, so a plan begins at what you are actually
  training rather than at a number from the onboarding form. Setting "training
  now" in your profile overrides it — you may know about travel or illness the
  data cannot see. With fewer than six sessions on record there is not enough
  signal, and the plan falls back to a conservative default.
- **How hard the block opens.** Your form (TSB) at generation time adjusts the
  first week: deeply fatigued (TSB below -25) opens 15% easier, mildly tired
  opens 7% easier, and the ramp catches up afterwards. The peak week is never
  lowered — this shifts the start, not the ceiling.
- **What the coach sees.** Both AI passes are given your observed weekly hours,
  session counts per sport, and CTL/ATL/TSB, so the written rationale matches
  the athlete rather than the questionnaire.
