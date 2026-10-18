import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { telegramIdentity } from "../data/marketData";
import { messageOf, useRead } from "../data/query";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import {
  ActivateDialog,
  AdoptBotDialog,
  ConfirmRemoval,
  CreateBotDialog,
  LoginDialog,
  LogoutDialog,
} from "./dialogs";
import {
  ACCOUNT_LABEL,
  DESTINATION_LABEL,
  destinationsOf,
  headline,
  missingSettings,
  recipientLabel,
} from "./present";
import {
  createTelegramApi,
  type Bot,
  type Destination,
  type GateState,
  type TelegramApi,
} from "./telegramApi";

/**
 * The door to Telegram from the operator's seat: who owns the bots, which bots there are — and, one click into a bot, who
 * receives through it and which kinds of event go there. **The question is "will I be told", so what is not heard is said
 * at the top** whichever bot is open: a purpose nobody receives is collected and told to nobody, and looks exactly like
 * a quiet day.
 */

const POLL_MS = 30_000;
const signal = () => new AbortController().signal;
const SELECT = "rounded border border-border bg-sunken px-1 py-0.5 text-xs text-ink";

const NO_STATE: GateState = {
  account: {
    status: "logged_out",
    username: null,
    phone: null,
    reason: null,
    sessionKeyConfigured: false,
    apiCredentialsConfigured: false,
  },
  canCreateBots: false,
  bots: 0,
  destinations: 0,
  destinationsReady: 0,
};

type Dialog =
  | { kind: "login" }
  | { kind: "logout" }
  | { kind: "create-bot" }
  | { kind: "adopt-bot" }
  | { kind: "activate"; bot: Bot; existing?: Destination }
  | { kind: "rotate"; bot: Bot }
  | { kind: "remove-bot"; bot: Bot }
  | { kind: "remove-destination"; destination: Destination };

