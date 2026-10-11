// A small "?" that explains something in one plain sentence on hover or focus.
export default function Info({ text, side = "top" }: { text: string; side?: "top" | "bottom" }) {
  return (
    <span className="relative inline-flex group align-middle" tabIndex={0} aria-label={text}>
      <span className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-600 text-[10px] font-semibold text-slate-400 group-hover:border-violet-400 group-hover:text-violet-300 group-focus:border-violet-400 cursor-help">
        ?
      </span>
      <span
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 z-50 w-60 -translate-x-1/2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-normal normal-case leading-snug tracking-normal text-slate-200 opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100 ${side === "top" ? "bottom-6" : "top-6"}`}
      >
        {text}
      </span>
    </span>
  );
}
