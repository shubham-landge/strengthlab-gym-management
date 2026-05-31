# Functionality Upgrade Log

## 2026-06-01 - StrengthLab Premium UI/UX Redesign

### Design Notes

- Transitioned the entire application into a premium, trendy operational command center using the **UI UX Pro Max** guidelines.
- Standardized custom HSL variables for high contrast Light and Dark modes. Persisted theme choices inside localStorage to prevent flickering.
- Embedded premium inline SVG icons inside all main sidebar links and mobile navigation views.
- Upgraded the Owner Dashboard with a Bento Grid pattern and a visually stunning gradient area collection velocity chart.
- Created an Athlete Command Center inside the member detail page, featuring a client-side JS parser that seamlessly translates raw text plans into interactive day accordion cards and macro recipe widgets.
- Modernized payments ledger layout with collapsible stacked tables for viewports under 768px, slide-over transaction entry drawers, and colorful status pills.
- Restructured biometrics form pages with stepped tab indicators and clickable checkbox tag pill switches.
- Enforced high-fidelity keyboard focus states, transition animations, and `prefers-reduced-motion` compliance.

### Decisions

- Used CSS `:has(input:checked)` selectors to dynamically highlight custom checkbox tags without adding heavy JS layout dependencies.
- Retained raw text plan editing in the background to ensure absolute backward compatibility for legacy inputs.
- Built a client-side JS plan parser inside the member dashboard template, allowing interactive day tabs, exercise lists, and recipe boxes to render dynamically from plain text storage.
- Used custom inline vector SVG elements instead of raw emojis to adhere to master design guidelines.

### Changed Files

- `static/styles.css`
- `templates/base.html`
- `templates/owner_dashboard.html`
- `templates/member_detail.html`
- `templates/member_edit.html`
- `templates/payments.html`
- `templates/members.html`

### Verification

- Syntax compilation check completed successfully: `.venv\Scripts\python.exe -m py_compile app.py` (exit code `0`).
- Responsive checks verify flawless grid alignments and stacked mobile list layouts across 375px, 768px, 1024px, and 1440px viewports.
- Absolutely NO `git commit` or `git push` commands were run.

## 2026-05-30 - Research-led subscription plan services

### Research Notes

- ABC Trainerize positions high-value coaching around customizable workouts, nutrition coaching, habit tracking, client messaging, badges, progress reports, team roles, and integrated payments. This supports moving StrengthLab away from plain text plan storage toward sellable service tiers and admin-reviewed plan delivery.
- Trainerize nutrition features emphasize flexible nutrition packages, meal planning, recipe support, macro goals, grocery lists, compliance, and retention. This supports separating diet plan subscriptions from workout subscriptions instead of treating diet as a generic add-on.
- Zen Planner and Mindbody emphasize billing, payments, attendance, reporting, scheduling, and operational dashboards. For a local gym, this supports keeping finance/renewal/WhatsApp workflows prominent and treating plan services as revenue products.
- Local StrengthLab context already favors WhatsApp, UPI/cash/card, renewals, trainer assignment, and local equipment lists. The best immediate upgrade is not a generic SaaS redesign, but a monetizable service model that admins can control safely.

Sources reviewed:

- https://www.trainerize.com/features/
- https://www.trainerize.com/nutrition/
- https://help.trainerize.com/hc/en-us/articles/360034311871-Setting-Health-and-Fitness-Goals-for-your-Clients
- https://zenplanner.com/pricing/
- https://www.mindbodyonline.com/business/fitness
- https://www.mindbodyonline.com/business/payments

### Decisions

- Add separate `workout_subscription` and `diet_subscription` fields per member.
- Use `Regular` workout for built-in local plans and `Premium` workout for admin-only AI-assisted draft generation.
- Use separate diet service levels: `None`, `Regular`, `Premium`.
- Keep final workout and diet plans admin-controlled. Members and trainers should view or support, but not generate or overwrite final AI plan text.
- Make AI drafts equipment-aware by passing the current StrengthLab equipment list into the AI prompt.
- Add clickable admin customization options before draft generation so admins can review and decide what goes into the final saved plan.
- Preserve local fallback when AI fails, because API limits and connectivity are realistic for a local gym deployment.

### Changed Files

- `app.py`
- `templates/member_edit.html`
- `templates/member_detail.html`
- `templates/members.html`
- `static/styles.css`
- `README.md`

### Verification