export function TelegramView({ api }: { api?: TelegramApi } = {}) {
  const client = useMemo(
    () => api ?? createTelegramApi(resolveEndpoints().telegramHttp, telegramIdentity),
    [api],
  );
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [openBot, setOpenBot] = useState<string | null>(null);

  const state = useRead<GateState>({
    key: ["telegram", "state"],
    read: (s) => client.state(s),
    initial: NO_STATE,
    fallbackMessage: "nie udało się wczytać stanu bramy Telegrama",
    pollMs: POLL_MS,
  });
  const ready = state.status === "ready";
  const bots = useRead<Bot[]>({
    key: ["telegram", "bots"],
    read: (s) => client.bots(s),
    initial: [],
    fallbackMessage: "nie udało się wczytać botów",
    pollMs: POLL_MS,
    enabled: ready,
  });
  const destinations = useRead<Destination[]>({
    key: ["telegram", "destinations"],
    read: (s) => client.destinations(s),
    initial: [],
    fallbackMessage: "nie udało się wczytać odbiorców",
    pollMs: POLL_MS,
    enabled: ready,
  });
  const refresh = () => {
    state.reload();
    bots.reload();
    destinations.reload();
  };

  const gate = state.value;
  const account = gate.account;
  const missing = missingSettings(account);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-base font-semibold text-ink">Telegram</h1>
        {ready && <span className="text-xs text-ink-faint">{headline(gate)}</span>}
      </header>

      {state.error !== null && <UnreachableNotice onRetry={state.reload}>{state.error}</UnreachableNotice>}
      <p className="text-xs text-ink-faint">
        Kto o czym słyszy — jakie zdarzenia i jakie ceny dają wiadomość, i do którego z tych odbiorców — ustawiasz w zakładce
        Alerty. Tu jest tylko droga: konto, boty i odbiorcy.
      </p>
      {ready && account.status === "logged_out" && bots.status === "ready" && bots.value.length === 0 && (
        <p className="rounded bg-panel px-3 py-2 text-sm text-ink-secondary">
          Zacznij od zalogowania konta-właściciela (osobnego konta tylko do botów), a potem utwórz bota i aktywuj odbiorcę.
          Masz już bota z @BotFathera? Dodaj jego token i pomiń logowanie.
        </p>
      )}

      <Section title="Konto-właściciel">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-ink">
            {ACCOUNT_LABEL[account.status]}
            {account.username !== null && (
              <span className="text-ink-faint">
                {" "}
                · {account.username}
                {account.phone !== null && ` · ${account.phone}`}
              </span>
            )}
          </span>
          {account.status === "logged_in" ? (
            <Button size="xs" tone="muted" onClick={() => setDialog({ kind: "logout" })}>
              Wyloguj
            </Button>
          ) : (
            <Button size="xs" tone="primary" disabled={missing.length > 0} onClick={() => setDialog({ kind: "login" })}>
              Zaloguj konto…
            </Button>
          )}
        </div>
        {account.reason !== null && <p className="text-xs text-warning">{account.reason}</p>}
        {missing.length > 0 && (
          <p className="text-xs text-ink-muted">
            Serwerowi brakuje ustawień: <code>{missing.join(", ")}</code>. Bez nich bramka wysyła, ale nie zaloguje konta ani
            nie założy bota — to działająca konfiguracja, nie awaria.
          </p>
        )}
        <p className="text-xs text-ink-faint">
          Konto zakłada boty u BotFathera; powinno być osobne, tylko do tego. Jego sesja leży w bazie zaszyfrowana kluczem
          serwera i nigdy nie wraca do przeglądarki.
        </p>
      </Section>

      <Section
        title="Boty"
        actions={
          <>
            <Button
              size="xs"
              tone="primary"
              disabled={!gate.canCreateBots}
              title={gate.canCreateBots ? undefined : "Najpierw zaloguj konto-właściciela"}
              onClick={() => setDialog({ kind: "create-bot" })}
            >
              Utwórz bota…
            </Button>
            <Button size="xs" tone="muted" onClick={() => setDialog({ kind: "adopt-bot" })}>
              Dodaj token…
            </Button>
          </>
        }
      >
        {bots.error !== null && <UnreachableNotice onRetry={bots.reload}>{bots.error}</UnreachableNotice>}
        {bots.status === "ready" && bots.value.length === 0 && (
          <p className="text-sm text-ink-muted">Brama nie zna jeszcze żadnego bota.</p>
        )}
        <ul className="flex flex-col gap-2">
          {bots.value.map((bot) => {
            const mine = destinationsOf(bot, destinations.value);
            const isOpen = bot.username === openBot;
            const receiving = mine.filter((one) => one.receives).length;
            return (
              <li key={bot.username} className="overflow-hidden rounded-md border border-border bg-panel">
                <div className="flex flex-wrap items-center gap-3 px-3 py-2">
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    aria-label={`@${bot.username} — ${isOpen ? "zwiń" : "pokaż odbiorców"}`}
                    className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
                    onClick={() => setOpenBot(isOpen ? null : bot.username)}
                  >
                    <span aria-hidden className="w-3 text-xs text-ink-faint">
                      {isOpen ? "▾" : "▸"}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-ink">@{bot.username}</span>
                      <span className="block truncate text-xs text-ink-faint">
                        {bot.title} · {bot.createdHere ? "utworzony tu" : "dodany tokenem"}
                      </span>
                    </span>
                  </button>
                  <span className="flex gap-2 text-[11px]">
                    <span
                      className={[
                        "rounded px-1.5 py-0.5",
                        receiving > 0 ? "bg-raised text-ink-secondary" : "bg-warning-soft text-warning",
                      ].join(" ")}
                    >
                      {receiving}/{mine.length} odbiera
                    </span>
                  </span>
                  <span className="flex gap-1.5">
                    <Button size="xs" tone="quiet" onClick={() => setDialog({ kind: "activate", bot })}>
                      Dodaj odbiorcę…
                    </Button>
                    <Button
                      size="xs"
                      tone="muted"
                      disabled={!gate.canCreateBots}
                      title={gate.canCreateBots ? undefined : "Rotacja wymaga zalogowanego konta-właściciela"}
                      onClick={() => setDialog({ kind: "rotate", bot })}
                    >
                      Rotuj token
                    </Button>
                    <Button
                      size="xs"
                      tone="critical"
                      aria-label={`Usuń bota @${bot.username}`}
                      onClick={() => setDialog({ kind: "remove-bot", bot })}
                    >
                      Usuń bota
                    </Button>
                  </span>
                </div>
                {isOpen && (
                  <BotDetail
                    destinations={mine}
                    onActivate={(existing) => setDialog({ kind: "activate", bot, existing })}
                    onRemoveDestination={(destination) => setDialog({ kind: "remove-destination", destination })}
                    onSend={(destination, text) => client.sendMessage(destination, text, signal())}
                  />
                )}
              </li>
            );
          })}
        </ul>
      </Section>

      {dialog?.kind === "login" && (
        <LoginDialog api={client} onClose={() => setDialog(null)} onDone={refresh} />
      )}
      {dialog?.kind === "logout" && (
        <LogoutDialog api={client} username={account.username} onClose={() => setDialog(null)} onDone={refresh} />
      )}
      {dialog?.kind === "create-bot" && (
        <CreateBotDialog
          api={client}
          onClose={() => setDialog(null)}
          onDone={(bot) => {
            refresh();
            setOpenBot(bot.username);
            setDialog({ kind: "activate", bot });
          }}
        />
      )}
      {dialog?.kind === "adopt-bot" && (
        <AdoptBotDialog
          api={client}
          onClose={() => setDialog(null)}
          onDone={(bot) => {
            refresh();
            setOpenBot(bot.username);
            setDialog({ kind: "activate", bot });
          }}
        />
      )}
      {dialog?.kind === "activate" && (
        <ActivateDialog
          api={client}
          bot={dialog.bot}
          existing={dialog.existing}
          destinations={destinations.value}
          onClose={() => {
            setDialog(null);
            refresh();
          }}
          onDone={refresh}
        />
      )}
      {dialog?.kind === "rotate" && (
        <ConfirmRemoval
          title={`Zrotuj token @${dialog.bot.username}`}
          confirmLabel="Zrotuj"
          fallbackError="nie udało się zrotować tokenu"
          body={
            <p>
              BotFather wyda nowy token, a stary przestanie działać od razu. Odbiorcy zostają — nikt nie musi
              dotykać linku ponownie.
            </p>
          }
          onConfirm={async () => {
            await client.rotateBot(dialog.bot.username, signal());
            refresh();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "remove-bot" && (
        <ConfirmRemoval
          title={`Usuń @${dialog.bot.username}`}
          confirmLabel="Usuń bota"
          fallbackError="nie udało się usunąć bota"
          body={
            <>
              <p>
                {dialog.bot.createdHere
                  ? "Bot zostanie skasowany u BotFathera i stąd, razem z odbiorcami."
                  : "Ten bot został dodany tokenem: brama go zapomni, ale u BotFathera zostaje do ręcznego skasowania."}
              </p>
              <p>
                Reguły w zakładce Alerty, które wskazują jego odbiorców, zostaną na liście, ale przestaną dostarczać — brama
                nie ma już jak ich ostrzec, więc sprawdź je najpierw.
              </p>
            </>
          }
          onConfirm={async () => {
            await client.removeBot(dialog.bot.username, signal());
            setOpenBot(null);
            refresh();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "remove-destination" && (
        <ConfirmRemoval
          title={`Usuń odbiorcę ${dialog.destination.name}`}
          confirmLabel="Usuń odbiorcę"
          fallbackError="nie udało się usunąć odbiorcy"
          body={
            <p>
              Znika tylko powiązanie z czatem — bot zostaje. Reguły w zakładce Alerty, które go wskazują, zostaną na liście,
              ale przestaną dostarczać.
            </p>
          }
          onConfirm={async () => {
            await client.removeDestination(dialog.destination.name, signal());
            refresh();
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </section>
  );
}

function Section({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {actions}
      </div>
      {children}
    </div>
  );
}

/** One bot opened: who receives through it, and a message to try the road with. */
function BotDetail({
  destinations,
  onActivate,
  onRemoveDestination,
  onSend,
}: {
  destinations: Destination[];
  onActivate(existing?: Destination): void;
  onRemoveDestination(destination: Destination): void;
  onSend(destination: string, text: string): Promise<number>;
}) {
  return (
    <div className="grid gap-3 border-t border-border bg-sunken/40 p-3 md:grid-cols-2">
      <Card title="Odbiorcy" hint="Kto dostaje wiadomości od tego bota. Każdy raz dotknął „Start”.">
        {destinations.length === 0 && <Empty>Nikt jeszcze nie odbiera — „Dodaj odbiorcę…” pokaże link i kod QR.</Empty>}
        {destinations.map((destination) => (
          <Row key={destination.name}>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-ink">{recipientLabel(destination)}</span>
              <span className="block text-[11px] text-ink-faint">nazwa w regułach: {destination.name}</span>
            </span>
            <span
              className={[
                "rounded px-1.5 py-0.5 text-[11px]",
                destination.receives ? "bg-raised text-ink-secondary" : "bg-warning-soft text-warning",
              ].join(" ")}
            >
              {DESTINATION_LABEL[destination.state]}
            </span>
            {!destination.receives && (
              <Button size="2xs" tone="muted" onClick={() => onActivate(destination)}>
                {destination.state === "blocked" ? "Wiąż ponownie" : "Nowy link"}
              </Button>
            )}
            <Button
              size="2xs"
              tone="critical"
              aria-label={`Usuń odbiorcę ${destination.name}`}
              onClick={() => onRemoveDestination(destination)}
            >
              Usuń
            </Button>
          </Row>
        ))}
      </Card>

      <TestMessage destinations={destinations} onSend={onSend} />
    </div>
  );
}

/** Says something through this bot, now, to one of its recipients — to see that the road works end to end without waiting
 *  for an archive to have news. A real message on a real phone, so it asks for nothing it cannot say plainly. */
function TestMessage({
  destinations,
  onSend,
}: {
  destinations: Destination[];
  onSend(destination: string, text: string): Promise<number>;
}) {
  const ready = destinations.filter((one) => one.receives);
  const [chosen, setChosen] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<{ ok: boolean; text: string } | null>(null);
  const target = ready.find((one) => one.name === chosen)?.name ?? ready[0]?.name ?? "";

  async function send(): Promise<void> {
    setBusy(true);
    setOutcome(null);
    try {
      const id = await onSend(target, text);
      setOutcome({ ok: true, text: `Wysłane (wiadomość nr ${id} w Telegramie).` });
      setText("");
    } catch (cause: unknown) {
      setOutcome({ ok: false, text: messageOf(cause, "nie udało się wysłać") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="md:col-span-2">
      <Card title="Wyślij wiadomość" hint="Do jednego z odbiorców tego bota, od razu — do wypróbowania drogi. Nic nie jest zapisywane.">
        {ready.length === 0 ? (
          <Empty>Nikt jeszcze nie odbiera przez tego bota, więc nie ma do kogo.</Empty>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <label className="flex items-center gap-2 text-ink-secondary">
                Do
                <select
                  className={SELECT}
                  aria-label="odbiorca wiadomości"
                  value={target}
                  onChange={(e) => setChosen(e.target.value)}
                >
                  {ready.map((one) => (
                    <option key={one.name} value={one.name}>
                      {recipientLabel(one)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <textarea
              className="min-h-20 rounded border border-border bg-sunken px-2 py-1 text-sm text-ink"
              aria-label="treść wiadomości"
              placeholder="Treść…"
              value={text}
              maxLength={4096}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="flex items-center gap-3">
              <Button size="xs" tone="primary" disabled={busy || text.trim() === ""} onClick={() => void send()}>
                {busy ? "Wysyłam…" : "Wyślij"}
              </Button>
              {outcome !== null && (
                <span className={outcome.ok ? "text-xs text-ink-secondary" : "text-xs text-critical"}>{outcome.text}</span>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function Card({
  title,
  hint,
  action,
  children,
}: {
  title: string;
  hint: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded border border-border bg-panel p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">{title}</h3>
        <span className="flex-1" />
        {action}
      </div>
      <p className="text-[11px] text-ink-faint">{hint}</p>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-border/60 bg-sunken/40 px-2 py-1.5 text-xs">
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-ink-faint">{children}</p>;
}
