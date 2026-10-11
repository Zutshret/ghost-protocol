const KEY = "ghost-howto-seen";

export function seenHowTo(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return true; // storage blocked: don't nag
  }
}

const STEPS = [
  { t: "Pick an incident and press Run", d: "Choose an outage and who responds: the fixed rule (the baseline) or our AI agents. Then press Run incident." },
  { t: "Read the page from 1 to 4", d: "1 shows what broke, 2 what each agent thinks, 3 how they argued and decided, and 4 whether it worked." },
  { t: "Click anything for the why", d: "Every moment and decision opens its evidence trail. The ? icons explain each number in one sentence." },
];

export default function HowTo({ onClose }: { onClose: () => void }) {
  const close = () => {
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      /* ignore */
    }
    onClose();
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={close}>
      <div className="w-[560px] max-w-full rounded-2xl border border-slate-700 bg-slate-950 p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="text-xl font-semibold text-white">How to read this</div>
        <p className="mt-1 text-sm text-slate-400">A simulated payments platform breaks. AI agents with different goals work out why, and decide what to do.</p>
        <ol className="mt-5 space-y-4">
          {STEPS.map((s, i) => (
            <li key={s.t} className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-600/25 text-sm font-bold text-violet-300">{i + 1}</span>
              <div><div className="font-medium text-slate-100">{s.t}</div><div className="text-sm text-slate-400">{s.d}</div></div>
            </li>
          ))}
        </ol>
        <button onClick={close} className="mt-6 w-full rounded-lg bg-violet-600 py-2.5 font-semibold text-white hover:bg-violet-500">Got it</button>
        <p className="mt-2 text-center text-xs text-slate-500">Reopen any time with the ? button at the top.</p>
      </div>
    </div>
  );
}