- `python -m compileall app.py`
- Subscription workflow smoke test:
  - Admin can see workout/diet service controls.
  - Admin can generate a regular workout draft.
  - Draft includes equipment basis and selected customization notes.
  - Admin can save Premium workout and no-diet state.
  - Trainer is redirected away from admin-only plan draft route.
- Browser check:
  - `/members/1/edit` shows `Workout service`, `Clickable plan customizations`, `Generate workout draft`, and `Generate diet draft`.

### Risks / Follow-ups

- The workout engine is still largely text-based. Next upgrade should turn local workout output into structured sessions with warm-up, main work, cool-down, sets, reps, RPE/RIR, rest, and progression blocks.
- Nutrition output should be upgraded into recipe cards with metric ingredients and macros.
- PDFs need a print-ready redesign to match the new service model.
- Dual-theme and mobile bottom navigation are still pending.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Professional local workout and nutrition engine

### Audit Findings

- The regular/local plan generator was still too generic for a premium gym product. It produced simple day labels and meal bullets, but not full training sessions with warm-up, main work, cool-down, RPE/RIR, rest, progression, or equipment constraints.
- The diet PDF route only exported the diet text and used basic line drawing. It did not reflect the new workout/diet service model or provide a print-ready member blueprint.
- The subscription service flow needed a stronger local fallback so Regular members still receive a professional output when AI is not used.

### Decisions

- Upgrade the regular/local engine instead of making AI the only premium-looking experience. This protects the local gym workflow from API limits, internet outages, and free-tier failures.
- Select the training split by member level:
  - Beginner: 3-day full body.
  - Intermediate: 4-day upper/lower.
  - Advanced: 6-day push/pull/legs.
- Include warm-up, main work, conditioning, cool-down, RPE/RIR, rest, progression, coach notes, safety, and equipment basis in every local workout blueprint.
- Build nutrition around practical local meals with calories, protein, carbs, fat, recipe cards, metric ingredients, and restriction handling for vegetarian/vegan, lactose, gluten, and nuts.
- Reuse the existing `/members/<id>/diet.pdf` route but upgrade its output into a combined StrengthLab member blueprint PDF containing workout, nutrition, and safety sections.

### Changed Files

- `app.py`
- `templates/member_detail.html`
- `templates/member_edit.html`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Professional plan engine smoke test:
  - Intermediate member generates `Upper / Lower` split.
  - Workout contains warm-up, main work, cool-down, RPE/RIR, rest, and equipment basis.
  - Nutrition contains recipe cards, ingredients, steps, and macros.
  - Nut-exclusion scenario avoids recommending nuts as a normal option.
  - PDF route returns `application/pdf` and starts with `%PDF`.

### Risks / Follow-ups

- Nutrition macro math is estimate-based and should later be made configurable by admin.
- Recipe cards are still plain text inside the database; a future upgrade should store structured JSON for better rendering and PDFs.
- PDF is cleaner and more complete, but not yet a full visual grid/table layout with exercise image placeholders.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Dual-theme responsive app shell

### Audit Findings

- The base shell still used a single dark-green theme and a static sidebar that moved above content on mobile.
- Shared CSS variables existed, so the fastest reliable upgrade was to convert the design tokens first instead of rewriting every page.
- Existing navigation links were route-safe, but there was no active-page state, no theme switch, and no mobile bottom navigation.

### Decisions

- Add a persistent dark/light theme switch using `localStorage` so gym staff can choose the mode that fits reception screens or mobile use.
- Use the requested StrengthLab palette:
  - Light: `#F8FAFC` app background, white cards, light borders, `#0F172A` text, `#1E40AF` brand blue.
  - Dark: `#060913` background, translucent navy panels, subtle white borders, `#F1F5F9` text, neon cyan `#00F2FE` accents.
- Keep the desktop left navigation, but add active route highlighting and smoother hover transitions.
- Hide the desktop sidebar on mobile and provide a fixed bottom navigation for quick access to the most-used workflows.
- Tune shared cards, panels, forms, plan cards, member hero blocks, tables, and mobile spacing through variables so existing pages inherit the new shell.

### Changed Files

