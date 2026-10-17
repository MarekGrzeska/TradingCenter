import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { botUsernameProblem, keyProblem } from "./present";
import { QrCode } from "./QrCode";
import type { Bot, Destination, StartLink, TelegramApi } from "./telegramApi";

/**
 * The questions this tab asks. A refusal from the door — a wrong code, an assignment still pointing at what is being removed,
 * a setting it names — stays in the dialog with the door's own words: it answers what was asked, it is not a failure of the screen.
 */

const INPUT = "rounded border border-border bg-sunken px-2 py-1 text-ink";
const signal = () => new AbortController().signal;

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-ink-secondary">{label}</span>
      {children}
      {hint && <span className="text-ink-faint">{hint}</span>}
    </label>
  );
}

type Step = "phone" | "code" | "password";

/** Telegram's steps in Telegram's order. The number is the only thing remembered between them, and only to say which. */
export function LoginDialog({
  api,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  onClose(): void;
  onDone(): void;
}) {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");

  const labels: Record<Step, { title: string; confirm: string; busy: string; disabled: boolean }> = {
    phone: { title: "Zaloguj konto-właściciela", confirm: "Wyślij kod", busy: "Pytam Telegram…", disabled: phone.trim() === "" },
    code: { title: "Kod z Telegrama", confirm: "Zaloguj", busy: "Loguję…", disabled: code.trim() === "" },
    password: { title: "Hasło dwuetapowe", confirm: "Zaloguj", busy: "Loguję…", disabled: password === "" },
  };
  const now = labels[step];

  async function advance(): Promise<void> {
    const result =
      step === "phone"
        ? await api.loginStart(phone.trim(), signal())
        : step === "code"
          ? await api.loginCode(code.trim(), signal())
          : await api.loginPassword(password, signal());
    if (result.step === "done") {
      onDone();
      onClose();
      return;
    }
    setStep(result.step);
  }

  return (
    <ConfirmDialog
      title={now.title}
      confirmLabel={now.confirm}
      busyLabel={now.busy}
      confirmDisabled={now.disabled}
      fallbackError="logowanie się nie udało"
      closeOnSuccess={false}
      onConfirm={advance}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        {step === "phone" && (
          <>
            <p className="rounded bg-warning-soft px-2 py-1 text-xs text-warning">
              Użyj <strong>osobnego konta tylko do botów</strong> (z hasłem dwuetapowym), nie swojego prywatnego. Sesja tego
              konta pozwala pisać jako boty, którym ufasz.
            </p>
            <Field label="Numer telefonu konta" hint="W formie międzynarodowej, np. +48123456789. Telegram wyśle kod do aplikacji.">
              <input
                className={INPUT}
                value={phone}
                autoFocus
                inputMode="tel"
                autoComplete="off"
                placeholder="+48123456789"
                onChange={(e) => setPhone(e.target.value)}
              />
            </Field>
          </>
        )}
        {step === "code" && (
          <Field label="Kod, który przyszedł do Telegrama" hint="Zły kod nie kończy logowania — można podać kolejny.">
            <input
              className={INPUT}
              value={code}
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              onChange={(e) => setCode(e.target.value)}
            />
          </Field>
        )}
        {step === "password" && (
          <Field label="Hasło dwuetapowe tego konta">
            <input
              className={INPUT}
              type="password"
              value={password}
              autoFocus
              autoComplete="off"
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        )}
      </div>
    </ConfirmDialog>
  );
}

