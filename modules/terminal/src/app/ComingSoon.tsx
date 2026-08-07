export function ComingSoon({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="text-center">
        <p className="text-lg text-ink">{label}</p>
        <p className="mt-1 text-sm text-ink-muted">This part of the terminal isn't built yet.</p>
      </div>
    </div>
  );
}