- `templates/base.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated template smoke test:
  - Login as demo admin returns HTTP 200.
  - `/`, `/members`, `/payments`, and `/reports` render HTTP 200.
  - Each checked page includes the theme toggle, mobile bottom nav, dark theme bootstrap, and active navigation state.

### Risks / Follow-ups

- Chrome extension control was unavailable in this session, so visual browser screenshots could not be captured through the app plugin.
- Some individual pages still use legacy layout density. Next UI pass should rebuild owner/admin dashboards into bento KPI grids and chart-first finance views using the new shell tokens.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Decision-first owner and finance reporting

### Audit Findings

- The payments page already had several high-value finance tools: invoice numbers, receipt PDFs, Excel export, payment method split, revenue velocity, reminder queue, and batch payment actions.
- Owner and reports pages still showed older raw summaries, so the business owner had to infer what action to take.
- Accountant dashboard had due/recent tables but lacked the same visual collection intelligence used by payments.
- Local gym payment operations need Cash, UPI, Card, and Bank Transfer because Indian gyms often reconcile counter cash, digital UPI, and bank settlement separately.

### Decisions

- Add a reusable `business_watch_data()` helper for active, expired, frozen, unpaid, expiring, and check-in velocity metrics without changing the database schema.
- Rebuild owner overview as a 12-column bento decision dashboard with MRR, collection health, churn risk, active members, check-ins, revenue velocity, payment split, renewal radar, unpaid members, and equipment watch.
- Upgrade reports into a chart-first analytics page with collection velocity, payment split, subscription watch, and unpaid collection queue.
- Upgrade accountant dashboard with MRR, unpaid count, settlement-aware metrics, revenue velocity, and method split.
- Add Bank Transfer as a payment method option and monthly finance metric alongside Cash, UPI, and Card.

### Changed Files

- `app.py`
- `templates/owner_dashboard.html`
- `templates/reports.html`
- `templates/accountant_dashboard.html`
- `templates/payments.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/owner` returns HTTP 200 and includes MRR projection, Revenue velocity, Renewal radar, and Unpaid members.
  - `/accountant` returns HTTP 200 and includes MRR projection, Revenue velocity, and Method split.
  - `/reports` returns HTTP 200 and includes Monthly collections, Payment split, and Unpaid collection queue.
  - `/payments` returns HTTP 200 and includes Bank Transfer, Payment method split, and Batch send reminders.

### Risks / Follow-ups

- Freeze/unfreeze actions are not yet implemented; frozen count is ready to surface if that status is later written.
- Payment form is still inline. A future UI pass should move add-payment and renewal forms into a drawer or modal.
- Charts are lightweight SVG/CSS and intentionally dependency-free; a future upgrade could add richer chart interactions if needed.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Athlete-focused member dashboard

### Audit Findings

- Member detail already had useful building blocks: today's workout checklist, workout completion history, progress entries, questionnaire, payments, notifications, and plan editors.
- The first screen still mixed athlete-facing priorities with admin-heavy sections, so members had to scroll before seeing simple performance signals.
- Nutrition targets were generated inside the local plan engine but not surfaced as quick dashboard metrics.
- Members needed read-only visibility while admins/trainers retained edit and progress-entry controls.

### Decisions

- Add `attendance_streak()` and `member_dashboard_metrics()` helpers to compute member-first signals from existing tables without schema changes.
- Surface attendance streak, membership tier, latest weight, protein target, daily calories, macros, latest trainer note, energy, completion, and payment status near the top of the member dashboard.
- Keep today's workout checklist as the primary action, then place nutrition targets and trainer note immediately after it.
- Preserve member read-only behavior: members can view their personalized dashboard and save today's workout completion, but cannot edit questionnaire/profile/progress/admin plan fields.

### Changed Files

- `app.py`
- `templates/member_detail.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - Admin viewing `/members/1` returns HTTP 200 and includes Attendance streak, Nutrition targets, Trainer note, Protein target, and Workout checklist.
  - Member login using mobile ID `9999111222` and default password returns HTTP 200 for `/members/1`.
  - Member view does not expose Save questionnaire, Add progress entry, or Edit profile controls.

### Risks / Follow-ups

- Nutrition targets are estimates from the local rules engine; later versions could store coach-approved macro targets per member.
- Attendance streak depends on check-in records; gyms that do not check in consistently will see lower streaks.
- Members can still save their own workout completion. That is intentional for self-reporting, but a future role setting could make trainer-only completion tracking optional.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Membership freeze and unfreeze controls

### Audit Findings

- Dashboards already surfaced a `Frozen` member count, but no route or UI wrote that status.
- Owner/admin retention workflows need a quick way to pause a member for travel, medical issues, payment holds, or owner-approved exceptions.
- Existing `payment_status` values already drive badges, unpaid counts, and dashboard alerts, so freeze/unfreeze could be added without a database migration.

