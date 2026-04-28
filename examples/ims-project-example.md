# IMS Adjustments — Proposed Features and Improvements

Below are proposed changes to the Inventory Management System (IMS). The
document groups related work under broad themes; under each theme are the
individual pieces of functionality, and under those are the smaller steps
required to deliver them.

---

## Real-Time Stock Visibility

We want warehouse and trading users to see stock levels that match the
physical warehouse within a minute of any movement, ending the recurring
"phantom stock" disagreements between Trading and Operations.

### Live stock counter on the IMS dashboard
Traders need the dashboard tile to update without a page refresh so that
they quote against current stock rather than a ten-minute-old snapshot.

- Add a real-time channel (SignalR or WebSockets) that carries stock-change
  events to connected clients.
- Emit events from the warehouse adjustment service on every inbound,
  outbound, and transfer movement.
- Update the dashboard tile component to subscribe to the channel and
  re-render when an event arrives.
- Add reconnection and back-off logic so the tile recovers gracefully when
  the warehouse network drops.

### Bonded vs. duty-paid split on every SKU view
Operations leads need each SKU page to show bonded and duty-paid counts
separately so that bonded stock isn't accidentally allocated to a
duty-paid order.

- Extend the stock read model to track bonded and duty-paid quantities
  independently.
- Update the SKU detail screen to show both values side by side.
- Backfill the split for existing SKUs from historical movement data.

### Low-stock alerting
Buyers want to be warned when a watched SKU drops below a threshold so they
can re-purchase before going out of stock.

- Add a place to store per-user, per-SKU thresholds.
- Run an hourly check that compares current stock against thresholds and
  queues alerts for any breaches.
- Deliver alerts by email and as in-app notifications.
- Build a settings screen where users can manage their thresholds.

---

## Faster, More Accurate Stock Adjustments

We want to cut the time it takes to log an adjustment from roughly four
minutes to under a minute, while reducing data-entry mistakes that show up
at month-end reconciliation.

### Bulk adjustment via CSV upload
Warehouse admins should be able to upload a spreadsheet of adjustments
instead of typing 200 lines in by hand after a stock-take.

- Define a clear CSV layout and provide a downloadable template.
- Validate every row server-side (wine identifier, quantity, location,
  reason).
- Process the batch atomically — either all rows succeed or none are saved.
- Return a clear error report identifying any rejected rows and why.

### Reason codes with required notes
Auditors want every adjustment to carry a structured reason and a free-text
note so they can run reports on shrinkage causes.

- Set up a reference list of reason codes (damage, miscount, theft, …).
- Replace the free-text "reason" field in the UI with a dropdown plus a
  note field.
- Make the note mandatory for sensitive reasons such as theft and damage.

### Mobile barcode scanning for adjustments
Warehouse pickers want to scan a bottle barcode on their phone to log an
adjustment, instead of walking back to a desktop terminal.

- Build a mobile-friendly screen optimised for camera scanning.
- Add a lookup that maps the barcode to the wine identifier.
- Queue adjustments locally on the device when warehouse Wi-Fi drops, and
  flush them once connectivity returns.

---

## Audit Trail and Compliance

Every change to stock or master data should be traceable to a user, a
timestamp, and a reason for at least seven years, so that the next external
audit can be passed without stitching logs together by hand.

### Immutable adjustment history
Compliance owners want adjustment history to be append-only so that nobody
can quietly rewrite the past.

- Move adjustments into an append-only ledger.
- Remove update and delete permissions on the ledger at the database level.
- Offer a "correction" flow that posts a compensating entry instead of
  editing the original.

### User activity export
Admins should be able to download a signed report of who did what, when.

- Add an admin-only screen that exports user activity.
- Produce a CSV with timestamp, user, entity, and before/after values.
- Sign the export with a checksum so tampering is detectable.

---

## Integrations

The goal is to stop copying data between IMS and other systems by hand.

### Two-way sync with the trading platform
- Agree a clear contract for stock reservation and release events.
- Publish those events from IMS on the message bus.
- Consume shipment events from the trading platform and decrement stock
  automatically.
- Use idempotency keys so re-delivered messages don't double-count.

### Finance system journal feed
- Generate a nightly export of stock value movements as accounting journal
  entries.
- Drop the file onto the finance system's ingest location.
- Produce a reconciliation report listing any entries the finance system
  rejected.

---

## User Experience Improvements

Smaller changes that reduce daily friction for the 30+ users who live in
IMS all day.

### Saved views and filters
Users want to save their filter combinations so they don't rebuild them
every morning.

- Store saved views per user.
- Provide UI to save, rename, and delete views.
- Allow a default view to be picked on login.

### Dark mode
- Audit the existing colour variables.
- Add a theme toggle in the user menu.
- Remember the user's preference in their profile.

### Keyboard shortcuts for power users
- Define a set of shortcuts for common navigation actions.
- Show a help overlay when the user presses `?`.

---

## Defects to Fix

### Negative stock allowed under rapid concurrent adjustments
Two adjustments submitted within roughly fifty milliseconds can both pass
the "is there enough stock?" check and push the SKU below zero.

- Reproduce the issue with a load-test script.
- Add a row-level lock or an optimistic concurrency check on the stock row.
- Audit historical data for SKUs that went negative and flag them for ops
  review.

### CSV exports use local timezone instead of UTC
Reports generated from London and Singapore show different timestamps for
the same adjustment, which confuses global operations.

- Standardise every exported timestamp to UTC in ISO-8601 format.
- Add a clear "timezone: UTC" header note to exported files.

### Search ignores accented characters on producer names
Searching for "Beaucastel" does not match "Beaucastél" in the catalogue.

- Switch the search index to a Unicode-folding analyzer.
- Re-index the catalogue so existing entries pick up the new behaviour.

---

The themes, items, and supporting steps above are intentionally written in
plain language — they describe the desired outcome and the work needed to
get there, and can be transferred into whichever tracking tool the team
uses.
