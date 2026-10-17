import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { telegramIdentity } from "../data/marketData";
import { messageOf, useRead } from "../data/query";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import {
  ActivateDialog,
  AdoptBotDialog,
  AssignDialog,
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
  orderedPurposes,
  originLabel,
  originOf,
} from "./present";
import {
  createTelegramApi,
  type Assignment,
  type Bot,
  type Destination,
  type GateState,
  type Purpose,
  type TelegramApi,
} from "./telegramApi";

/**
 * The door to Telegram from the operator's seat: who owns the bots, which bots there are and who receives, and — the part that
 * changes — which kind of event goes to whom. **The question is "will I be told", so what is not heard comes first**: a
 * purpose nobody receives is collected and told to nobody, and looks exactly like a quiet day.
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
  defaultAssignment: false,
  purposesUnheard: 0,
};

type Dialog =
  | { kind: "login" }
  | { kind: "logout" }
  | { kind: "create-bot" }
  | { kind: "adopt-bot" }
  | { kind: "activate"; bot: Bot; existing?: Destination }
  | { kind: "rotate"; bot: Bot }
  | { kind: "remove-bot"; bot: Bot }
  | { kind: "remove-destination"; destination: Destination }
  | { kind: "assign"; key?: string };

export function TelegramView({ api }: { api?: TelegramApi } = {}) {
  const client = useMemo(
    () => api ?? createTelegramApi(resolveEndpoints().telegramHttp, telegramIdentity),
    [api],
  );
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

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
  const purposes = useRead<Purpose[]>({
    key: ["telegram", "purposes"],
    read: (s) => client.purposes(s),
    initial: [],
    fallbackMessage: "nie udało się wczytać celów",
    pollMs: POLL_MS,
    enabled: ready,
  });
  const assignments = useRead<Assignment[]>({
    key: ["telegram", "assignments"],
    read: (s) => client.assignments(s),
    initial: [],
    fallbackMessage: "nie udało się wczytać przypisań",
    pollMs: POLL_MS,
    enabled: ready,
  });

  const refresh = () => {
    state.reload();
    bots.reload();
    destinations.reload();
    purposes.reload();
    assignments.reload();
  };

  async function act(work: () => Promise<unknown>, fallback: string): Promise<void> {
    setFailure(null);
    try {
      await work();
      refresh();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, fallback));
    }
  }

  const gate = state.value;
  const account = gate.account;
  const missing = missingSettings(account);
  const ordered = orderedPurposes(purposes.value);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-base font-semibold text-ink">Telegram</h1>
        {ready && <span className="text-xs text-ink-faint">{headline(gate)}</span>}
      </header>

      {state.error !== null && <UnreachableNotice onRetry={state.reload}>{state.error}</UnreachableNotice>}
      {failure !== null && <p className="text-sm text-critical">{failure}</p>}
      {ready && gate.purposesUnheard > 0 && (
        <p className="rounded bg-warning-soft px-3 py-1 text-sm font-semibold text-warning">
          {gate.purposesUnheard} {gate.purposesUnheard === 1 ? "rodzaj zdarzeń nie ma" : "rodzajów zdarzeń nie ma"} odbiorcy —
          są zbierane, ale nikt o nich nie usłyszy. Przypisz je poniżej.
        </p>
      )}

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
          {bots.value.map((bot) => (
            <BotRow
              key={bot.username}
              bot={bot}
              destinations={destinationsOf(bot, destinations.value)}
              canManage={gate.canCreateBots}
              onActivate={(existing) => setDialog({ kind: "activate", bot, existing })}
              onRotate={() => setDialog({ kind: "rotate", bot })}
              onRemove={() => setDialog({ kind: "remove-bot", bot })}
              onRemoveDestination={(destination) => setDialog({ kind: "remove-destination", destination })}
            />
          ))}
        </ul>
      </Section>

      <Section
        title="Cele"
        actions={
          <Button
            size="xs"
            tone="primary"
            disabled={destinations.value.length === 0}
            onClick={() => setDialog({ kind: "assign" })}
          >
            Dodaj przypisanie…
          </Button>
        }
      >
        <p className="text-xs text-ink-faint">
          Cel to rodzaj zdarzenia, o którym coś mówi system — pojawia się sam, gdy po raz pierwszy zostanie użyty. Przypisanie
          wskazuje, kto go słyszy; najdłuższy pasujący przedrostek wygrywa, a <code>*</code> łapie resztę.
        </p>
        {purposes.error !== null && <UnreachableNotice onRetry={purposes.reload}>{purposes.error}</UnreachableNotice>}
        {purposes.status === "ready" && ordered.length === 0 && (
          <p className="text-sm text-ink-muted">
            Żaden cel nie został jeszcze użyty. Pojawią się, gdy archiwa i strategie powiedzą pierwsze słowo.
          </p>
        )}
        <ul className="flex flex-col gap-1">
          {ordered.map((purpose) => (
            <PurposeRow
              key={purpose.name}
              purpose={purpose}
              destinations={destinations.value}
              owned={assignments.value.find((one) => one.key === purpose.name)?.destination ?? ""}
              onChoose={(destination) =>
                void act(
                  () =>
                    destination === ""
                      ? client.unassign(purpose.name, signal())
                      : client.assign(purpose.name, destination, signal()),
                  "nie udało się zmienić przypisania",
                )
              }
            />
          ))}
        </ul>

        <h3 className="mt-2 text-xs font-semibold text-ink-secondary">Przypisania</h3>
        {assignments.status === "ready" && assignments.value.length === 0 && (
          <p className="text-sm text-ink-muted">Nic nie jest przypisane.</p>
        )}
        <ul className="flex flex-col gap-1">
          {assignments.value.map((one) => (
            <li key={one.key} className="flex flex-wrap items-center gap-3 rounded border border-border bg-panel px-3 py-1.5">
              <code className="text-xs text-ink">{one.key}</code>
              <span className="text-xs text-ink-faint">→</span>
              <select
                className={SELECT}
                aria-label={`odbiorca dla ${one.key}`}
                value={one.destination}
                onChange={(e) =>
                  void act(() => client.assign(one.key, e.target.value, signal()), "nie udało się zmienić przypisania")
                }
              >
                {destinations.value.map((d) => (
                  <option key={d.name} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </select>
              <span className="text-xs text-ink-faint">@{one.bot}</span>
              {!one.receives && <span className="text-xs text-warning">jeszcze nie odbiera</span>}
              <span className="flex-1" />
              <Button
                size="xs"
                tone="critical"
                onClick={() => void act(() => client.unassign(one.key, signal()), "nie udało się zdjąć przypisania")}
              >
                Zdejmij
              </Button>
            </li>
          ))}
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
            setDialog({ kind: "activate", bot });
          }}
        />
      )}
      {dialog?.kind === "activate" && (
        <ActivateDialog
          api={client}
          bot={dialog.bot}
          existing={dialog.existing}
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
              BotFather wyda nowy token, a stary przestanie działać od razu. Odbiorcy i przypisania zostają — nikt nie musi
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
                Jeśli któryś z jego odbiorców ma jeszcze przypisane cele, brama odmówi i wskaże je — najpierw je przepnij.
              </p>
            </>
          }
          onConfirm={async () => {
            await client.removeBot(dialog.bot.username, signal());
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
              Znika tylko powiązanie z czatem — bot zostaje. Jeśli odbiorca ma przypisane cele, brama odmówi i wskaże je.
            </p>
          }
          onConfirm={async () => {
            await client.removeDestination(dialog.destination.name, signal());
            refresh();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "assign" && (
        <AssignDialog
          api={client}
          destinations={destinations.value}
          initialKey={dialog.key}
          onClose={() => setDialog(null)}
          onDone={refresh}
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

function BotRow({
  bot,
  destinations,
  canManage,
  onActivate,
  onRotate,
  onRemove,
  onRemoveDestination,
}: {
  bot: Bot;
  destinations: Destination[];
  canManage: boolean;
  onActivate(existing?: Destination): void;
  onRotate(): void;
  onRemove(): void;
  onRemoveDestination(destination: Destination): void;
}) {
  return (
    <li className="flex flex-col gap-1 rounded border border-border bg-panel px-3 py-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="min-w-0 flex-1">
          <span className="text-sm text-ink">@{bot.username}</span> <span className="text-xs text-ink-faint">{bot.title}</span>{" "}
          <span className="rounded bg-raised px-1 text-[11px] text-ink-muted">
            {bot.createdHere ? "utworzony tu" : "dodany tokenem"}
          </span>
        </span>
        <Button size="xs" tone="primary" onClick={() => onActivate()}>
          Aktywuj odbiorcę…
        </Button>
        <Button size="xs" tone="muted" disabled={!canManage} onClick={onRotate}>
          Rotuj token
        </Button>
        <Button size="xs" tone="critical" aria-label={`Usuń bota @${bot.username}`} onClick={onRemove}>
          Usuń
        </Button>
      </div>
      {destinations.length === 0 && <p className="text-xs text-ink-faint">Nikt jeszcze nie odbiera przez tego bota.</p>}
      <ul className="flex flex-col gap-0.5">
        {destinations.map((destination) => (
          <li key={destination.name} className="flex flex-wrap items-center gap-3 text-xs">
            <span className="text-ink">{destination.name}</span>
            <span className={destination.receives ? "text-ink-secondary" : "text-warning"}>
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
          </li>
        ))}
      </ul>
    </li>
  );
}

function PurposeRow({
  purpose,
  destinations,
  owned,
  onChoose,
}: {
  purpose: Purpose;
  destinations: Destination[];
  /** The destination this very purpose is assigned to, or "" when it is only heard through a prefix or the default. */
  owned: string;
  onChoose(destination: string): void;
}) {
  const origin = originOf(purpose);
  return (
    <li
      className={[
        "flex flex-wrap items-center gap-3 rounded border bg-panel px-3 py-1.5",
        origin.kind === "none" ? "border-warning" : "border-border",
      ].join(" ")}
    >
      <span className="min-w-0 flex-1">
        <code className="text-xs text-ink">{purpose.name}</code>
        {purpose.description !== null && <span className="ml-2 text-xs text-ink-faint">{purpose.description}</span>}
        <span className="block text-xs text-ink-faint">
          {purpose.destination !== null ? `→ ${purpose.destination} · ` : ""}
          <span className={origin.kind === "none" ? "text-warning" : undefined}>{originLabel(origin)}</span>
          {" · ostatnio "}
          {purpose.lastSeen.toLocaleString("pl-PL")}
          {purpose.lastCaller !== null && ` · ${purpose.lastCaller}`}
        </span>
      </span>
      <select
        className={SELECT}
        aria-label={`odbiorca dla ${purpose.name}`}
        value={owned}
        onChange={(e) => onChoose(e.target.value)}
      >
        <option value="">(dziedzicz)</option>
        {destinations.map((one) => (
          <option key={one.name} value={one.name}>
            {one.name}
          </option>
        ))}
      </select>
    </li>
  );
}