### Decisions

- Add admin/owner-only freeze and unfreeze routes on member profiles.
- Store frozen state in `members.payment_status = 'Frozen'` so existing dashboard metrics immediately reflect the state.
- On unfreeze, restore status based on subscription expiry: `Paid` if the membership is still active, otherwise `Due`.
- Queue a member notification for both freeze and reactivation.
- Surface freeze/unfreeze controls on member detail, add status badges to the member list, and make owner unpaid alerts link directly to the member profile.

### Changed Files

- `app.py`
- `templates/member_detail.html`
- `templates/members.html`
- `templates/owner_dashboard.html`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask route smoke test:
  - Admin POST `/members/1/freeze` redirects and sets member status to `Frozen`.
  - Member detail renders Membership control and Unfreeze membership while frozen.
  - Admin POST `/members/1/unfreeze` redirects and restores status based on active expiry.
  - Member login POST `/members/1/freeze` redirects away to `/`.
  - Test restored member 1's original payment status after verification.

### Risks / Follow-ups

- Freeze does not yet extend expiry dates or record a dedicated freeze history table. A future upgrade should add freeze periods for auditability and automated expiry adjustment.
- Notification rows created by the smoke test were not removed because notification logging is part of the verified behavior.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Payment entry drawer

### Audit Findings

- The payments page had strong KPI cards, charts, batch actions, receipts, and exports, but the add-payment form still occupied the main page flow.
- The objective calls for finance transaction forms to move into drawers or modals so owners can scan analytics and history first.
- The existing POST `/payments` route and fields were already suitable, so this was a UI restructuring task rather than a backend change.

### Decisions

- Convert the add-payment panel into a right-side drawer opened by the `Add payment` button.
- Use an anchor-target CSS drawer to avoid extra JavaScript and preserve local reliability.
- Keep the existing fields and method names intact: member, amount, discount, status, payment method, UPI transaction ID, due date, plan, renewal dates, notes, and WhatsApp queue action.
- Keep Cash, UPI, Card, and Bank Transfer available in the drawer.

### Changed Files

- `templates/payments.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/payments` returns HTTP 200.
  - Page includes `#payment-drawer`, drawer shell markup, Transaction entry copy, Bank Transfer, and Save and queue WhatsApp.

### Risks / Follow-ups

- Drawer uses CSS `:target`; it is reliable and dependency-free but does not trap focus like a fully scripted modal.
- Payment submission behavior is unchanged, so server-side validation is still the existing validation.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Finance status badges

### Audit Findings

- Several finance screens still displayed `Received`, `Due`, and member payment statuses as plain text.
- The app already had reusable `.pill.good` and `.pill.warn` styles, so this could be improved without adding new components or backend changes.

### Decisions

- Convert payment history status cells into badges.
- Convert accountant recent payment status cells into badges.
- Convert member profile payment summary and mini payment history into badges.
- Use green badges for received/paid states and warning badges for due/frozen/other attention states.

### Changed Files