export function LogoutDialog({
  api,
  username,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  username: string | null;
  onClose(): void;
  onDone(): void;
}) {
  const [endedAtTelegram, setEnded] = useState<boolean | null>(null);

  if (endedAtTelegram !== null) {
    return (
      <ConfirmDialog
        title="Konto wylogowane"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          {endedAtTelegram
            ? "Sesja została zakończona w Telegramie i usunięta stąd."
            : "Sesja została usunięta stąd, ale Telegram nie odpowiedział — zakończ to urządzenie w ustawieniach Telegrama (Urządzenia)."}
        </p>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Wyloguj konto"
      confirmLabel="Wyloguj"
      busyLabel="Wylogowuję…"
      tone="danger"
      fallbackError="nie udało się wylogować"
      closeOnSuccess={false}
      onConfirm={async () => {
        setEnded(await api.logout(signal()));
        onDone();
      }}
      onClose={onClose}
    >
      <p className="text-xs text-ink-secondary">
        <span className="text-ink">{username ?? "Konto"}</span> przestaje być zalogowane. Boty i odbiorcy zostają i dalej
        dostają wiadomości — znika tylko możliwość zakładania, usuwania i rotacji botów, dopóki konta nie zalogujesz ponownie.
      </p>
    </ConfirmDialog>
  );
}

export function CreateBotDialog({
  api,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  onClose(): void;
  onDone(bot: Bot): void;
}) {
  const [title, setTitle] = useState("");
  const [username, setUsername] = useState("");
  const problem = botUsernameProblem(username);

  return (
    <ConfirmDialog
      title="Utwórz bota"
      confirmLabel="Utwórz"
      busyLabel="Rozmawiam z BotFatherem…"
      confirmDisabled={title.trim() === "" || username.trim() === "" || problem !== null}
      fallbackError="nie udało się utworzyć bota"
      onConfirm={async () => {
        onDone(await api.createBot(title.trim(), username.trim().replace(/^@/, ""), signal()));
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <Field label="Nazwa wyświetlana">
          <input className={INPUT} value={title} autoFocus placeholder="TradingCenter alerty" onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Nazwa użytkownika bota" hint={problem ?? "Musi kończyć się na „bot”. Telegram dopuszcza do 20 botów na konto."}>
          <input className={INPUT} value={username} placeholder="tc_alerty_bot" onChange={(e) => setUsername(e.target.value)} />
        </Field>
      </div>
    </ConfirmDialog>
  );
}

export function AdoptBotDialog({
  api,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  onClose(): void;
  onDone(bot: Bot): void;
}) {
  const [token, setToken] = useState("");

  return (
    <ConfirmDialog
      title="Dodaj istniejącego bota"
      confirmLabel="Dodaj"
      busyLabel="Pytam Telegram, czyj to token…"
      confirmDisabled={token.trim() === ""}
      fallbackError="nie udało się dodać bota"
      onConfirm={async () => {
        onDone(await api.adoptBot(token.trim(), signal()));
      }}
      onClose={onClose}
    >
      <Field
        label="Token od @BotFathera"
        hint="Zapisuje się w bazie i nigdy nie wraca w żadnej odpowiedzi. Bota dodanego tokenem nie da się usunąć stąd w BotFatherze — tylko zapomnieć."
      >
        <input
          className={INPUT}
          type="password"
          value={token}
          autoFocus
          autoComplete="off"
          onChange={(e) => setToken(e.target.value)}
        />
      </Field>
    </ConfirmDialog>
  );
}

const POLL_MS = 3000;

/**
 * The one tap a bot cannot do for itself. Asks for a name, shows the link and its code, and watches for the tap: the
 * destination turns "odbiera" without a reload. The watching runs only while this is open and the tab is visible.
 */
export function ActivateDialog({
  api,
  bot,
  existing,
  onClose,
  onDone,
}: {
  api: TelegramApi;
  bot: Bot;
  /** When set, a fresh link for a destination that already has a name — an expired one, or a blocked one. */
  existing?: Destination;
  onClose(): void;
  onDone(): void;
}) {
  const [name, setName] = useState(existing?.name ?? "operator");
  const [link, setLink] = useState<StartLink | null>(null);
  const [received, setReceived] = useState(false);
  // The watching must not restart each time the parent renders a fresh callback, or the interval never gets to fire.
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (link === null || received) return;
    const timer = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      void api
        .destinations(signal())
        .then((all) => {
          if (all.some((one) => one.name === link.destination.name && one.receives)) {
            setReceived(true);
            done.current();
          }
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, link, received]);

  if (received) {
    return (
      <ConfirmDialog
        title="Odbiorca aktywny"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          <span className="text-ink">{link?.destination.name}</span> odbiera wiadomości od @{bot.username}. Przypisz mu teraz
          cele w sekcji poniżej.
        </p>
      </ConfirmDialog>
    );
  }

  if (link !== null) {
    return (
      <ConfirmDialog
        title="Dotknij „Start” w Telegramie"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <div className="flex flex-col items-center gap-3 text-xs text-ink-secondary">
          <p>
            Z konta, które ma dostawać alerty, zeskanuj kod albo otwórz link i naciśnij <strong>Start</strong>. Ważne do{" "}
            {link.expiresAt.toLocaleTimeString("pl-PL")}; to okno samo zauważy tapnięcie.
          </p>
          <QrCode text={link.url} label={`Kod QR odnośnika startowego @${bot.username}`} />
          <a className="break-all text-primary underline" href={link.url} target="_blank" rel="noreferrer">
            {link.url}
          </a>
        </div>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title={`Aktywuj odbiorcę przez @${bot.username}`}
      confirmLabel="Pokaż link"
      busyLabel="Przygotowuję…"
      confirmDisabled={name.trim() === ""}
      fallbackError="nie udało się przygotować odbiorcy"
      closeOnSuccess={false}
      onConfirm={async () => {
        setLink(await api.offerDestination(name.trim(), bot.username, signal()));
      }}
      onClose={onClose}
    >
      <Field
        label="Nazwa odbiorcy"
        hint="To nazwa w przypisaniach, nie czat — przeżywa wymianę bota. Bot nie może odezwać się pierwszy, więc ktoś musi raz dotknąć linku."
      >
        <input className={INPUT} value={name} autoFocus disabled={existing !== undefined} onChange={(e) => setName(e.target.value)} />
      </Field>
    </ConfirmDialog>
  );
}

export function ConfirmRemoval({
  title,
  confirmLabel,
  body,
  fallbackError,
  onConfirm,
  onClose,
}: {
  title: string;
  confirmLabel: string;
  body: React.ReactNode;
  fallbackError: string;
  onConfirm(): Promise<void>;
  onClose(): void;
}) {
  return (
    <ConfirmDialog
      title={title}
      confirmLabel={confirmLabel}
      busyLabel="Pracuję…"
      tone="danger"
      fallbackError={fallbackError}
      onConfirm={onConfirm}
      onClose={onClose}
    >
      <div className="flex flex-col gap-2 text-xs text-ink-secondary">{body}</div>
    </ConfirmDialog>
  );
}

export function AssignDialog({
  api,
  destinations,
  initialKey = "",
  onClose,
  onDone,
}: {
  api: TelegramApi;
  destinations: Destination[];
  initialKey?: string;
  onClose(): void;
  onDone(): void;
}) {
  const [key, setKey] = useState(initialKey);
  const [destination, setDestination] = useState(destinations[0]?.name ?? "");
  const problem = keyProblem(key.trim());

  return (
    <ConfirmDialog
      title="Dodaj przypisanie"
      confirmLabel="Przypisz"
      busyLabel="Przypisuję…"
      confirmDisabled={key.trim() === "" || destination === "" || problem !== null}
      fallbackError="nie udało się przypisać"
      onConfirm={async () => {
        await api.assign(key.trim(), destination, signal());
        onDone();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <Field
          label="Cel, przedrostek albo *"
          hint={problem ?? "Przedrostek obejmuje całe segmenty: „youtube” łapie youtube.film.cokolwiek, ale nie youtubers. * to wszystko, czego nic nie złapało."}
        >
          <input className={INPUT} value={key} autoFocus placeholder="youtube.film" onChange={(e) => setKey(e.target.value)} />
        </Field>
        <Field label="Kto ma o tym słyszeć">
          <select className={INPUT} value={destination} onChange={(e) => setDestination(e.target.value)}>
            {destinations.map((one) => (
              <option key={one.name} value={one.name}>
                {one.name} (@{one.bot}) — {one.receives ? "odbiera" : "jeszcze nie odbiera"}
              </option>
            ))}
          </select>
        </Field>
      </div>
    </ConfirmDialog>
  );
}
