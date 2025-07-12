# UI & UX Playbook for **mcp-agent-inspector**
Version 1.0  (2025-07-11)  
Primary audience: Front-end engineers, AI coding assistants

This single file merges two concerns:  
*UI-UX patterns* (how we architect React code so assistants can extend it) and a concise *UX guideline* (set of tokens, colours, spacing, accessibility rules) that guarantees a consistent look-and-feel.

---

## 1. Why this document exists
1. AI assistants rely on clear, repeatable patterns - the less ambiguity, the less hallucination.  
2. Human contributors need a canonical reference to avoid style drift.  
3. Milestones M1-M3 schedule rapid UI growth (Session list -> DAGs). A shared playbook prevents re-work.

> Whenever you add or change UI, **cite the relevant rule number in your PR.**

---

## 2. High-level architecture patterns
### 2.1 Observable Component Architecture (OCA)
Foundation -> Pattern -> Domain -> Page


* **Foundation** Stateless primitives (Button, Card, ScrollArea) – imported from `shadcn/ui` or wrapped once in `components/ui/*`.
* **Pattern** Reusable layouts/behaviours (VirtualList, JSONTree, SplitPane).
* **Domain** Inspector-specific widgets (SpanTree, TraceBanner, ModelCostBar).
* **Page** Top-level routes (SessionsPage, DebuggerPage).

Rule 2.1.1 Never skip a layer – Domain components may import Foundation & Pattern, but not Page.

### 2.2 File & naming conventions
src/
components/
ui/               # Foundation
patterns/         # Pattern
domain/           # Domain
pages/
hooks/
stores/

* **kebab-case** file names (`span-tree.tsx`).  
* **PascalCase** component names (`SpanTree`).  
* One **.test.tsx** and optional **.stories.tsx** next to each component.

---

## 3 · Design-token ladder
We use a three-layer system inspired by Radix & shadcn:

| Layer | File | Example key |
|-------|------|-------------|
| **Primitive** | `tokens/primitives.ts` | `blue.500 = #2563eb` |
| **Semantic**  | `tokens/semantic.ts`   | `text.primary = blue.900` |
| **Component** | `tokens/component.ts`  | `button.primary.bg = blue.600` |

Rule 3.1 Only Semantic tokens may appear in component CSS.  
Rule 3.2 Add/change tokens in a PR **before** using them.

---

## 4 · State management patterns
* **Zustand per-slice** (`stores/sessionStore.ts`, `stores/traceStore.ts`).  
* Use [`devtools`](https://github.com/pmndrs/zustand#middleware) with `{ serialize:{map:true,set:true} }`.  
* Cross-slice comms via events (`eventBus.publish('traceParsed', spanCount)`).

Snippet – store template:
```ts
export const useTraceStore = create<TraceSlice>()(
  devtools(
    (set, get) => ({
      traces: new Map<string, ParsedTrace>(),
      addTrace: (sid, trace) =>
        set(state => ({ traces: new Map(state.traces).set(sid, trace) }))
    }),
    { name: 'trace-store', serialize: { map: true } }
  )
)
```

---

## 5 · Performance rules
Concern	Budget	Technique
Initial bundle	≤ 180 kB gzip	shadcn/ui + dayjs only (no lodash)
Span tree render	60 fps	@tanstack/react-virtual
Trace parse (50 k spans)	< 1.5 s in Web Worker	Stream + pako
SSE update flood	throttle 100 ms	Lodash throttle or custom hook
Rule 5.2 DOM nodes for SpanTree are virtualised; never render > 500 elements at once.

## 6. Testing & Visual regression
vitest + @testing-library/react for unit/component.
Storybook stories in /stories for every Domain component.
Chromatic CI runs on PRs - diff budget <= 5 px.
Example component test:

it('renders collapsed span', () => {
  render(<SpanView span={mockSpan} depth={1} isCollapsed={true} />)
  expect(screen.getByText('workflow.run')).toBeInTheDocument()
})
## 7 · UX Guidelines (visual & interaction)

### 7.1 Colour palette (primitive tokens)
blue:  #2563eb  #1e40af
green: #10b981  #047857
yellow:#facc15  #eab308
red:   #ef4444  #b91c1c
gray:  slate-500-900
Success = green-500; Warning (paused) = yellow-400; Error = red-500.
Status dots are filled for terminal status, pulsing ring for “running”.
### 7.2 Typography
Base font: Inter, system-ui, sans-serif.
Font scale (rem): 0.75 / 0.875 / 1 / 1.25 / 1.5
### 7.3 Spacing & layout
4-point grid (4 px multiples).
Standard component padding: px-3 py-2.
Icon + label gap: gap-2.
### 7.4 Iconography
lucide-react – import only used icons.
Status icons:
Running (blue pulse)
Paused (yellow)
Error (red)
Completed (white)
### 7.5 Interaction & accessibility

| Pattern | Rule |
|---------|------|
| Keyboard nav | Every clickable row gets tabIndex=0 & role="button" |
| Colour contrast | >= WCAG AA (4.5:1) - test in Storybook |
| Motion | Reduce motion when prefers-reduced-motion |
| Focus ring | 2 px outline-offset:2px using ring-2 ring-blue-500 |
### 7.6 Layout grid
SessionsPage - two-pane (240 px fixed left, auto right).
DebuggerPage - three-pane (SpanTree | InspectorPanel | ContextViewer).
### 7.7 High-contrast / dark mode
Tailwind dark: classes already configured.
Tokens map automatically (semantic.background.primary changes per mode).
### 7.8 Responsive breakpoints

| Name | Min-width |
|------|-----------|
| md | 768 px |
| lg | 1024 px |

On small screens (< md) hide SpanTree, show dropdown.

### 7.9 Keyboard shortcuts (Page layer)
s = focus Session list search.
a = toggle “Advanced” raw-attributes mode.
Cmd+k = command palette (roadmap M4).
## 8 · Copy guidelines
Use sentence-case (Waiting on signal) not Title Case.
Avoid jargon; if unavoidable, expose tooltip (<Abbr> component).
Error messages: “Something went wrong loading spans” – never raw stack.
## 9 · Don'ts list
Don’t pull in component libraries that hide source (e.g., MUI).
Don’t inline CSS literals – always className with tokens.
No anonymous default exports.
No setState loops inside SSE handlers – batch via requestAnimationFrame.
Never mutate Zustand state outside its set function.
## 10 · Quick crib-sheet for AI assistants
• Need list UI?  ->  Foundation Button + Pattern VirtualList.
• Need live data? ->  hook useSSE() then update zustand slice.
• New visualisation? ->  Domain component + register in plugins/index.ts.
• Unsure of colour? ->  semanticTokens.background.muted.
• Performance dropped? ->  Check SpanTree virtualiser & throttling.
## 11 · Change-control
Add/modify tokens → PR must update tokens/*.ts + Storybook theme story.
Any new keyboard shortcut → document in 7.9 table + E2E test.
Breaking visual changes → include before/after screenshots in PR.
Happy building - let's keep Inspector fast, readable and delightful.