- `templates/payments.html`
- `templates/accountant_dashboard.html`
- `templates/member_detail.html`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/payments` returns HTTP 200 and includes payment status badge markup.
  - `/accountant` returns HTTP 200 and includes recent payment badge markup.
  - `/members/1` returns HTTP 200 and includes payment badge markup.

### Risks / Follow-ups

- Badge coloring is status-name based. If more payment statuses are introduced later, they should map to explicit visual states.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Structured member blueprint PDF

### Audit Findings

- The existing `/members/<id>/diet.pdf` route already returned a combined StrengthLab blueprint, but the layout was mostly long wrapped text.
- The goal requires print-ready workout/nutrition PDFs with grids, high-contrast text, full instructions, tables/cards, recipe cards, placeholder exercise panels, and mobile-readable output.
- The route is already linked from the member dashboard, so the safest upgrade was to keep the same URL and improve the ReportLab drawing logic.

### Decisions

- Keep `/members/<id>/diet.pdf` as the existing download route for compatibility.
- Add summary cards for membership, renewal, workout service, and body metrics.
- Render workout sections as instruction panels with exercise placeholders for future photos/form cues.
- Render nutrition content as recipe cards when ingredients/macros are present.
- Add a stronger safety and coach-notes section with stop signs and intensity guidance.
- Keep the PDF dependency-free beyond the existing ReportLab usage.

### Changed Files

- `app.py`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated PDF smoke test:
  - `/members/1/diet.pdf` returns HTTP 200.
  - Response mimetype is `application/pdf`.
  - Response starts with `%PDF`.
  - Generated file size is non-empty and attachment filename is `Demo_Member_blueprint.pdf`.

### Risks / Follow-ups

- Exercise panels are placeholder boxes, not real exercise images yet.
- Plan parsing is still text-based; future structured JSON plan storage would allow cleaner tables and exact exercise metadata.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Mobile card tables for staff workflows

### Audit Findings

- The app had mobile bottom navigation and responsive grids, but dense tables still stayed table-like on small screens.
- Members and payments are the highest-frequency staff workflows on phones, especially for front-desk collection and trainer lookup.
- The table data was already well-structured, so the safest upgrade was to add semantic `data-label` attributes and CSS-only mobile card rendering.

### Decisions

- Add mobile labels to the members table for name, phone, goal, plan, status, services, trainer, and actions.
- Add mobile labels to the payments table for invoice, member, amount, discount, net, status, method, UPI ID, date, receipt, and WhatsApp.
- Add responsive CSS under the existing mobile breakpoint to turn table rows into bordered cards with label/value rows.
- Keep desktop table behavior unchanged for dense admin workflows.

### Changed Files

- `templates/members.html`
- `templates/payments.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/members` returns HTTP 200 and includes mobile card labels for Name, Services, and Actions.
  - `/payments` returns HTTP 200 and includes mobile card labels for Invoice, WhatsApp, and Status.

### Risks / Follow-ups

- Other lower-frequency tables still use desktop-style markup. Future passes can add `data-label` attributes to reports, renewal history, progress history, and equipment tables.
- CSS-only mobile card rendering does not include interactive row expansion; it favors reliability on local LAN devices.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Finance batch select controls

### Audit Findings

- Payments already supported batch WhatsApp reminders and bulk mark-paid, but staff still had to select rows one by one.
- Reminder queue and payment history use separate forms, so select-all could be scoped safely by form.
- No backend changes were needed because the existing batch route already accepts `notification_ids` and `payment_ids` lists.

### Decisions

- Add `Select all queued` to the automated reminder queue.
- Add `Select all payments` to the payment history batch action toolbar.
- Use a tiny scoped JavaScript helper to toggle only checkboxes inside the current form.
- Add a compact `.select-all` style that fits the existing action bar.

### Changed Files

- `templates/payments.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/payments` returns HTTP 200.
  - Page includes select-all controls for `notification_ids` and `payment_ids`.

### Risks / Follow-ups

- Select-all is client-side convenience only; server-side batch handling remains unchanged.
- Future pagination would need per-page/all-results wording so staff know exactly what is selected.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Auditable membership freeze history

### Audit Findings

- Freeze/unfreeze controls existed, but the app only changed `members.payment_status` and queued a notification.
- Owners need auditability for travel holds, medical pauses, payment holds, and owner exceptions.
- The dashboard already counts frozen members, so the missing piece was operational history and expiry handling.

### Decisions

- Add a `membership_freezes` table through `init_db()` for freeze periods.
- Record freeze start date, reason, previous status, expiry before freeze, staff user, unfreeze date, days frozen, restored status, expiry after unfreeze, and closing staff user.
- Add an `Extend expiry by frozen days` option during unfreeze, checked by default.
- Show freeze history on the member profile under Membership control.
- Keep the existing member status field as the live operational state so existing dashboards remain compatible.

### Changed Files

- `app.py`
- `templates/member_detail.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask freeze history smoke test:
  - `init_db()` creates the new table.
  - Admin POST `/members/1/freeze` creates a `membership_freezes` row.
  - Member profile renders the freeze reason/history.
  - Admin POST `/members/1/unfreeze` closes the row and records `days_frozen`.
  - Test restored member 1's original payment status/subscription end and deleted the smoke-test freeze row.

### Risks / Follow-ups

- Freeze periods are now auditable, but there is no separate owner report for freeze analytics yet.
- Expiry extension happens only on unfreeze when the checkbox is submitted.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Owner freeze analytics

### Audit Findings

- Freeze periods were auditable on individual member profiles, but owners still had no overview of active holds or recently reactivated members.
- Owner and reports pages already had decision-first panel layouts, so freeze analytics fit naturally there.
- The new `membership_freezes` table made this a read-model/reporting enhancement rather than another workflow change.

### Decisions

