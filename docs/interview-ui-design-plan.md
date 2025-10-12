# Interview Chat Experience – Light Theme UI Design Plan

## 1. Product Vision
* Deliver a modern, confident, and calm interface for structured interviews.
* Prioritize clarity and trust—candidates should instantly understand the interviewer persona and available controls.
* Ensure accessibility and responsiveness across desktop and tablet breakpoints.

## 2. Key Personas & Scenarios
| Persona | Goals | Pain Points Addressed |
| --- | --- | --- |
| Candidate | Understand current question, respond confidently, request assistance | Anxiety, unclear actions |
| Interviewer/Ops | Monitor interaction quality, ensure guardrails | Need transparency into system hints, pauses, skips |

Primary flows: interview start, active chat exchange, using quick-actions (hint/think/repeat/skip), viewing scores summary (future stage).

## 3. Layout Structure
1. **Global Shell**
   * Top bar: interview title, timer indicator, persona avatar, subtle progress dots.
   * Secondary status row for alerts (safety reminders, nudge banners).
2. **Main Column (left)**
   * Chat timeline with alternating cards (assistant/candidate).
   * Each assistant message includes badges for question type (base/follow-up) and quick-action responses.
3. **Control Column (right)**
   * **Quick-Action Panel**: pill buttons with iconography, dynamically reorders based on priority; includes tooltip copy.
   * **Hint Drawer**: collapsible summary of last hint, evidence targets.
   * **Score Snapshot**: minimalist card showing avg/median/max once available.
4. **Composer Bar**
   * Sticky bottom area spanning full width.
   * Input field with placeholder guidance, character counter, attach button (future), and helper text for persona tone.

## 4. Visual Language
* **Color Palette**: warm neutrals with teal accent (#19A0A0) for action, soft gray backgrounds (#F7F9FB), charcoal text (#1F2933).
* **Typography**: Sans-serif pairing (e.g., Inter) with 16px base, 20px question headers, 14px meta captions.
* **Spacing**: 8px baseline grid; generous 24px padding around chat cards for readability.
* **Iconography**: duotone line icons for actions (light teal stroke + neutral fill).
* **Motion**: 150–200ms micro-interactions (button hover, hint drawer slide) using easing-out curves.

## 5. Component Guidelines
### 5.1 Chat Cards
* Assistant question card: tinted background (#E8F5F5), top-left persona avatar, label chip for "Follow-up".
* Candidate response: white card with subtle shadow, timestamp below.
* Safety or system messages: full-width banner with orange accent, dismissible.

### 5.2 Quick-Action Buttons
* Pill-shaped, 44px height for touch targets.
* Default row: Hint, 30s Think, Repeat, Skip. When nudge triggered, animate remaining actions and show informative tooltip.
* Disabled state: grayscale background, tooltip explaining cap reached (e.g., hint limit).

### 5.3 Hint Drawer
* Collapsible panel with summary of latest hint, evidence targets checklist with completion ticks.
* Secondary CTA to "Show previous hints" revealing accordion list.

### 5.4 Timer & Status Indicators
* Think timer chip transitions from teal to amber in final five seconds.
* Pause state overlays translucent layer with resume CTA.

## 6. Accessibility Checklist
* WCAG AA contrast (>4.5:1 for text, 3:1 for UI elements).
* Keyboard navigation: focus rings, skip to composer shortcut.
* Announce quick-action availability changes via ARIA live region.
* Provide descriptive labels for hints, timers, and status banners.

## 7. Responsive Strategy
* **≥1280px**: two-column layout with control panel visible.
* **768–1279px**: stack control components below chat with sticky quick-action row.
* **<768px**: full-width chat, quick-actions as horizontal scrollable chips, hint drawer in modal.

## 8. Empty & Edge States
* No hints available: show supportive copy "You’ve used all hints—try summarizing key evidence." with subtle illustration.
* Connection loss: offline banner with retry button.
* Think timer expired: automatic resume message card.

## 9. Observability Hooks
* Embed event IDs for telemetry: `qa_clicked`, `hint_viewed`, `think_timer_started`.
* Provide placeholder areas for real-time score updates and safety flag indicators.

## 10. Next Steps
1. Produce high-fidelity mockups (desktop + tablet).
2. Create component library tokens (colors, spacing, typography).
3. Prototype interactions in Figma (quick-action transitions, hint drawer).
4. Usability test with 3–5 candidates; iterate on clarity of controls.