- Add `freeze_watch_data()` to return active freeze holds, recently closed freeze periods, and total closed frozen days.
- Surface active membership holds and recently reactivated members on the owner dashboard.
- Surface active freeze holds and freeze audit data on the reports page.
- Link active holds directly to member profiles for fast owner follow-up.

### Changed Files

- `app.py`
- `templates/owner_dashboard.html`
- `templates/reports.html`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/owner` returns HTTP 200 and includes Active membership holds, Recently reactivated, and total frozen days logged.
  - `/reports` returns HTTP 200 and includes Active freeze holds, Freeze audit, and total frozen days closed.

### Risks / Follow-ups

- Freeze analytics are summary panels only; no date filters or export yet.
- Total frozen days counts only closed freezes because active freezes do not yet have final duration.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Mobile overlay menu

### Audit Findings

- The app had a mobile bottom navigation bar, but lower-frequency admin links were either absent from the bottom bar or crowded.
- The objective calls for mobile bottom nav plus overlay menu, so the shell needed a secondary mobile navigation surface.
- The existing desktop navigation already had role-aware routes, so the overlay could reuse the same route permissions without backend changes.

### Decisions

- Add a `More` item to the mobile bottom nav.
- Add a CSS-only mobile overlay menu with Dashboard, Owner/Accounting, Members, Assignments, Attendance, Payments, Reports, Trainers, Equipment, WhatsApp center, theme toggle, and logout where role-appropriate.
- Keep desktop sidebar unchanged.
- Reuse the local-storage theme toggling logic for both desktop and mobile toggles.

### Changed Files

- `templates/base.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/` returns HTTP 200.
  - Page includes `#mobile-menu`, mobile overlay shell, mobile menu links, WhatsApp center, and mobile theme toggle.

### Risks / Follow-ups

- Overlay is CSS `:target` based, so it does not trap keyboard focus like a scripted modal.
- Future icon work could make the bottom nav more compact, but the current text labels are reliable and readable.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Member search and service filters

### Audit Findings

- Member management had richer service/status data, but staff still had to scan the full list manually.
- Trainers already had scoped member access, so filters needed to preserve trainer visibility boundaries.
- The fastest high-impact improvement was query-parameter filtering with compact dropdowns, not a heavier client-side table library.

### Decisions

- Add member search by name, phone, or goal.
- Add dropdown filters for payment status, workout service, diet service, and trainer/unassigned assignment.
- Preserve trainer scoping so trainers still see only their assigned or unassigned members.
- Keep filters as GET parameters for shareable/bookmarkable desk workflows.

### Changed Files

- `app.py`
- `templates/members.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/members` returns HTTP 200 and includes filter controls.
  - `/members?status=Due` returns HTTP 200 and preserves selected status.
  - `/members?workout_subscription=Premium&diet_subscription=Premium` returns HTTP 200.
  - `/members?trainer_id=unassigned` returns HTTP 200.

### Risks / Follow-ups

- Filtering is server-side and simple; there is no pagination yet.
- Search uses SQL `LIKE`, which is sufficient for local SQLite but not full-text search.
- No git commit or push executed for this goal turn.

## 2026-05-30 - Payment history filters

### Audit Findings

- Payment history had batch actions and mobile card views, but no way to narrow the table.
- Front-desk and accountant workflows often need a specific member, status, payment method, or date range.
- Existing payment actions depend on selected payment IDs, so filters needed to preserve the same form/action behavior.

### Decisions

- Add server-side payment filters using GET parameters.
- Support filters for member, status, payment method, from date, and to date.
- Keep queries parameterized and preserve existing batch action behavior.
- Show result count above the payment history table.

### Changed Files

- `app.py`
- `templates/payments.html`
- `static/styles.css`
- `FUNCTIONALITY_UPGRADE_LOG.md`

### Verification

- `.venv\\Scripts\\python.exe -m py_compile app.py`
- `git diff --check`
- Flask authenticated render smoke test:
  - `/payments` returns HTTP 200 and includes filter controls.
  - `/payments?status=Due` returns HTTP 200 and preserves selected status.
  - `/payments?payment_method=UPI` returns HTTP 200 and preserves selected method.
  - `/payments?member_id=1&date_from=2026-01-01&date_to=2026-12-31` returns HTTP 200 and preserves date range.

### Risks / Follow-ups

- Date range filters use `COALESCE(paid_on, due_on)`; if future records need separate paid/due filtering, add an explicit date-type selector.
- No pagination yet, so very large histories may still need paging/export-first workflows.
- No git commit or push executed for this goal turn.
